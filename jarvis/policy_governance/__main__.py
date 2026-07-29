"""`python -m jarvis.policy_governance <cmd>` — 정책·설정 거버넌스 CLI. **관리·감사 전용.**

  register  --policy-id --name --category --version --params-json --by [--commit]
  request   --policy-id --new-hash --reason --by [--commit]
  approve   --change-id --approver --decision {APPROVE,REJECT} [--reason] [--commit]
  snapshot  [--commit]
  drift     [--commit]
  verify
  summary
  replay

실제 변경 실행 없음 — config/risk/autonomy/permission/kill switch 무변경·execution 없음.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _p(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _cmd_register(a) -> int:
    from jarvis.policy_governance.engine import PolicyGovernanceEngine
    params = json.loads(a.params_json) if a.params_json else {}
    d = PolicyGovernanceEngine().register_policy(
        a.policy_id, a.name, a.category, a.version, params, a.description or "",
        a.by, _now(), commit=a.commit)
    _p({"committed": a.commit, "policy": d.to_dict(),
        "note": "정책 등록(불변 버전) — 실제 적용 아님"})
    return 0


def _cmd_request(a) -> int:
    from jarvis.policy_governance.engine import PolicyGovernanceEngine
    cid = PolicyGovernanceEngine().request(a.policy_id, a.new_hash, a.reason or "", a.by,
                                           _now(), commit=a.commit)
    _p({"committed": a.commit, "change_id": cid, "note": "변경요청 기록 — 실제 변경 아님"})
    return 0


def _cmd_approve(a) -> int:
    from jarvis.policy_governance.engine import PolicyGovernanceEngine
    from jarvis.policy_governance.models import ApprovalError, IllegalTransition
    try:
        rec = PolicyGovernanceEngine().approve_change(
            a.change_id, a.approver, a.decision, a.reason or "", _now(), commit=a.commit)
    except (ApprovalError, IllegalTransition) as e:
        _p({"error": str(e)})
        return 1
    _p({"committed": a.commit, "approval": rec, "note": "승인 기록만 — 실제 적용 아님"})
    return 0


def _cmd_snapshot(a) -> int:
    from jarvis.policy_governance.engine import PolicyGovernanceEngine
    _p(PolicyGovernanceEngine().snapshot(_now(), commit=a.commit).to_dict())
    return 0


def _cmd_drift(a) -> int:
    from jarvis.policy_governance.engine import PolicyGovernanceEngine
    from jarvis.policy_governance.models import DriftError
    try:
        _p(PolicyGovernanceEngine().detect_drift(_now(), commit=a.commit).to_dict())
    except DriftError as e:
        _p({"error": str(e)})
        return 1
    return 0


def _cmd_verify(a) -> int:
    from jarvis.policy_governance.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_summary(a) -> int:
    from jarvis.policy_governance.engine import PolicyGovernanceEngine
    _p(PolicyGovernanceEngine().governance_report(_now()).to_dict())
    return 0


def _cmd_replay(a) -> int:
    from jarvis.policy_governance.engine import PolicyGovernanceEngine
    from jarvis.policy_governance.verify import replay
    _p(replay(PolicyGovernanceEngine(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.policy_governance")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("register")
    for f in ("policy-id", "name", "category", "version", "by"):
        r.add_argument(f"--{f}", required=True)
    r.add_argument("--params-json", default="{}")
    r.add_argument("--description", default="")
    r.add_argument("--commit", action="store_true")
    q = sub.add_parser("request")
    for f in ("policy-id", "new-hash", "by"):
        q.add_argument(f"--{f}", required=True)
    q.add_argument("--reason", default="")
    q.add_argument("--commit", action="store_true")
    p = sub.add_parser("approve")
    p.add_argument("--change-id", required=True)
    p.add_argument("--approver", required=True)
    p.add_argument("--decision", required=True, choices=["APPROVE", "REJECT"])
    p.add_argument("--reason", default="")
    p.add_argument("--commit", action="store_true")
    for name in ("snapshot", "drift"):
        s = sub.add_parser(name)
        s.add_argument("--commit", action="store_true")
    sub.add_parser("verify")
    sub.add_parser("summary")
    sub.add_parser("replay")
    args = ap.parse_args(argv)
    disp = {"register": _cmd_register, "request": _cmd_request, "approve": _cmd_approve,
            "snapshot": _cmd_snapshot, "drift": _cmd_drift, "verify": _cmd_verify,
            "summary": _cmd_summary, "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
