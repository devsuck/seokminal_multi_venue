"""`python -m jarvis.research_compliance <cmd>` — 연구 컴플라이언스·무결성 거버넌스 CLI. **관찰·기록 전용.**

  rule       --category --description [--severity --version] [--commit]
  evidence   --source --artifact-reference [--checksum --epoch] [--commit]
  check      --rule-id --source [--result --evidence-reference] [--commit]
  review     --reviewer --target --decision [--notes] [--commit]
  violation  --category --source [--severity] [--commit]
  report     [--metrics-json] [--commit]
  verify / replay / summary

실제 위반 자동수정·연구 산출물 수정·배포 승인·permission 변경·실행 없음 — 컴플라이언스 관찰·기록만.
COMPLIANCE CHECK ≠ APPROVAL · VIOLATION DETECTION ≠ CORRECTION · RECOMMENDATION ≠ ACTION · AUDIT RESULT ≠ DEPLOYMENT PERMISSION.
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
    from jarvis.research_compliance.engine import ResearchComplianceEngine
    return ResearchComplianceEngine()


def _cmd_rule(a) -> int:
    r = _eng().register_rule(a.category, a.description, a.severity or "MEDIUM", a.version or "1.0",
                             {}, _now(), commit=a.commit)
    _p({"committed": a.commit, "rule": r.to_dict(), "note": "규칙 등록 — 불변"})
    return 0


def _cmd_evidence(a) -> int:
    e = _eng().register_evidence(a.source, a.artifact_reference, None, a.checksum or "",
                                 a.epoch or "", _now(), commit=a.commit)
    _p({"committed": a.commit, "evidence": e.to_dict(), "note": "증거 기록 — 불변"})
    return 0


def _cmd_check(a) -> int:
    c = _eng().run_check(a.rule_id, a.source, a.result, a.evidence_reference or "", {}, _now(),
                         commit=a.commit)
    _p({"committed": a.commit, "check": c.to_dict(), "note": "COMPLIANCE CHECK ≠ APPROVAL"})
    return 0


def _cmd_review(a) -> int:
    rv = _eng().create_review(a.reviewer, a.target, a.decision, a.notes or "", _now(),
                              commit=a.commit)
    _p({"committed": a.commit, "review": rv.to_dict(), "note": "검토 기록 — 자동 승인/배포 아님"})
    return 0


def _cmd_violation(a) -> int:
    v = _eng().record_violation(a.category, a.source, a.severity or "MEDIUM", [], _now(),
                                commit=a.commit)
    _p({"committed": a.commit, "violation": v.to_dict(), "note": "탐지 기록 — 자동 시정 없음"})
    return 0


def _cmd_report(a) -> int:
    metrics = json.loads(a.metrics_json) if a.metrics_json else {}
    r = _eng().generate_report("GLOBAL", metrics, _now(), commit=a.commit)
    _p({"committed": a.commit, "report": r.to_dict()})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_compliance.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_compliance.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_compliance")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ru = sub.add_parser("rule")
    ru.add_argument("--category", required=True)
    ru.add_argument("--description", required=True)
    ru.add_argument("--severity", default="MEDIUM")
    ru.add_argument("--version", default="1.0")
    ru.add_argument("--commit", action="store_true")
    ev = sub.add_parser("evidence")
    ev.add_argument("--source", required=True)
    ev.add_argument("--artifact-reference", required=True)
    ev.add_argument("--checksum", default="")
    ev.add_argument("--epoch", default="")
    ev.add_argument("--commit", action="store_true")
    ck = sub.add_parser("check")
    ck.add_argument("--rule-id", required=True)
    ck.add_argument("--source", required=True)
    ck.add_argument("--result", default="PASS")
    ck.add_argument("--evidence-reference", default="")
    ck.add_argument("--commit", action="store_true")
    rv = sub.add_parser("review")
    rv.add_argument("--reviewer", required=True)
    rv.add_argument("--target", required=True)
    rv.add_argument("--decision", required=True)
    rv.add_argument("--notes", default="")
    rv.add_argument("--commit", action="store_true")
    vi = sub.add_parser("violation")
    vi.add_argument("--category", required=True)
    vi.add_argument("--source", required=True)
    vi.add_argument("--severity", default="MEDIUM")
    vi.add_argument("--commit", action="store_true")
    rp = sub.add_parser("report")
    rp.add_argument("--metrics-json", default="")
    rp.add_argument("--commit", action="store_true")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"rule": _cmd_rule, "evidence": _cmd_evidence, "check": _cmd_check,
            "review": _cmd_review, "violation": _cmd_violation, "report": _cmd_report,
            "verify": _cmd_verify, "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
