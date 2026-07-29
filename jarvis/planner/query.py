"""Planner 읽기 헬퍼 (P5). 원장 없으면 빈 결과."""
from __future__ import annotations

from jarvis.planner.planner import read_all


def latest_proposals(limit: int = 10) -> list[dict]:
    rows = read_all()
    if not rows:
        return []
    return rows[-1]["proposals"][:limit]


def proposals_by_category(category: str) -> list[dict]:
    rows = read_all()
    if not rows:
        return []
    return [p for p in rows[-1]["proposals"] if p.get("category") == category]


def history() -> list[dict]:
    return [{"timestamp": r["timestamp"], "n_proposals": r["n_proposals"],
             "by_category": r.get("by_category"), "checksum": r.get("checksum")}
            for r in read_all()]
