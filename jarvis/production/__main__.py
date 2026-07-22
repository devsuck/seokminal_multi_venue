"""`python -m jarvis.production <cmd>` — 프로덕션 경계 CLI. 기본 dry-run.

  status                          모니터 스냅샷(읽기)
  check [--commit]                paper_active 전략들 게이트 검사(ALLOW/BLOCK)
  approve --proposal-id X [--commit]   사람 승인(기본 미리보기)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cmd_status() -> int:
    from jarvis.production.monitor import ProductionMonitor
    print(json.dumps(ProductionMonitor().snapshot(_now()), ensure_ascii=False, indent=2, default=str))
    return 0


def _demo_proposals(now: str):
    """registry paper_active 전략 → 데모 ProductionProposal(경계 시연용)."""
    from jarvis.production.models import ProductionProposal, make_proposal_id
    from jarvis.registry import StrategyRegistry
    out = []
    for r in StrategyRegistry().list("paper_active"):
        sid = r["strategy_id"]
        out.append(ProductionProposal(
            proposal_id=make_proposal_id("demo", sid, now), source="demo", strategy=sid,
            rationale=["demo boundary check — paper_active strategy"], created_at=now))
    return out


def _cmd_check(commit: bool) -> int:
    from jarvis.production.gate import ProductionGate
    now = _now()
    gate = ProductionGate()
    results = []
    for prop in _demo_proposals(now):
        dec = gate.check(prop, now, ts=now)
        if commit:
            gate.persist(prop, dec)
        results.append({"strategy": prop.strategy, "decision": dec.decision,
                        "failed_checks": dec.failed_checks})
    out = {"as_of": now, "n_proposals": len(results), "results": results,
           "note": "제안 전용 — 집행 없음. " + ("COMMIT: 결정 기록됨." if commit else "DRY-RUN.")}
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_approve(proposal_id: str | None, commit: bool) -> int:
    from jarvis.agents import HUMAN_ADMIN
    from jarvis.production.approval import ApprovalGate, read_approvals, read_proposals
    now = _now()
    if not proposal_id:
        print(json.dumps({"error": "--proposal-id required"}, ensure_ascii=False)); return 1
    if not commit:
        props = read_proposals()
        prop = next((p for p in props if p["proposal_id"] == proposal_id), None)
        from jarvis.production.approval import proposal_status
        st = proposal_status(prop, read_approvals(), now) if prop else "not_found"
        print(json.dumps({"proposal_id": proposal_id, "current_status": st,
                          "note": "DRY-RUN — --commit 로 사람(ADMIN) 승인 기록"},
                         ensure_ascii=False, indent=2))
        return 0
    res = ApprovalGate().approve(proposal_id, now, ts=now, approver=HUMAN_ADMIN)
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="jarvis.production")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    c = sub.add_parser("check")
    c.add_argument("--commit", action="store_true")
    a = sub.add_parser("approve")
    a.add_argument("--proposal-id", default=None)
    a.add_argument("--commit", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "status":
        return _cmd_status()
    if args.cmd == "check":
        return _cmd_check(args.commit)
    if args.cmd == "approve":
        return _cmd_approve(args.proposal_id, args.commit)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
