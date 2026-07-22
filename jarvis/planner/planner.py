"""Planner Engine (P5) — projection + KG → 랭킹된 PlannerProposal. 제안 전용.

결정적: 같은 소스 → 같은 제안(같은 checksum). 집행/트레이딩 없음.
append-only planner_proposals.jsonl(write 시 권한+audit). 기존 원장 무변경.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field

from jarvis.db.sqlite import Database
from jarvis.planner.coverage import analyze_all
from jarvis.planner.models import PlannerProposal, proposal_id


@dataclass
class PlannerReport:
    timestamp: str
    n_gaps: int = 0
    n_proposals: int = 0
    by_category: dict = field(default_factory=dict)
    proposals: list = field(default_factory=list)
    checksum: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _gap_to_proposal(gap) -> PlannerProposal:
    ev = gap.evidence or {}
    rationale = [gap.description]
    for k in ("remedy", "failure_reason", "reject_rate", "share", "n_blocked"):
        if k in ev and k != "remedy":
            rationale.append(f"{k}={ev[k]}")
    if ev.get("remedy"):
        rationale.append(ev["remedy"])
    target = gap.related_entities[0] if gap.related_entities else gap.type
    factors = {k: ev[k] for k in ("impact", "confidence", "evidence_strength") if k in ev}
    deps = ["knowledge_graph", "sqlite_projection"]
    if gap.type in ("DATA_GAP",):
        deps.append("data_acquisition")
    return PlannerProposal(
        proposal_id=proposal_id(gap.type, str(target)), category=gap.type,
        target_area=str(target), rationale=rationale,
        expected_value=factors.get("impact", 0.0), confidence=factors.get("confidence", 0.0),
        priority_score=gap.priority_score, dependencies=deps, status="proposed",
        factors=factors, created_at=gap.created_at)


def _checksum(proposals: list) -> str:
    h = hashlib.sha256()
    for p in sorted(proposals, key=lambda x: (-x.priority_score, x.proposal_id)):
        h.update(json.dumps([p.proposal_id, p.category, p.target_area, p.priority_score,
                             p.rationale], sort_keys=True, default=str).encode())
    return "sha256:" + h.hexdigest()


def _open(projection_db, graph_db, ts):
    """(p3, kg, tmp_paths). None이면 projection/graph 임시 재구축."""
    tmps = []
    if projection_db is None:
        from jarvis.db.projector import rebuild as p3_rebuild
        projection_db = os.path.join(tempfile.mkdtemp(), "proj.db")
        p3_rebuild(projection_db, ts=ts)
        tmps.append(projection_db)
    if graph_db is None:
        from jarvis.knowledge.builder import build as kg_build
        graph_db = os.path.join(tempfile.mkdtemp(), "graph.db")
        kg_build(graph_db, projection_db=projection_db, ts=ts)
        tmps.append(graph_db)
    return Database(projection_db, read_only=True), Database(graph_db, read_only=True), tmps


def run_planner(projection_db: str | None = None, graph_db: str | None = None,
                ts: str = "") -> PlannerReport:
    p3, kg, tmps = _open(projection_db, graph_db, ts)
    try:
        gaps = analyze_all(p3, kg, ts)
    finally:
        p3.close(); kg.close()
        for t in tmps:
            for sfx in ("", "-wal", "-shm"):
                try:
                    os.remove(t + sfx)
                except OSError:
                    pass

    proposals = [_gap_to_proposal(g) for g in gaps]
    # dedup(proposal_id) — 최고 우선순위 유지
    best: dict = {}
    for p in proposals:
        if p.proposal_id not in best or p.priority_score > best[p.proposal_id].priority_score:
            best[p.proposal_id] = p
    ranked = sorted(best.values(), key=lambda x: (-x.priority_score, x.proposal_id))

    by_cat: dict = {}
    for p in ranked:
        by_cat[p.category] = by_cat.get(p.category, 0) + 1
    return PlannerReport(timestamp=ts, n_gaps=len(gaps), n_proposals=len(ranked),
                         by_category=by_cat, proposals=[p.to_dict() for p in ranked],
                         checksum=_checksum(ranked))


# ── append-only 원장(write 시 권한+audit) ──
_LEDGER = "planner_proposals.jsonl"


def write_proposals(report: PlannerReport) -> dict:
    """제안 append. 권한: write_planner_proposal(RESEARCH_ONLY) + audit."""
    from jarvis.agents import PLANNER_AGENT
    from jarvis.audit import record
    from jarvis.config import state_path
    from jarvis.permissions import require
    require(PLANNER_AGENT, "write_planner_proposal", str(report.n_proposals))
    path = state_path(_LEDGER)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    row = {"timestamp": report.timestamp, "n_proposals": report.n_proposals,
           "by_category": report.by_category, "checksum": report.checksum,
           "proposals": report.proposals, "kind": "proposal_only", "executed": False}
    with open(path, "a") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    record({"layer": "planner", "action": "write_planner_proposal",
            "n_proposals": report.n_proposals, "checksum": report.checksum,
            "executed": False, "result": "written"})
    return {"written": True, "n_proposals": report.n_proposals}


def read_all() -> list[dict]:
    from jarvis.config import state_path
    path = state_path(_LEDGER)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(ln) for ln in f if ln.strip()]
