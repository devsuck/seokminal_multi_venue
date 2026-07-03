"""buyback 엣지 생존 모니터 — forward(OOS, 동결 이후) 월 코호트가 in-sample
envelope 안에 있나 = 엣지 decay 감지. series 로드 무거움 → 캐시.

endpoint(/lab/execution/edge)와 service(배경 워밍)가 공유. service가 주기적으로
edge_status(force=True)로 캐시를 데워두면 프론트는 즉시 캐시된 값을 받는다.
"""
from __future__ import annotations

import time

from research.paper import buyback_config as CFG

_cache: dict = {"ts": 0.0, "data": None}
_TTL = 600.0


_MIN_OOS_EVENTS = 20   # 이벤트 레벨 판단 최소 표본(사전등록)


def _event_level(rows: list) -> dict:
    """이벤트 레벨 OOS 검정 — 월 코호트(월 ~1개)보다 빨리 쌓임(월 ~70건).
    사전등록: p_worse = Mann-Whitney 단측 P(OOS 분포가 in-sample보다 나쁨).
    arm 게이트(월 기준 동결)는 불변 — 보조 증거."""
    in_r = [r for d, r in rows if d < CFG.FROZEN_AT]
    oos_r = [r for d, r in rows if d >= CFG.FROZEN_AT]
    import statistics as _st
    out = {"n_oos": len(oos_r), "n_in_sample": len(in_r),
           "oos_median": round(_st.median(oos_r), 6) if oos_r else None,
           "in_sample_median": round(_st.median(in_r), 6) if in_r else None,
           "powered": len(oos_r) >= _MIN_OOS_EVENTS, "min_events": _MIN_OOS_EVENTS,
           "p_worse": None}
    if oos_r and in_r:
        try:
            from scipy.stats import mannwhitneyu
            # alternative="less": OOS가 확률적으로 더 작다(나쁘다) = decay 방향 단측
            out["p_worse"] = round(float(mannwhitneyu(oos_r, in_r, alternative="less").pvalue), 4)
        except Exception:  # noqa: BLE001
            pass
    return out


def _compute(need_months: int) -> dict:
    from research.paper.buyback_forward import generate
    r = generate(since=CFG.FROZEN_AT, write=False)
    env = r.get("envelope", {})
    p10, p90 = env.get("cohort_median_p10"), env.get("cohort_median_p90")
    fwd = r.get("forward_cohorts", {}) or {}
    oos, n_in = [], 0
    for m, c in sorted(fwd.items()):
        inside = p10 is not None and p90 is not None and p10 <= c["median"] <= p90
        n_in += 1 if inside else 0
        oos.append({"month": m, "median": c["median"], "n": c["n"], "in_envelope": inside})
    n_oos = len(oos)
    if n_oos == 0:
        status = "no_oos_yet"        # 동결 후 완결 월 없음 = 카운트다운 0
    elif n_in / n_oos < 0.5:
        status = "drifting"          # 과반 envelope 밖 = 엣지 소멸 경고
    elif n_oos < need_months:
        status = "accumulating"      # envelope 안이나 월 부족
    else:
        status = "confirmed"         # 충분한 OOS + envelope 안 = 살아있음
    return {"status": status, "in_sample_months": env.get("n_months", 0),
            "envelope": {"p10": p10, "avg": env.get("cohort_median_avg"), "p90": p90},
            "oos_months": n_oos, "oos_in_envelope": n_in, "need_months": need_months, "oos": oos,
            "event_level": _event_level(r.get("rows", []))}


def edge_status(need_months: int | None = None, force: bool = False, read_only: bool = False) -> dict:
    """엣지 생존 상태.
    read_only=True(endpoint용): 계산 절대 안 함 — 캐시 있으면 즉시 반환, 없으면 'warming'.
    force=True(service 배경 워밍용): 재계산 후 캐시 갱신(유일 계산자).
    """
    need = CFG.MIN_OBSERVATION_MONTHS if need_months is None else need_months
    if read_only:
        if _cache["data"] is not None:
            return _cache["data"]
        return {"status": "warming", "in_sample_months": 0, "envelope": {},
                "oos_months": 0, "oos_in_envelope": 0, "need_months": need, "oos": []}
    if not force and _cache["data"] is not None and time.time() - _cache["ts"] < _TTL:
        return _cache["data"]
    try:
        out = _compute(need)
    except Exception as exc:  # noqa: BLE001
        return {"status": "unavailable", "error": str(exc)[:60], "oos_months": 0,
                "in_sample_months": 0, "envelope": {}, "oos": [], "need_months": need}
    _cache.update(ts=time.time(), data=out)
    return out
