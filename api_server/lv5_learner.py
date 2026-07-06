"""Lv5 자가학습 단타 AI — 기대값(expectancy) 기반 자율 파라미터 조정 (페이퍼 전용).

파이프라인:
  1. 사이클 이력에서 체결→청산 쌍 추출 (실현 수익률 % 파싱 포함)
  2. 최근 거래의 비용 차감 기대값(expectancy) + 경로 MDD 계산 (shrinkage 적용)
  3. 기대값·MDD 기준으로 threshold·position_pct 조정 — 승률은 표시용으로만
  4. 연속 손절 감지 → 일시 휴식 (drawdown 방지)
  5. 결정 이유를 note로 반환 (사이클 로그에 남겨 에이전틱 투명성 확보)
  6. (데이터 충분 시) score band별 posterior → entry 필터
  7. validate_proposal(): Claude 리뷰가 제안한 threshold를 counterfactual replay로
     검증 — 통과 못 하면 적용 안 함 (검증 게이트)
"""
from __future__ import annotations

import math
import re
from typing import Any

# 왕복 거래비용 (수수료+슬리피지 보수 추정, fraction). 기대값은 항상 이 비용 차감 후.
COST_PCT = 0.001

# 실현 수익률 파싱: "익절 +5.2%" / "손절 -3.1%" → 0.052 / -0.031
_PNL_RE = re.compile(r"([+-]?\d+(?:\.\d+)?)%")


# ── 매매 결과 파싱 ────────────────────────────────────────────────────────────

def extract_trade_outcomes(cycles: list[dict]) -> list[dict]:
    """사이클 이력에서 (entry_score, outcome, net_ret) 추출.

    daytrade_tick 사이클 포맷:
      fill = {"side": "buy", "qty": N, "price": P}
      fill_symbol = "NVDA"
      actions = ["close NVDA (익절 +5.2%)", "청산 000660 (손절 -3.1%)",
                 "close TSLA (신호 반전)", ...]

    net_ret: 실현 수익률 fraction (비용 차감 전). % 파싱 실패(신호 반전/소멸 청산 등)
    시 None — 기대값 계산에서 제외되고 승패 카운트에만 반영.
    """
    open_trades: dict[str, dict] = {}  # symbol → metadata at entry
    outcomes: list[dict] = []

    for c in cycles:
        actions: list[str] = c.get("actions") or []
        fill: dict | None = c.get("fill")
        fill_sym: str = c.get("fill_symbol") or ""

        # 신규 체결 기록
        if fill and fill.get("side") == "buy" and fill_sym:
            open_trades[fill_sym] = {
                "entry_price": float(fill.get("price") or 0),
                "entry_score": float(c.get("best_score") or 0),
                "lv5_threshold": float(c.get("lv5_threshold") or 0),
            }

        # 청산 기록 파싱
        for action in actions:
            a_low = action.lower()
            if "close" not in a_low and "청산" not in a_low:
                continue
            # 종목 코드 추출 ("close NVDA (익절 +5.2%)" 또는 "청산 000660 (손절 -3.1%)")
            parts = action.split()
            sym = parts[1] if len(parts) >= 2 else ""
            if not sym or sym not in open_trades:
                continue
            # TP/SL 판별 — 한글(익절/손절)과 영문(tp/sl) 표기 모두 지원
            tp = "익절" in action or "tp" in a_low
            sl = "손절" in action or "sl" in a_low
            m = _PNL_RE.search(action)
            net_ret = float(m.group(1)) / 100 if m else None
            outcomes.append({
                "symbol": sym,
                "entry_score": open_trades[sym]["entry_score"],
                "lv5_threshold": open_trades[sym]["lv5_threshold"],
                "tp": tp,
                "sl": sl,
                "win": tp and not sl,
                "net_ret": net_ret,
            })
            del open_trades[sym]

    return outcomes


# ── 기대값 통계 ───────────────────────────────────────────────────────────────

def _expectancy_stats(outcomes: list[dict], *, shrink_k: int = 10) -> dict:
    """비용 차감 기대값 + 경로 MDD.

    shrinkage: 표본이 적을수록 기대값을 0으로 수축 (n/(n+k)) — 20건짜리
    표본평균을 액면 그대로 믿고 사이즈 키우는 것 방지.
    """
    rets = [o["net_ret"] - COST_PCT for o in outcomes if o.get("net_ret") is not None]
    n = len(rets)
    if n == 0:
        return {"expectancy": None, "expectancy_raw": None, "mdd": None, "n_ret": 0}
    raw = sum(rets) / n
    shrunk = raw * n / (n + shrink_k)
    # 경로 MDD (거래 순서 누적 수익 기준)
    eq = 0.0
    peak = 0.0
    mdd = 0.0
    for r in rets:
        eq += r
        peak = max(peak, eq)
        mdd = max(mdd, peak - eq)
    return {"expectancy": shrunk, "expectancy_raw": raw, "mdd": mdd, "n_ret": n}


# ── 간이 온라인 모델: score band 학습 ────────────────────────────────────────

def _score_band_filter(outcomes: list[dict], candidate_score: float) -> float:
    """최근 거래에서 score band별 승률 → 해당 구간의 신뢰도 (0..1) 반환.

    구간: [0,40), [40,60), [60,80), [80,100]
    각 구간 win/total → posterior (Laplace smoothing 1/2).
    candidate_score가 있는 구간의 posterior 반환.
    """
    bands: dict[int, list[int]] = {0: [], 40: [], 60: [], 80: []}

    def _band(s: float) -> int:
        if s < 40: return 0
        if s < 60: return 40
        if s < 80: return 60
        return 80

    for o in outcomes[-40:]:
        b = _band(float(o.get("entry_score") or 0))
        bands[b].append(1 if o["win"] else 0)

    b = _band(candidate_score)
    wins_in_band = bands[b]
    n = len(wins_in_band)
    if n == 0:
        return 0.5  # 데이터 없으면 중립
    wins = sum(wins_in_band)
    # Laplace smoothing
    return (wins + 0.5) / (n + 1)


# ── 메인 진입점 ───────────────────────────────────────────────────────────────

def compute_lv5_params(
    cycles: list[dict],
    base_threshold: float,
    base_position_pct: float,
    *,
    recent_window: int = 20,
    min_data: int = 5,
) -> dict:
    """사이클 이력 → 자가학습 파라미터 반환.

    Returns:
        threshold        : 조정된 entry 임계값
        position_pct     : 조정된 포지션 비율
        pause            : True면 이번 사이클 entry skip (drawdown 방지)
        win_rate         : 최근 승률 (None if 데이터 부족)
        n_trades         : 최근 거래 수
        lv5_note         : 에이전틱 투명성 — 왜 파라미터를 바꿨는지 텍스트
        model_confidence : score band 신뢰도 (계산 불가 시 None)
    """
    outcomes = extract_trade_outcomes(cycles)
    recent = outcomes[-recent_window:]
    n = len(recent)

    if n < min_data:
        return {
            "threshold": base_threshold,
            "position_pct": base_position_pct,
            "pause": False,
            "win_rate": None,
            "n_trades": n,
            "lv5_note": f"[Lv5 학습중] 데이터 {n}/{min_data}건 — 기본 파라미터 사용",
            "model_confidence": None,
        }

    wins = sum(1 for o in recent if o["win"])
    win_rate = wins / n

    # 연속 손절 감지 (마지막 3건 전부 SL → 1사이클 휴식)
    last3 = recent[-3:]
    all_sl = len(last3) == 3 and all(o["sl"] for o in last3)

    # ── 파라미터 조정 규칙 — 기대값(비용 차감·shrinkage) 기준 ────────────────
    # 목표함수는 expectancy/MDD. 승률은 표시용으로만 유지 (v2 원칙).
    stats = _expectancy_stats(recent)
    exp_ = stats["expectancy"]
    mdd = stats["mdd"]
    threshold = base_threshold
    position_pct = base_position_pct
    reasons: list[str] = []

    if exp_ is None:
        # 실현 % 파싱 가능한 거래 없음 (전부 신호 청산 등) → 조정 보류
        reasons.append(f"수익률 라벨 없음({n}건 중 0) → 파라미터 유지")
    elif exp_ < -COST_PCT:
        threshold = min(base_threshold + 15, 85)
        position_pct = max(base_position_pct * 0.70, 0.04)
        reasons.append(f"기대값 {exp_*100:+.2f}%/건 (비용 못 이김) → 임계값 {threshold:.0f}(+15), 사이즈 ↓30%")
    elif exp_ < 0:
        threshold = min(base_threshold + 8, 80)
        position_pct = max(base_position_pct * 0.85, 0.05)
        reasons.append(f"기대값 {exp_*100:+.2f}%/건 음수 → 임계값 {threshold:.0f}(+8), 사이즈 ↓15%")
    elif exp_ > 0.004 and (mdd or 0) < 0.06:
        threshold = max(base_threshold - 8, 25)
        position_pct = min(base_position_pct * 1.20, 0.20)
        reasons.append(f"기대값 {exp_*100:+.2f}%/건 · MDD {mdd*100:.1f}% 양호 → 임계값 {threshold:.0f}(-8), 사이즈 ↑20%")
    elif exp_ > 0.0015:
        threshold = max(base_threshold - 4, 30)
        position_pct = min(base_position_pct * 1.10, 0.18)
        reasons.append(f"기대값 {exp_*100:+.2f}%/건 플러스 → 임계값 {threshold:.0f}(-4), 사이즈 ↑10%")
    else:
        reasons.append(f"기대값 {exp_*100:+.2f}%/건 (승률 {win_rate:.0%}) → 파라미터 유지")

    # 드로다운 거버너 — 기대값과 무관하게 경로 MDD 크면 사이즈 축소
    if mdd is not None and mdd > 0.10:
        position_pct = max(position_pct * 0.70, 0.04)
        reasons.append(f"경로 MDD {mdd*100:.1f}% 과대 → 사이즈 추가 ↓30%")

    if all_sl:
        reasons.append("연속 SL 3회 → 이번 사이클 entry 휴식")

    # ── score band 모델 (≥15건 이상일 때만 의미) ─────────────────────────────
    model_confidence: float | None = None
    if n >= 15:
        # 중간 점수(threshold 기준) 구간 신뢰도 반환
        model_confidence = round(_score_band_filter(recent, threshold + 5), 3)
        if model_confidence < 0.35:
            threshold = min(threshold + 5, 85)
            reasons.append(f"모델 신뢰도 {model_confidence:.0%} 낮음 → 임계값 추가 +5")

    note = f"[Lv5 자가학습] {n}건 관찰. " + " | ".join(reasons)

    return {
        "threshold": round(threshold, 1),
        "position_pct": round(position_pct, 4),
        "pause": all_sl,
        "win_rate": round(win_rate, 3),
        "expectancy": round(exp_, 5) if exp_ is not None else None,
        "mdd": round(mdd, 4) if mdd is not None else None,
        "n_trades": n,
        "lv5_note": note,
        "model_confidence": model_confidence,
    }


# ── 검증 게이트: Claude 제안 counterfactual replay ────────────────────────────

def validate_proposal(
    outcomes: list[dict],
    current_threshold: float,
    proposed_threshold: float,
    *,
    min_n: int = 5,
    epsilon: float = 0.0005,
) -> dict:
    """Claude 리뷰가 제안한 threshold를 기록된 거래로 재현 검증.

    원리:
      - 제안 ≥ 현재: 과거 거래 중 entry_score ≥ 제안값 부분집합의 기대값이
        전체 기대값보다 나빠지지 않아야 통과 (유효한 counterfactual).
      - 제안 < 현재: 임계값 아래 거래는 애초에 진입 안 해서 데이터가 없음 —
        counterfactual 불가. 현재 기대값이 플러스일 때만 소폭(-5까지) 허용.

    Returns: {passed, reason, n_all, n_subset, exp_all, exp_subset}
    """
    valid = [o for o in outcomes if o.get("net_ret") is not None]
    rets_all = [o["net_ret"] - COST_PCT for o in valid]
    n_all = len(rets_all)
    result = {
        "passed": False, "reason": "", "n_all": n_all,
        "n_subset": None, "exp_all": None, "exp_subset": None,
    }
    if n_all < min_n:
        result["reason"] = f"수익률 라벨 {n_all}건 < 최소 {min_n}건 — 판단 불가, 기존 유지"
        return result
    exp_all = sum(rets_all) / n_all
    result["exp_all"] = round(exp_all, 5)

    if abs(proposed_threshold - current_threshold) < 1e-9:
        result.update(passed=True, reason="임계값 변경 없음")
        return result

    if proposed_threshold >= current_threshold:
        subset = [o["net_ret"] - COST_PCT for o in valid
                  if o["entry_score"] >= proposed_threshold]
        n_sub = len(subset)
        result["n_subset"] = n_sub
        if n_sub < min_n:
            result["reason"] = f"제안 임계값 {proposed_threshold:.0f} 적용 시 표본 {n_sub}건 < {min_n} — 기각"
            return result
        exp_sub = sum(subset) / n_sub
        result["exp_subset"] = round(exp_sub, 5)
        if exp_sub >= exp_all - epsilon:
            result.update(passed=True,
                          reason=f"replay 통과: 부분집합 기대값 {exp_sub*100:+.2f}% ≥ 전체 {exp_all*100:+.2f}%")
        else:
            result["reason"] = (f"replay 기각: 부분집합 기대값 {exp_sub*100:+.2f}% < "
                                f"전체 {exp_all*100:+.2f}%")
        return result

    # 제안 < 현재 — 완화 방향은 데이터 없음. 보수적으로만 허용.
    if exp_all > 0 and (current_threshold - proposed_threshold) <= 5:
        result.update(passed=True,
                      reason=f"완화 -{current_threshold - proposed_threshold:.0f} 허용 (현재 기대값 {exp_all*100:+.2f}% 플러스)")
    else:
        result["reason"] = ("완화 방향은 counterfactual 데이터 없음 — "
                            f"현재 기대값 {exp_all*100:+.2f}%"
                            + ("" if exp_all > 0 else " 음수라 기각")
                            + ("" if (current_threshold - proposed_threshold) <= 5 else " · 폭 5 초과 기각"))
    return result
