"""배분 제안 원장 — append-only. write는 META_PORTFOLIO_AGENT 권한 필수. 삭제/재작성 없음.

제안 전용: 원장 기록은 '무엇을 제안했나'의 감사기록일 뿐, 집행 아님.
집행은 기존 execution gateway + risk governor + 사람 ARM이 별도로 결정(무수정).
"""
from __future__ import annotations

import json
import os

from jarvis.agents import META_PORTFOLIO_AGENT
from jarvis.audit import record
from jarvis.config import state_path
from jarvis.permissions import require
from jarvis.portfolio.allocator import AllocationResult

_LEDGER = "allocation_proposals.jsonl"


def write_proposal(result: AllocationResult) -> dict:
    """배분 제안 append. 권한: propose_allocation(LIVE_PROPOSAL_ONLY). 반환: 기록 요약."""
    require(META_PORTFOLIO_AGENT, "propose_allocation", result.method)
    path = state_path(_LEDGER)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    row = {"method": result.method, "portfolio_risk": result.portfolio_risk,
           "timestamp": result.timestamp, "diagnostics": result.diagnostics,
           "proposals": [p.__dict__ for p in result.proposals], "capital": "proposal_only",
           "executed": False}
    with open(path, "a") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    record({"layer": "meta_portfolio", "action": "write_allocation_proposal",
            "method": result.method, "n_proposals": len(result.proposals),
            "portfolio_risk": result.portfolio_risk, "executed": False, "result": "written"})
    return {"written": True, "n_proposals": len(result.proposals), "method": result.method}


def read_all() -> list[dict]:
    path = state_path(_LEDGER)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def read_latest(limit: int = 20) -> list[dict]:
    return read_all()[-limit:]
