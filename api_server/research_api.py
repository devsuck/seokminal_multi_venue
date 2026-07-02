"""Strategy Validation Terminal — research 산출물 서빙.

읽기전용. 검증 실험 registry + TSMOM paper_candidate forward-test 요약.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/research", tags=["research"])

# TSMOM 요약 캐시(백테스트 여러번 도니 60초 캐시)
_tsmom_cache: dict = {"ts": 0.0, "data": None}


@router.get("/experiments")
def experiments() -> dict:
    """검증 실험 registry 전체 (rejected / blocked / paper_candidate...)."""
    from research.agents.experiment_registry import load_all
    entries = load_all()
    # 최신 상태만(같은 hypothesis_id는 마지막 항목 우선)
    latest: dict = {}
    for e in entries:
        hid = e.get("hypothesis_id")
        if hid:
            latest[hid] = e
    rows = list(latest.values())
    counts: dict = {}
    for e in rows:
        s = e.get("status", "?")
        counts[s] = counts.get(s, 0) + 1
    return {"experiments": rows, "counts": counts, "total": len(rows)}


@router.get("/tsmom")
def tsmom() -> dict:
    """TSMOM paper_candidate forward-test 요약 (envelope/regime/sleeve/cost)."""
    import time
    if _tsmom_cache["data"] is not None and time.time() - _tsmom_cache["ts"] < 60:
        return _tsmom_cache["data"]
    try:
        from research.paper.tsmom_forward import generate
        data = generate(write=False)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"TSMOM 데이터 없음(선물 pull 필요): {exc}") from exc
    _tsmom_cache.update(ts=time.time(), data=data)
    return data
