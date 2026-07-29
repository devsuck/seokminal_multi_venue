"""`python -m jarvis.research_reliability <cmd>` — 연구 신뢰성 엔지니어링 CLI. **기록 전용.**

  incident    --source --category --desc [--severity]      장애 기록(genesis OPEN) [--commit]
  plan        --incident --steps --owner                   복구 계획(자동 실행 없음) [--commit]
  event       --incident --action [--result --detail]      복구 시도 기록 [--commit]
  integrity   --layer --type [--result]                    무결성 검사 [--commit]
  metrics     신뢰성 지표 산출(관찰만) [--commit]
  postmortem  --incident --root --impact --lesson          포스트모템 기록(DRAFT) [--commit]
  report [--scope] / verify / summary / replay

거래 시스템 재시작·프로덕션 수정·자동 배포·권한 변경·전략 실행·모델 자동 수정 없음. RECORD ≠ REPAIR · INCIDENT ≠ EXECUTION.
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
    from jarvis.research_reliability.engine import ResearchReliabilityEngine
    return ResearchReliabilityEngine()


def _cmd_incident(a) -> int:
    _p({"committed": a.commit,
        "incident": _eng().register_incident(a.source, a.category, a.desc, a.severity or "MEDIUM",
                                             _now(), commit=a.commit).to_dict(),
        "note": "RECORD ≠ REPAIR"})
    return 0


def _cmd_plan(a) -> int:
    steps = [s for s in (a.steps or "").split("|") if s]
    _p({"committed": a.commit,
        "plan": _eng().create_recovery_plan(a.incident, steps, a.owner, _now(),
                                           commit=a.commit).to_dict(),
        "note": "auto_execute=False"})
    return 0


def _cmd_event(a) -> int:
    _p({"committed": a.commit,
        "recovery_event": _eng().record_recovery_event(a.incident, a.action, a.result or "RECORDED",
                                                       a.detail or "", _now(),
                                                       commit=a.commit).to_dict()})
    return 0


def _cmd_integrity(a) -> int:
    _p({"committed": a.commit,
        "integrity_check": _eng().run_integrity_check(a.layer, a.type, a.result or "PASS", {},
                                                     _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_metrics(a) -> int:
    _p({"committed": a.commit, "reliability_metrics": _eng().calculate_reliability_metrics(
        _now(), commit=a.commit), "note": "is_observation=True · no automated decision"})
    return 0


def _cmd_postmortem(a) -> int:
    _p({"committed": a.commit,
        "postmortem": _eng().create_postmortem(a.incident, a.root, a.impact, a.lesson, _now(),
                                              commit=a.commit).to_dict(),
        "note": "human review required for RECORDED"})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_report(a.scope or "SYSTEM", _now(), commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_reliability.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def _cmd_replay(a) -> int:
    from jarvis.research_reliability.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_reliability")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ic = sub.add_parser("incident")
    ic.add_argument("--source", required=True)
    ic.add_argument("--category", required=True)
    ic.add_argument("--desc", required=True)
    ic.add_argument("--severity", default="MEDIUM")
    ic.add_argument("--commit", action="store_true")

    pl = sub.add_parser("plan")
    pl.add_argument("--incident", required=True)
    pl.add_argument("--steps", default="")
    pl.add_argument("--owner", required=True)
    pl.add_argument("--commit", action="store_true")

    ev = sub.add_parser("event")
    ev.add_argument("--incident", required=True)
    ev.add_argument("--action", required=True)
    ev.add_argument("--result", default="RECORDED")
    ev.add_argument("--detail", default="")
    ev.add_argument("--commit", action="store_true")

    it = sub.add_parser("integrity")
    it.add_argument("--layer", required=True)
    it.add_argument("--type", required=True)
    it.add_argument("--result", default="PASS")
    it.add_argument("--commit", action="store_true")

    mt = sub.add_parser("metrics")
    mt.add_argument("--commit", action="store_true")

    pm = sub.add_parser("postmortem")
    pm.add_argument("--incident", required=True)
    pm.add_argument("--root", required=True)
    pm.add_argument("--impact", required=True)
    pm.add_argument("--lesson", required=True)
    pm.add_argument("--commit", action="store_true")

    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="SYSTEM")
    rp.add_argument("--commit", action="store_true")

    sub.add_parser("verify")
    sub.add_parser("summary")
    sub.add_parser("replay")

    args = ap.parse_args(argv)
    disp = {"incident": _cmd_incident, "plan": _cmd_plan, "event": _cmd_event,
            "integrity": _cmd_integrity, "metrics": _cmd_metrics, "postmortem": _cmd_postmortem,
            "report": _cmd_report, "verify": _cmd_verify, "summary": _cmd_summary,
            "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
