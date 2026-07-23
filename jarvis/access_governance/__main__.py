"""`python -m jarvis.access_governance <cmd>` — 접근 거버넌스·신원 CLI. **감사 전용.**

  operator  --operator-id --name --email [--roles a,b] [--commit]
  role      --role-id --name [--description] [--scope a,b] [--commit]
  session   --operator-id --started-at --expires-at [--commit]
  request   --operator-id --resource --scope [--reason] [--commit]
  approve   --request-id --approver --decision {APPROVE,REJECT} [--reason] [--commit]
  audit [--commit] / verify / summary / replay

실제 권한 부여·permission 변경·operator action 실행 없음 — 신원 거버넌스·접근 감사만.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _p(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _eng():
    from jarvis.access_governance.engine import AccessGovernanceEngine
    return AccessGovernanceEngine()


def _split(s: str) -> list:
    return [x.strip() for x in s.split(",") if x.strip()] if s else []


def _cmd_operator(a) -> int:
    d = _eng().register_operator(a.operator_id, a.name, a.email, _split(a.roles), "ACTIVE",
                                 _now(), commit=a.commit)
    _p({"committed": a.commit, "operator": d.to_dict()})
    return 0


def _cmd_role(a) -> int:
    r = _eng().register_role(a.role_id, a.name, a.description or "", _split(a.scope), _now(),
                             commit=a.commit)
    _p({"committed": a.commit, "role": r.to_dict(), "note": "역할 메타 — 실제 권한 부여 아님"})
    return 0


def _cmd_session(a) -> int:
    s = _eng().create_session(a.operator_id, a.started_at, a.expires_at, {}, _now(),
                              commit=a.commit)
    _p({"committed": a.commit, "session": s.to_dict()})
    return 0


def _cmd_request(a) -> int:
    rid = _eng().request_access(a.operator_id, a.resource, a.scope, a.reason or "", _now(),
                                commit=a.commit)
    _p({"committed": a.commit, "request_id": rid, "note": "접근요청 기록 — 실제 권한 아님"})
    return 0


def _cmd_approve(a) -> int:
    from jarvis.access_governance.models import ApprovalError, IllegalTransition
    try:
        r = _eng().approve_access(a.request_id, a.approver, a.decision, a.reason or "", _now(),
                                  commit=a.commit)
    except (ApprovalError, IllegalTransition) as e:
        _p({"error": str(e)})
        return 1
    _p({"committed": a.commit, "approval": r.to_dict(), "note": "승인 기록만 — 권한 부여 아님"})
    return 0


def _cmd_audit(a) -> int:
    r = _eng().audit_access(_now(), commit=a.commit)
    _p({"committed": a.commit, "audit": r.to_dict()})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.access_governance.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_summary(a) -> int:
    _p(_eng().generate_report(_now()).to_dict())
    return 0


def _cmd_replay(a) -> int:
    from jarvis.access_governance.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.access_governance")
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("operator")
    for f in ("operator-id", "name", "email"):
        o.add_argument(f"--{f}", required=True)
    o.add_argument("--roles", default="")
    o.add_argument("--commit", action="store_true")
    r = sub.add_parser("role")
    r.add_argument("--role-id", required=True)
    r.add_argument("--name", required=True)
    r.add_argument("--description", default="")
    r.add_argument("--scope", default="")
    r.add_argument("--commit", action="store_true")
    s = sub.add_parser("session")
    for f in ("operator-id", "started-at", "expires-at"):
        s.add_argument(f"--{f}", required=True)
    s.add_argument("--commit", action="store_true")
    q = sub.add_parser("request")
    for f in ("operator-id", "resource", "scope"):
        q.add_argument(f"--{f}", required=True)
    q.add_argument("--reason", default="")
    q.add_argument("--commit", action="store_true")
    p = sub.add_parser("approve")
    p.add_argument("--request-id", required=True)
    p.add_argument("--approver", required=True)
    p.add_argument("--decision", required=True, choices=["APPROVE", "REJECT"])
    p.add_argument("--reason", default="")
    p.add_argument("--commit", action="store_true")
    au = sub.add_parser("audit")
    au.add_argument("--commit", action="store_true")
    sub.add_parser("verify")
    sub.add_parser("summary")
    sub.add_parser("replay")
    args = ap.parse_args(argv)
    disp = {"operator": _cmd_operator, "role": _cmd_role, "session": _cmd_session,
            "request": _cmd_request, "approve": _cmd_approve, "audit": _cmd_audit,
            "verify": _cmd_verify, "summary": _cmd_summary, "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
