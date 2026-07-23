"""`python -m jarvis.research_evolution <cmd>` — 연구 진화 거버넌스 CLI. **저장·분석·기록 전용.**

  object    --source-layer --source-reference --research-type [--commit]
  failure   --category --pattern [--severity --frequency] [--commit]
  cycle     --name [--sources s1,s2 --lessons l1,l2 --questions q1,q2] [--commit]
  iteration --cycle-ref --number [--outcome --notes] [--commit]
  proposal  --source-failure --hypothesis [--expected] [--commit]
  learning  --source --lesson [--confidence --applicability] [--commit]
  transfer  --from-context --to-context --knowledge [--applicability] [--commit]
  report    [--metrics-json] [--commit]
  verify / replay / summary

실제 실행·거래·배포·strategy/model/parameter 수정·config 변경·자본 배분 없음 — 학습 기록 저장·분석만.
LEARNING ≠ MODIFICATION · PROPOSAL ≠ APPROVAL · ACCEPTED ≠ DEPLOYMENT · IMPLEMENTED(record) ≠ PRODUCTION CHANGE.
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
    from jarvis.research_evolution.engine import ResearchEvolutionEngine
    return ResearchEvolutionEngine()


def _split(s: str) -> list:
    return [x.strip() for x in s.split(",") if x.strip()] if s else []


def _cmd_object(a) -> int:
    o = _eng().register_research_object(a.source_layer, a.source_reference, a.research_type,
                                        {}, _now(), commit=a.commit)
    _p({"committed": a.commit, "object": o.to_dict(), "note": "학습 대상 등록 — 원본 수정 아님"})
    return 0


def _cmd_failure(a) -> int:
    f = _eng().record_failure(a.category, a.pattern, a.severity or "MEDIUM", [], [],
                              a.frequency or 1, _now(), commit=a.commit)
    _p({"committed": a.commit, "failure": f.to_dict(), "note": "실패 패턴 분석·기록만"})
    return 0


def _cmd_cycle(a) -> int:
    c = _eng().create_evolution_cycle(a.name, _split(a.sources), [], _split(a.lessons),
                                      _split(a.questions), _now(), commit=a.commit)
    _p({"committed": a.commit, "cycle": c.to_dict(), "note": "진화 사이클 — LEARNING ≠ MODIFICATION"})
    return 0


def _cmd_iteration(a) -> int:
    it = _eng().record_iteration(a.cycle_ref, a.number, [], a.outcome or "INCONCLUSIVE",
                                 a.notes or "", _now(), commit=a.commit)
    _p({"committed": a.commit, "iteration": it.to_dict()})
    return 0


def _cmd_proposal(a) -> int:
    p = _eng().create_improvement_proposal(a.source_failure, a.hypothesis, a.expected or "", [],
                                           _now(), commit=a.commit)
    _p({"committed": a.commit, "proposal": p.to_dict(), "note": "PROPOSAL ≠ APPROVAL — 자동 적용 없음"})
    return 0


def _cmd_learning(a) -> int:
    l = _eng().create_learning_record(a.source, a.lesson, a.confidence or 0.0,
                                      a.applicability or "MODERATE", [], _now(), commit=a.commit)
    _p({"committed": a.commit, "learning": l.to_dict(), "note": "학습 기록 — LEARNING ≠ MODIFICATION"})
    return 0


def _cmd_transfer(a) -> int:
    t = _eng().create_transfer_record(a.from_context, a.to_context, a.knowledge,
                                      a.applicability or "MODERATE", [], _now(), commit=a.commit)
    _p({"committed": a.commit, "transfer": t.to_dict(), "note": "지식 이전 제안·기록만"})
    return 0


def _cmd_report(a) -> int:
    metrics = json.loads(a.metrics_json) if a.metrics_json else {}
    r = _eng().generate_report("GLOBAL", metrics, _now(), commit=a.commit)
    _p({"committed": a.commit, "report": r.to_dict()})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_evolution.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_evolution.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_evolution")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ob = sub.add_parser("object")
    ob.add_argument("--source-layer", required=True)
    ob.add_argument("--source-reference", required=True)
    ob.add_argument("--research-type", required=True)
    ob.add_argument("--commit", action="store_true")
    fa = sub.add_parser("failure")
    fa.add_argument("--category", required=True)
    fa.add_argument("--pattern", required=True)
    fa.add_argument("--severity", default="MEDIUM")
    fa.add_argument("--frequency", type=int, default=1)
    fa.add_argument("--commit", action="store_true")
    cy = sub.add_parser("cycle")
    cy.add_argument("--name", required=True)
    cy.add_argument("--sources", default="")
    cy.add_argument("--lessons", default="")
    cy.add_argument("--questions", default="")
    cy.add_argument("--commit", action="store_true")
    it = sub.add_parser("iteration")
    it.add_argument("--cycle-ref", required=True)
    it.add_argument("--number", type=int, required=True)
    it.add_argument("--outcome", default="INCONCLUSIVE")
    it.add_argument("--notes", default="")
    it.add_argument("--commit", action="store_true")
    pr = sub.add_parser("proposal")
    pr.add_argument("--source-failure", required=True)
    pr.add_argument("--hypothesis", required=True)
    pr.add_argument("--expected", default="")
    pr.add_argument("--commit", action="store_true")
    le = sub.add_parser("learning")
    le.add_argument("--source", required=True)
    le.add_argument("--lesson", required=True)
    le.add_argument("--confidence", type=float, default=0.0)
    le.add_argument("--applicability", default="MODERATE")
    le.add_argument("--commit", action="store_true")
    tr = sub.add_parser("transfer")
    tr.add_argument("--from-context", required=True)
    tr.add_argument("--to-context", required=True)
    tr.add_argument("--knowledge", required=True)
    tr.add_argument("--applicability", default="MODERATE")
    tr.add_argument("--commit", action="store_true")
    rp = sub.add_parser("report")
    rp.add_argument("--metrics-json", default="")
    rp.add_argument("--commit", action="store_true")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"object": _cmd_object, "failure": _cmd_failure, "cycle": _cmd_cycle,
            "iteration": _cmd_iteration, "proposal": _cmd_proposal, "learning": _cmd_learning,
            "transfer": _cmd_transfer, "report": _cmd_report, "verify": _cmd_verify,
            "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
