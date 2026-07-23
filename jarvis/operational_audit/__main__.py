"""`python -m jarvis.operational_audit <cmd>` — 운영 감사·컴플라이언스 CLI. **감사 전용.**

  audit [--commit]   P9.1~P9.5 원장 감사 → ComplianceReport(--commit 기록)
  summary            최신 컴플라이언스·감사 원장 건수 요약
  verify             자체 감사 원장 해시체인·변조·중복 검증
  replay             동일 입력 재감사(결정성 확인)

읽기전용 감사 — 집행/주문/브로커/킬스위치/복구실행/권한변경 없음. 운영 제어권 없음.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cmd_audit(commit: bool) -> int:
    from jarvis.operational_audit.engine import OperationalAuditEngine
    res = OperationalAuditEngine().audit(_now(), commit=commit)
    out = res["report"].to_dict()
    out["note"] = "감사 전용 — 운영 제어권 없음·집행/주문/브로커/킬스위치/복구실행 없음"
    print(json.dumps({"committed": commit, "report": out,
                      "n_events": len(res["events"]), "n_findings": len(res["findings"])},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_summary() -> int:
    from jarvis.operational_audit import ledger
    last = ledger.compliance_reports_head()
    print(json.dumps({
        "latest_compliance_score": last.get("compliance_score") if last else None,
        "latest_chain_status": last.get("chain_status") if last else None,
        "audit_events": len(ledger.read_audit_events()),
        "operator_actions": len(ledger.read_operator_actions()),
        "configuration_snapshots": len(ledger.read_config_snapshots()),
        "compliance_reports": len(ledger.read_compliance_reports()),
    }, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_verify() -> int:
    from jarvis.operational_audit.verify import verify_chain
    res = verify_chain()
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    return 0 if res["ok"] else 1


def _cmd_replay() -> int:
    from jarvis.operational_audit.engine import OperationalAuditEngine
    from jarvis.operational_audit.verify import replay
    print(json.dumps(replay(OperationalAuditEngine(), _now()),
                     ensure_ascii=False, indent=2, default=str))
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="jarvis.operational_audit")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("audit")
    a.add_argument("--commit", action="store_true")
    sub.add_parser("summary")
    sub.add_parser("verify")
    sub.add_parser("replay")
    args = ap.parse_args(argv)
    return {"audit": lambda: _cmd_audit(args.commit), "summary": _cmd_summary,
            "verify": _cmd_verify, "replay": _cmd_replay}[args.cmd]()


if __name__ == "__main__":
    raise SystemExit(main())
