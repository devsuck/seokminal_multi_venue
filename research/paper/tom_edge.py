"""turn-of-month 엣지 생존 모니터 — buyback_edge.py와 동일 패턴(캐시/read_only/force),
tom_forward.generate()의 출력 필드명(envelope.mean_p10/p90/forward_cohorts)에 맞춤.
"""
from __future__ import annotations

import time

from research.paper import tom_config as CFG

_cache: dict = {"ts": 0.0, "data": None}
_TTL = 600.0


def _compute(need_months: int) -> dict:
    from research.paper.tom_forward import generate
    r = generate(since=CFG.FROZEN_AT, write=False)
    env = r["envelope"]
    p10, p90 = env.get("mean_p10"), env.get("mean_p90")
    oos = []
    n_in = 0
    for m, c in sorted(r.get("forward_cohorts", {}).items()):
        inside = p10 is not None and p90 is not None and p10 <= c["mean"] <= p90
        n_in += 1 if inside else 0
        oos.append({"month": m, "mean": c["mean"], "n": c["n"], "in_envelope": inside})
    n_oos = len(oos)
    if n_oos == 0:
        status = "no_oos_yet"
    elif n_in / n_oos < 0.5:
        status = "drifting"
    elif n_oos < need_months:
        status = "accumulating"
    else:
        status = "confirmed"
    return {"status": status, "in_sample_months": env.get("n_months", 0),
            "envelope": {"p10": p10, "avg": env.get("mean_avg"), "p90": p90},
            "oos_months": n_oos, "oos_in_envelope": n_in, "need_months": need_months, "oos": oos}


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
