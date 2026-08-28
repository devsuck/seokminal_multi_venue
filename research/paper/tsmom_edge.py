"""tsmom 엣지 생존 모니터 — buyback_edge.py와 동일 패턴(캐시/read_only/force),
tsmom_forward.generate()의 출력 필드명(backtest_envelope/envelope_deviation)에 맞춤.
"""
from __future__ import annotations

import time

from research.paper import tsmom_config as CFG

_cache: dict = {"ts": 0.0, "data": None}
_TTL = 600.0


def _compute(need_months: int) -> dict:
    from research.paper.tsmom_forward import generate
    r = generate(since=CFG.FROZEN_AT, write=False)
    env = r["backtest_envelope"]
    fwd, dev = r["forward_months"], r["envelope_deviation"]
    oos = [{"month": m, "return": fwd[m], "in_envelope": dev[m] == "in_envelope"} for m in sorted(dev)]
    n_oos = len(oos)
    n_in = sum(1 for o in oos if o["in_envelope"])
    if n_oos == 0:
        status = "no_oos_yet"
    elif n_in / n_oos < 0.5:
        status = "drifting"
    elif n_oos < need_months:
        status = "accumulating"
    else:
        status = "confirmed"
    return {"status": status, "in_sample_months": env.get("n_months", 0),
            "envelope": {"p10": env.get("monthly_p10"), "avg": env.get("monthly_mean"), "p90": env.get("monthly_p90")},
            "oos_months": n_oos, "oos_in_envelope": n_in, "need_months": need_months, "oos": oos,
            "trend_regime": r.get("trend_regime")}


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
