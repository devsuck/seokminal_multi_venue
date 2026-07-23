"""`python -m jarvis.self_audit_intelligence <cmd>` — 연구 자가 감사 CLI. **READ ONLY 검사·기록 전용.**

  run       [--name --scope --epoch] [--commit]        # create_audit_run
  scan      --run-ref --layer [--commit]               # scan_layer_integrity
  lineage   --run-ref --layer [--commit]               # verify_lineage
  missing   --run-ref [--commit]                       # detect_missing_governance
  drift     --run-ref --layer [--commit]               # detect_policy_drift
  scan-all  --run-ref [--commit]
  report    --run-ref [--commit]                       # generate_audit_report
  replay / verify / summary

실제 원장·정책·config·permission·strategy·model 수정·복구·적용·배포 없음 — 무결성 검사·기록만.
AUDIT ≠ REPAIR · FINDING ≠ FIX · INSPECTION ≠ MODIFICATION · REPORT ≠ ACTION.
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
    from jarvis.self_audit_intelligence.engine import ResearchSelfAuditEngine
    return ResearchSelfAuditEngine()


def _cmd_run(a) -> int:
    r = _eng().create_audit_run(a.name or "ecosystem_integrity", a.scope or "GLOBAL", None,
                                a.epoch or "", _now(), commit=a.commit)
    _p({"committed": a.commit, "run": r.to_dict(), "note": "검사 준비 — 수정 없음"})
    return 0


def _cmd_scan(a) -> int:
    c = _eng().scan_layer_integrity(a.run_ref, a.layer, _now(), commit=a.commit)
    _p({"committed": a.commit, "checks": [x.to_dict() for x in c], "note": "INSPECTION ≠ MODIFICATION"})
    return 0


def _cmd_lineage(a) -> int:
    c = _eng().verify_lineage(a.run_ref, a.layer, _now(), commit=a.commit)
    _p({"committed": a.commit, "check": c.to_dict()})
    return 0


def _cmd_missing(a) -> int:
    c = _eng().detect_missing_governance(a.run_ref, _now(), commit=a.commit)
    _p({"committed": a.commit, "checks": [x.to_dict() for x in c]})
    return 0


def _cmd_drift(a) -> int:
    c = _eng().detect_policy_drift(a.run_ref, a.layer, _now(), commit=a.commit)
    _p({"committed": a.commit, "check": c.to_dict()})
    return 0


def _cmd_scan_all(a) -> int:
    res = _eng().scan_all(a.run_ref, None, _now(), commit=a.commit)
    _p({"committed": a.commit, "scan_all": res})
    return 0


def _cmd_report(a) -> int:
    r = _eng().generate_audit_report(a.run_ref, _now(), commit=a.commit)
    _p({"committed": a.commit, "report": r.to_dict(), "note": "REPORT ≠ ACTION"})
    return 0 if r.overall_result != "CRITICAL" else 1


def _cmd_replay(a) -> int:
    _p(_eng().replay_audit(None))
    return 0


def _cmd_verify(a) -> int:
    from jarvis.self_audit_intelligence.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.self_audit_intelligence")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ru = sub.add_parser("run")
    ru.add_argument("--name", default="ecosystem_integrity")
    ru.add_argument("--scope", default="GLOBAL")
    ru.add_argument("--epoch", default="")
    ru.add_argument("--commit", action="store_true")
    sc = sub.add_parser("scan")
    sc.add_argument("--run-ref", required=True)
    sc.add_argument("--layer", required=True)
    sc.add_argument("--commit", action="store_true")
    li = sub.add_parser("lineage")
    li.add_argument("--run-ref", required=True)
    li.add_argument("--layer", required=True)
    li.add_argument("--commit", action="store_true")
    mi = sub.add_parser("missing")
    mi.add_argument("--run-ref", required=True)
    mi.add_argument("--commit", action="store_true")
    dr = sub.add_parser("drift")
    dr.add_argument("--run-ref", required=True)
    dr.add_argument("--layer", required=True)
    dr.add_argument("--commit", action="store_true")
    sa = sub.add_parser("scan-all")
    sa.add_argument("--run-ref", required=True)
    sa.add_argument("--commit", action="store_true")
    rp = sub.add_parser("report")
    rp.add_argument("--run-ref", required=True)
    rp.add_argument("--commit", action="store_true")
    sub.add_parser("replay")
    sub.add_parser("verify")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"run": _cmd_run, "scan": _cmd_scan, "lineage": _cmd_lineage, "missing": _cmd_missing,
            "drift": _cmd_drift, "scan-all": _cmd_scan_all, "report": _cmd_report,
            "replay": _cmd_replay, "verify": _cmd_verify, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
