"""`python -m jarvis.operations <cmd>` — 관제(Alerting & Incident) CLI. **관제 전용.**

  check [--commit]   최신 P9.1 헬스 리포트 관측 → alert/incident/escalation 산출(--commit 기록)
  status             5개 관제 원장 요약(건수·최근 상태)
  verify             전 원장 해시체인·변조·중복 검증
  replay             동일 입력 재처리(결정성 확인)
  summary            severity/incident 상태 분포 집계

읽기전용 — 주문/집행/브로커/킬스위치/상태변경 없음. 거래를 승인하지 않음.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cmd_check(commit: bool) -> int:
    from jarvis.operations.engine import OperationsEngine
    res = OperationsEngine().process(None, _now(), commit=commit)
    res["note"] = "관제 관측만 — 거래 승인 아님·집행/주문/브로커/킬스위치 없음"
    print(json.dumps({"committed": commit, "result": res},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_status() -> int:
    from jarvis.operations import ledger
    from jarvis.operations.models import fold_incident_state
    inc_states: dict = {}
    inc_ids = {r["incident_id"] for r in ledger.read_incidents()}
    for inc_id in inc_ids:
        st = fold_incident_state(ledger.incident_events(inc_id))
        inc_states[st] = inc_states.get(st, 0) + 1
    sev_dist: dict = {}
    for a in ledger.read_alerts():
        sev_dist[a.get("severity")] = sev_dist.get(a.get("severity"), 0) + 1
    print(json.dumps({
        "alerts": len(ledger.read_alerts()),
        "alert_severity_distribution": dict(sorted(sev_dist.items())),
        "incidents": len(inc_ids),
        "incident_state_distribution": dict(sorted(inc_states.items())),
        "escalations": len(ledger.read_escalations()),
        "acknowledgements": len(ledger.read_acks()),
        "resolutions": len(ledger.read_resolutions()),
    }, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_verify() -> int:
    from jarvis.operations.verify import verify_chain
    res = verify_chain()
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    return 0 if res["ok"] else 1


def _cmd_replay() -> int:
    from jarvis.operations.engine import OperationsEngine
    eng = OperationsEngine()
    report = eng._latest_report()
    from jarvis.operations.verify import replay
    print(json.dumps(replay(eng, report, _now()),
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_summary() -> int:
    from jarvis.operations import ledger
    from jarvis.operations.models import fold_incident_state
    open_incidents = []
    for inc_id in {r["incident_id"] for r in ledger.read_incidents()}:
        evs = ledger.incident_events(inc_id)
        st = fold_incident_state(evs)
        if st in ("OPEN", "ACKNOWLEDGED", "MITIGATING"):
            open_incidents.append({"incident_id": inc_id, "state": st,
                                   "alert_key": evs[-1].get("alert_key"),
                                   "severity": evs[-1].get("severity")})
    print(json.dumps({"open_incidents": sorted(open_incidents, key=lambda x: x["incident_id"]),
                      "n_open": len(open_incidents)},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="jarvis.operations")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--commit", action="store_true")
    sub.add_parser("status")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    return {"check": lambda: _cmd_check(args.commit), "status": _cmd_status,
            "verify": _cmd_verify, "replay": _cmd_replay, "summary": _cmd_summary}[args.cmd]()


if __name__ == "__main__":
    raise SystemExit(main())
