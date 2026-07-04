"""buyback 봇 손실 포지션 진단 + 청산룰 시뮬레이션.

목적: 손실난 포지션에 '왜 깨졌는지' 결정적 진단 + 더 정교한 청산룰이
      기대치를 올리는지 백테스트. v1은 동결 → 개선은 v2 섀도 후보로만.

정직: LLM 서술 아님(예산). 규칙 기반 결정적 진단(오히려 이 문제엔 LLM 추측보다 정확).
      가격 경로 = 실 KRX PIT 시리즈. """
from __future__ import annotations

import bisect
import json
import os
import time

from jarvis.paper.buyback_bot import _series, _positions
from jarvis.config import state_path

_CACHE = "buyback_analysis.json"


def _entry_idx(bars: dict, entry_date: str) -> int | None:
    ds = bars["dates"]
    i = bisect.bisect_left(ds, entry_date)
    return i if i < len(ds) and ds[i] == entry_date else None


def _hold_path(bars: dict, j: int, horizon: int) -> list[float]:
    """진입 종가 기준 일별 수익률 경로(비용 전, gross). j=진입 인덱스."""
    entry_px = bars["open"][j] if j < len(bars["open"]) else 0.0
    if entry_px <= 0:
        return []
    end = min(j + horizon + 1, len(bars["close"]))
    return [bars["close"][k] / entry_px - 1.0 for k in range(j, end)]


def _diagnose(rec: dict, path: list[float], cost: float, horizon: int) -> dict:
    """단일 포지션 손실 진단(결정적 태그 + 한 줄 설명)."""
    if not path:
        return {"tags": ["no_data"], "explain": "가격 경로 없음"}
    cur = path[-1] - cost
    peak = max(path)
    trough = min(path)
    peak_day = path.index(peak)
    held = len(path) - 1
    tags: list[str] = []
    parts: list[str] = []

    if held >= horizon:
        tags.append("past_horizon")
        parts.append(f"보유 {held}일 = 20일 엣지창 지남(원래 청산됐어야)")
    else:
        tags.append("still_open")
        parts.append(f"{held}일차(20일 창 안, 아직 미완)")

    if peak >= 0.03 and cur < 0:
        tags.append("gave_back")
        parts.append(f"고점 +{peak*100:.1f}%(D+{peak_day}) 찍고 반납")
    elif peak < 0.01:
        tags.append("never_worked")
        parts.append("진입 후 반등 사실상 없음(공시가 안 먹힘)")

    if cur <= -0.10:
        tags.append("deep_loss")
        parts.append(f"현재 {cur*100:.1f}% 깊은 손실")

    for s in (0.08, 0.12):
        if trough <= -s:
            tags.append(f"broke_{int(s*100)}")
            parts.append(f"장중 저점 {trough*100:.1f}% → 손절 -{int(s*100)}% 있었으면 방어")
            break

    return {"cur_ret": round(cur, 4), "peak": round(peak, 4), "trough": round(trough, 4),
            "peak_day": peak_day, "held": held, "tags": tags, "explain": " · ".join(parts)}


# ── 청산룰 시뮬(닫힌 포지션 전체 경로에 대안 룰 적용) ─────────────────
def _apply_rule(path: list[float], rule: str, cost: float, horizon: int) -> float | None:
    """gross 경로 → 룰별 실현수익(비용 후). path[0]=진입일(=0 근처)."""
    if len(path) < 2:
        return None
    body = path[1:]  # 진입 다음날부터
    if rule == "hold20":
        r = body[min(horizon, len(body)) - 1]
    elif rule.startswith("stop"):
        s = int(rule[4:]) / 100.0
        r = body[min(horizon, len(body)) - 1]
        for x in body[:horizon]:
            if x <= -s:
                r = -s
                break
    elif rule == "trail5":
        peak = 0.0
        r = body[min(horizon, len(body)) - 1]
        for x in body[:horizon]:
            peak = max(peak, x)
            if x <= peak - 0.05:
                r = x
                break
    elif rule == "take5trail":
        peak = 0.0
        armed = False
        r = body[min(horizon, len(body)) - 1]
        for x in body[:horizon]:
            peak = max(peak, x)
            if x >= 0.05:
                armed = True
            if armed and x <= peak - 0.05:
                r = x
                break
    else:
        return None
    return round(r - cost, 6)


def _stats(pnls: list[float]) -> dict:
    if not pnls:
        return {"n": 0, "mean": None, "median": None, "win_rate": None, "cum": None}
    s = sorted(pnls)
    m = s[len(s) // 2] if len(s) % 2 else (s[len(s) // 2 - 1] + s[len(s) // 2]) / 2
    return {"n": len(pnls), "mean": round(sum(pnls) / len(pnls), 6), "median": round(m, 6),
            "win_rate": round(sum(1 for x in pnls if x > 0) / len(pnls), 4), "cum": round(sum(pnls), 6)}


def _compute() -> dict:
    """손실 진단(열린 포지션) + 청산룰 시뮬(닫힌 포지션). v1 동결 → 섀도 제안.
    ⚠️ _series 빌드 80s 가능 → analyze()/refresh()로 캐싱 경유 권장."""
    from research.paper import buyback_config as CFG
    horizon, cost = CFG.HOLD_DAYS, CFG.COST_BASE_BPS / 1e4
    series = _series()
    pos = _positions()

    losers = []
    closed_paths = []
    for rec in pos.values():
        bars = series.get(rec["stock_code"])
        if bars is None:
            continue
        j = _entry_idx(bars, rec["entry_date"])
        if j is None:
            continue
        path = _hold_path(bars, j, horizon)
        if not path:
            continue
        if rec["status"] == "open":
            diag = _diagnose(rec, path, cost, horizon)
            if diag.get("cur_ret", 0) < 0:   # 손실만
                losers.append({"corp": rec["corp_name"], "code": rec["stock_code"],
                               "entry_date": rec["entry_date"], **diag})
        else:  # closed → 룰 시뮬용 경로
            closed_paths.append(path)

    losers.sort(key=lambda d: d["cur_ret"])   # 최악부터

    rules = ["hold20", "stop8", "stop12", "trail5", "take5trail"]
    sim = {}
    for rl in rules:
        pnls = [p for p in (_apply_rule(pp, rl, cost, horizon) for pp in closed_paths) if p is not None]
        sim[rl] = _stats(pnls)
    base = sim["hold20"]
    best = max(rules, key=lambda r: (sim[r]["mean"] or -9))
    return {
        "version": CFG.VERSION, "frozen": True, "horizon": horizon, "cost_bps": CFG.COST_BASE_BPS,
        "losers": losers[:20], "n_losers": len(losers),
        "exit_sim": sim, "baseline": "hold20", "best_rule": best,
        "improves": bool(sim[best]["mean"] and base["mean"] is not None and sim[best]["mean"] > base["mean"]),
        "shadow_note": ("v1(hold20)은 동결 — 여기 청산룰은 v2 섀도 후보로만 평가. "
                        "닫힌 포지션 전체 경로에 대안 룰 재적용해 기대치 비교. "
                        "in-sample 주의: 개선돼도 forward OOS 재현 필요."),
        "llm_note": "서술은 규칙 기반 결정적 진단(LLM 추측 아님). 이 문제엔 오히려 정확.",
    }


# ── 캐싱 래퍼 (엔드포인트용: _series 빌드 80s 회피) ──────────────────
def refresh() -> dict:
    """무거운 재계산 + 캐시 저장. 서비스 틱(warm 프로세스)에서 호출 권장."""
    res = _compute()
    res["computed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    try:
        p = state_path(_CACHE)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            json.dump(res, f, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        pass
    return res


def load_cached() -> dict | None:
    p = state_path(_CACHE)
    if not os.path.exists(p):
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def analyze(max_age_s: float = 21600) -> dict:
    """캐시 신선하면 반환(즉시), 아니면 재계산. 기본 6h."""
    c = load_cached()
    if c and time.time() - _parse_ts(c.get("computed_at")) < max_age_s:
        return c
    return refresh()


def _parse_ts(s: str | None) -> float:
    if not s:
        return 0.0
    try:
        return time.mktime(time.strptime(s, "%Y-%m-%dT%H:%M:%S"))
    except Exception:  # noqa: BLE001
        return 0.0
