"""Human Approval Gate (P6.1) — 프로덕션 제안은 사람 승인 필수.

규칙: 승인 필요 · 만료 제안 거부 · 중복 승인 방지 · 불변 승인이력(append-only).
승인은 ADMIN_HUMAN_ONLY(어떤 AI도 불가). 기존 파일 무변경.
"""
from __future__ import annotations

import json
import os

from jarvis.agents import HUMAN_ADMIN, LIVE_PROPOSAL_AGENT
from jarvis.config import state_path
from jarvis.permissions import require
from jarvis.production.audit import record_production
from jarvis.production.models import ApprovalRecord, ProductionProposal, is_expired

_PROPOSALS = "production_proposals.jsonl"
_APPROVALS = "production_approvals.jsonl"


def _read(name: str) -> list[dict]:
    p = state_path(name)
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def _append(name: str, row: dict) -> None:
    p = state_path(name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def read_proposals() -> list[dict]:
    return _read(_PROPOSALS)


def read_approvals() -> list[dict]:
    return _read(_APPROVALS)


def submit(proposal: ProductionProposal, principal=LIVE_PROPOSAL_AGENT) -> dict:
    """제안 제출 → PENDING_APPROVAL. 권한: submit_production_proposal(LIVE_PROPOSAL_ONLY)."""
    require(principal, "submit_production_proposal", proposal.proposal_id)
    row = {**proposal.to_dict(), "status": "PENDING_APPROVAL"}
    _append(_PROPOSALS, row)
    record_production({"action": "submit_production_proposal",
                       "proposal_id": proposal.proposal_id, "strategy": proposal.strategy,
                       "result": "pending_approval"})
    return {"submitted": True, "proposal_id": proposal.proposal_id, "status": "PENDING_APPROVAL"}


def proposal_status(proposal: dict, approvals: list[dict], now: str) -> str:
    pid = proposal["proposal_id"]
    decs = [a for a in approvals if a["proposal_id"] == pid]
    if any(d["decision"] == "APPROVED" for d in decs):
        return "APPROVED"
    if any(d["decision"] == "REJECTED" for d in decs):
        return "REJECTED"
    if is_expired(proposal.get("created_at", ""), now):
        return "EXPIRED"
    return "PENDING_APPROVAL"


class ApprovalGate:
    """사람 승인 게이트. 승인/거부는 불변 이력."""

    def approve(self, proposal_id: str, now: str, ts: str = "", approver=HUMAN_ADMIN) -> dict:
        """사람 승인. 권한: approve_production_proposal(ADMIN_HUMAN_ONLY, 사람만)."""
        require(approver, "approve_production_proposal", proposal_id)
        props = read_proposals()
        prop = next((p for p in props if p["proposal_id"] == proposal_id), None)
        if prop is None:
            return {"approved": False, "reason": "proposal_not_found", "proposal_id": proposal_id}
        approvals = read_approvals()
        if any(a["proposal_id"] == proposal_id and a["decision"] == "APPROVED" for a in approvals):
            return {"approved": False, "reason": "duplicate_approval", "proposal_id": proposal_id}
        if is_expired(prop.get("created_at", ""), now):
            self._record(proposal_id, "REJECTED", approver.name, "expired", ts)
            return {"approved": False, "reason": "expired", "proposal_id": proposal_id}
        self._record(proposal_id, "APPROVED", approver.name, "human_approved", ts)
        return {"approved": True, "proposal_id": proposal_id, "status": "APPROVED"}

    def reject(self, proposal_id: str, reason: str, ts: str = "", approver=HUMAN_ADMIN) -> dict:
        require(approver, "approve_production_proposal", proposal_id)
        self._record(proposal_id, "REJECTED", approver.name, reason, ts)
        return {"approved": False, "proposal_id": proposal_id, "status": "REJECTED", "reason": reason}

    def _record(self, pid: str, decision: str, approver: str, reason: str, ts: str) -> None:
        rec = ApprovalRecord(proposal_id=pid, decision=decision, approver=approver,
                             reason=reason, timestamp=ts)
        _append(_APPROVALS, rec.to_dict())
        record_production({"action": "approve_production_proposal", "proposal_id": pid,
                           "decision": decision, "approver": approver, "reason": reason,
                           "result": "recorded"})
