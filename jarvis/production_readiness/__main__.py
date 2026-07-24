"""`python -m jarvis.production_readiness <cmd>` — 배포 준비성 거버넌스 CLI. **검증·승인 기록·감사 전용.**

  candidate   --layer --ref [--strategy --model --portfolio]  후보 등록(REGISTERED) [--commit]
  check       --candidate --category --status --evidence       준비성 체크(증거 필수) [--commit]
  requirement --candidate --type --target --actual --met       요구사항 평가 [--commit]
  review      --candidate --subject [--reviewer --decision]     리뷰 요청/결정(검토자 필수) [--commit]
  risk        --candidate --level [--detail]                    전환 리스크 평가 [--commit]
  transition  --candidate --to                                 상태 전이(검증) [--commit]
  report --candidate / candidates / verify / summary / replay

실제 주문·live trading·자동 배포·자동 승인 없음. VALIDATED ≠ DEPLOYED · READY ≠ LIVE.
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
    from jarvis.production_readiness.engine import ProductionReadinessEngine
    return ProductionReadinessEngine()


def _cmd_candidate(a) -> int:
    _p({"committed": a.commit,
        "candidate": _eng().register_candidate(a.layer, a.ref, a.strategy or "", a.model or "",
                                              a.portfolio or "", {}, _now(),
                                              commit=a.commit).to_dict()})
    return 0


def _cmd_check(a) -> int:
    _p({"committed": a.commit,
        "check": _eng().create_readiness_check(a.candidate, a.category, a.status, [a.evidence], "",
                                             _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_requirement(a) -> int:
    _p({"committed": a.commit,
        "requirement": _eng().evaluate_requirements(a.candidate, a.type, a.target, a.actual, a.met,
                                                  "", _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_review(a) -> int:
    eng = _eng()
    if a.decision:
        from jarvis.production_readiness.models import review_id
        rev = review_id(a.candidate, a.subject)
        _p({"committed": a.commit,
            "review": eng.record_review(rev, a.reviewer or "", a.decision, "", _now(),
                                       commit=a.commit).to_dict(),
            "note": "reviewer required · no auto approval"})
    else:
        _p({"committed": a.commit,
            "review": eng.request_review(a.candidate, a.subject, _now(),
                                        commit=a.commit).to_dict()})
    return 0


def _cmd_risk(a) -> int:
    _p({"committed": a.commit,
        "risk": _eng().assess_transition_risk(a.candidate, a.level, [], a.detail or "", _now(),
                                            commit=a.commit).to_dict()})
    return 0


def _cmd_transition(a) -> int:
    _p({"committed": a.commit,
        "transition": _eng().create_transition_record(a.candidate, a.to, "", _now(),
                                                     commit=a.commit).to_dict(),
        "note": "READY_FOR_DEPLOYMENT ≠ DEPLOYED"})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_readiness_report(a.candidate, "CANDIDATE", _now(),
                                                  commit=a.commit).to_dict(),
        "note": "deployed=False · is_binding=False"})
    return 0


def _cmd_candidates(a) -> int:
    eng = _eng()
    _p({"candidates": [{"candidate_id": c, "state": eng.candidate_state(c)}
                       for c in eng.list_candidates()]})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.production_readiness.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.production_readiness.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.production_readiness")
    sub = ap.add_subparsers(dest="cmd", required=True)

    cd = sub.add_parser("candidate")
    cd.add_argument("--layer", required=True)
    cd.add_argument("--ref", required=True)
    cd.add_argument("--strategy", default="")
    cd.add_argument("--model", default="")
    cd.add_argument("--portfolio", default="")
    cd.add_argument("--commit", action="store_true")

    ck = sub.add_parser("check")
    ck.add_argument("--candidate", required=True)
    ck.add_argument("--category", required=True)
    ck.add_argument("--status", required=True)
    ck.add_argument("--evidence", required=True)
    ck.add_argument("--commit", action="store_true")

    rq = sub.add_parser("requirement")
    rq.add_argument("--candidate", required=True)
    rq.add_argument("--type", required=True)
    rq.add_argument("--target", default="")
    rq.add_argument("--actual", default="")
    rq.add_argument("--met", action="store_true")
    rq.add_argument("--commit", action="store_true")

    rv = sub.add_parser("review")
    rv.add_argument("--candidate", required=True)
    rv.add_argument("--subject", required=True)
    rv.add_argument("--reviewer", default="")
    rv.add_argument("--decision", default="")
    rv.add_argument("--commit", action="store_true")

    rk = sub.add_parser("risk")
    rk.add_argument("--candidate", required=True)
    rk.add_argument("--level", required=True)
    rk.add_argument("--detail", default="")
    rk.add_argument("--commit", action="store_true")

    tr = sub.add_parser("transition")
    tr.add_argument("--candidate", required=True)
    tr.add_argument("--to", required=True)
    tr.add_argument("--commit", action="store_true")

    rp = sub.add_parser("report")
    rp.add_argument("--candidate", required=True)
    rp.add_argument("--commit", action="store_true")

    sub.add_parser("candidates")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")

    args = ap.parse_args(argv)
    disp = {"candidate": _cmd_candidate, "check": _cmd_check, "requirement": _cmd_requirement,
            "review": _cmd_review, "risk": _cmd_risk, "transition": _cmd_transition,
            "report": _cmd_report, "candidates": _cmd_candidates, "verify": _cmd_verify,
            "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
