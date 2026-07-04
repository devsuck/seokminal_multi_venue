"""Lv5 자가학습 단타 AI — ML+agentic 자율 파라미터 조정 (페이퍼 전용).

파이프라인:
  1. 사이클 이력에서 체결→청산 쌍 추출 (TP/SL 결과 parsing)
  2. 최근 20건 승률·평균수익 계산
  3. 자체 규칙으로 threshold·position_pct 조정
  4. 연속 손절 감지 → 일시 휴식 (drawdown 방지)
  5. 결정 이유를 note로 반환 (사이클 로그에 남겨 에이전틱 투명성 확보)
  6. (데이터 충분 시) 간이 온라인 모델: score_at_entry × outcome 가중합 →
     고수익 구간 score band 학습 → entry 필터
"""
from __future__ import annotations

import math
from typing import Any


# ── 매매 결과 파싱 ────────────────────────────────────────────────────────────

def extract_trade_outcomes(cycles: list[dict]) -> list[dict]:
    """사이클 이력에서 (entry_score, outcome) 쌍 추출.

    daytrade_tick 사이클 포맷:
      fill = {"side": "buy", "qty": N, "price": P}
      fill_symbol = "NVDA"
      actions = ["close NVDA (tp_hit)", "close NVDA (sl_hit)", "청산 000660 (tp_hit)", ...]
    """
    open_trades: dict[str, dict] = {}  # symbol → metadata at entry
    outcomes: list[dict] = []

    for c in cycles:
        actions: list[str] = c.get("actions") or []
        fill: dict | None = c.get("fill")
        fill_sym: str = c.get("fill_symbol") or ""
        lv5_note: str = c.get("lv5_note") or ""

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
            # 종목 코드 추출 ("close NVDA (tp_hit)" 또는 "청산 000660 (tp_hit)")
            parts = action.split()
            sym = parts[1] if len(parts) >= 2 else ""
            if not sym or sym not in open_trades:
                continue
            tp = "tp" in a_low
            sl = "sl" in a_low
            outcomes.append({
                "symbol": sym,
                "entry_score": open_trades[sym]["entry_score"],
                "lv5_threshold": open_trades[sym]["lv5_threshold"],
                "tp": tp,
                "sl": sl,
                "win": tp and not sl,
            })
            del open_trades[sym]

    return outcomes


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

    # ── 파라미터 조정 규칙 (적응형 threshold + 사이즈) ───────────────────────
    threshold = base_threshold
    position_pct = base_position_pct
    reasons: list[str] = []

    if win_rate < 0.35:
        threshold = min(base_threshold + 15, 85)
        position_pct = max(base_position_pct * 0.70, 0.04)
        reasons.append(f"승률 {win_rate:.0%} 부진 → 임계값 {threshold:.0f}(+15), 사이즈 ↓30%")
    elif win_rate < 0.45:
        threshold = min(base_threshold + 8, 80)
        position_pct = max(base_position_pct * 0.85, 0.05)
        reasons.append(f"승률 {win_rate:.0%} 저조 → 임계값 {threshold:.0f}(+8), 사이즈 ↓15%")
    elif win_rate > 0.68:
        threshold = max(base_threshold - 8, 25)
        position_pct = min(base_position_pct * 1.20, 0.20)
        reasons.append(f"승률 {win_rate:.0%} 우수 → 임계값 {threshold:.0f}(-8), 사이즈 ↑20%")
    elif win_rate > 0.58:
        threshold = max(base_threshold - 4, 30)
        position_pct = min(base_position_pct * 1.10, 0.18)
        reasons.append(f"승률 {win_rate:.0%} 양호 → 임계값 {threshold:.0f}(-4), 사이즈 ↑10%")
    else:
        reasons.append(f"승률 {win_rate:.0%} 정상 → 파라미터 유지")

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
        "n_trades": n,
        "lv5_note": note,
        "model_confidence": model_confidence,
    }
