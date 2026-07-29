"""리밸런스 제안 원장 — append-only. write는 META_PORTFOLIO_AGENT 권한 필수.

제안 전용: 주문 안 냄(orders_placed=false, executed=false). 삭제/재작성 없음.
집행은 기존 execution gateway + risk governor + 사람 ARM이 별도로 결정(무수정).
"""
from __future__ import annotations

import json
import os

from jarvis.agents import META_PORTFOLIO_AGENT
from jarvis.audit import record
from jarvis.config import state_path
from jarvis.permissions import require
from jarvis.portfolio.decision_engine import RebalanceDecision

_LEDGER = "rebalance_proposals.jsonl"


def write_proposal(decision: RebalanceDecision) -> dict:
    """리밸런스 제안 append. 권한: propose_rebalance(LIVE_PROPOSAL_ONLY)."""
    require(META_PORTFOLIO_AGENT, "propose_rebalance",
            f"any_rebalance={decision.any_rebalance}")
    path = state_path(_LEDGER)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    row = {"timestamp": decision.timestamp, "any_rebalance": decision.any_rebalance,
           "cooldown_active": decision.cooldown_active,
           "total_turnover": decision.total_turnover,
           "total_estimated_cost": decision.total_estimated_cost,
           "proposals": [p.__dict__ for p in decision.proposals],
           "capital": "proposal_only", "orders_placed": False, "executed": False}
    with open(path, "a") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    record({"layer": "meta_portfolio", "action": "write_rebalance_proposal",
            "any_rebalance": decision.any_rebalance, "cooldown_active": decision.cooldown_active,
            "total_turnover": decision.total_turnover, "orders_placed": False,
            "executed": False, "result": "written"})
    return {"written": True, "any_rebalance": decision.any_rebalance,
            "n_proposals": len(decision.proposals)}


def read_all() -> list[dict]:
    path = state_path(_LEDGER)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def read_latest(limit: int = 20) -> list[dict]:
    return read_all()[-limit:]
