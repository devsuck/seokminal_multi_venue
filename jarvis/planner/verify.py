"""Planner 검증 (P5) — 결정적 출력. 두 번 실행 → 동일 checksum. 소스 무변경."""
from __future__ import annotations

from jarvis.planner.planner import run_planner


def verify(projection_db: str | None = None, graph_db: str | None = None) -> dict:
    r1 = run_planner(projection_db, graph_db, ts="verify")
    r2 = run_planner(projection_db, graph_db, ts="verify")
    deterministic = r1.checksum == r2.checksum
    return {"ok": bool(deterministic), "deterministic": deterministic,
            "checksum": r1.checksum, "n_proposals": r1.n_proposals,
            "by_category": r1.by_category}
