"""`python -m jarvis.decision_intelligence <cmd>` — 연구 결정 지원 CLI. **판단 지원 전용.**

  candidate --source-layer --source-reference --research-type [--commit]
  session   --objective --evaluator --candidates c1,c2 [--commit]
  framework --name --version [--weights-json] [--commit]
  evaluate  --session-id --candidate-id --framework-id --scores-json [--commit]
  compare   --session-id --candidate-a --candidate-b [--commit]
  report    --session-id [--commit]        # 결정 스냅샷 생성
  verify / summary / replay

실제 전략선택·배포·자본배분·주문·live trading 없음 — 비교·분석·기록만.
score ≠ approval · RECOMMENDED ≠ DEPLOYABLE · VALIDATED ≠ SELECTED.
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
    from jarvis.decision_intelligence.engine import ResearchDecisionEngine
    return ResearchDecisionEngine()


def _split(s: str) -> list:
    return [x.strip() for x in s.split(",") if x.strip()] if s else []


def _cmd_candidate(a) -> int:
    c = _eng().register_candidate(a.source_layer, a.source_reference, a.research_type, {},
                                  _now(), commit=a.commit)
    _p({"committed": a.commit, "candidate": c.to_dict(), "note": "결정 후보 — 선택/승인 아님"})
    return 0


def _cmd_session(a) -> int:
    s = _eng().create_decision_session(a.objective, a.evaluator, _split(a.candidates), _now(),
                                       commit=a.commit)
    _p({"committed": a.commit, "session": s.to_dict()})
    return 0


def _cmd_framework(a) -> int:
    weights = json.loads(a.weights_json) if a.weights_json else None
    f = _eng().define_framework(a.name, a.version, None, weights, _now(), commit=a.commit)
    _p({"committed": a.commit, "framework": f.to_dict()})
    return 0


def _cmd_evaluate(a) -> int:
    scores = json.loads(a.scores_json)
    sc = _eng().evaluate_candidate(a.session_id, a.candidate_id, a.framework_id, scores, None,
                                   None, _now(), commit=a.commit)
    _p({"committed": a.commit, "scorecard": sc.to_dict(), "note": "score ≠ approval"})
    return 0


def _cmd_compare(a) -> int:
    t = _eng().compare_candidates(a.session_id, a.candidate_a, a.candidate_b, _now(),
                                  commit=a.commit)
    _p({"committed": a.commit, "tradeoff": t.to_dict(), "note": "자동 추천 없음 — 사람 검토"})
    return 0


def _cmd_report(a) -> int:
    r = _eng().create_decision_snapshot(a.session_id, _now(), commit=a.commit)
    _p({"committed": a.commit, "report": r.to_dict()})
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().generate_report(_now()).to_dict())
    return 0


def _cmd_verify(a) -> int:
    from jarvis.decision_intelligence.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.decision_intelligence.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.decision_intelligence")
    sub = ap.add_subparsers(dest="cmd", required=True)
    cd = sub.add_parser("candidate")
    for f in ("source-layer", "source-reference", "research-type"):
        cd.add_argument(f"--{f}", required=True)
    cd.add_argument("--commit", action="store_true")
    se = sub.add_parser("session")
    se.add_argument("--objective", required=True)
    se.add_argument("--evaluator", required=True)
    se.add_argument("--candidates", default="")
    se.add_argument("--commit", action="store_true")
    fw = sub.add_parser("framework")
    fw.add_argument("--name", required=True)
    fw.add_argument("--version", required=True)
    fw.add_argument("--weights-json", default="")
    fw.add_argument("--commit", action="store_true")
    ev = sub.add_parser("evaluate")
    for f in ("session-id", "candidate-id", "framework-id", "scores-json"):
        ev.add_argument(f"--{f}", required=True)
    ev.add_argument("--commit", action="store_true")
    cm = sub.add_parser("compare")
    for f in ("session-id", "candidate-a", "candidate-b"):
        cm.add_argument(f"--{f}", required=True)
    cm.add_argument("--commit", action="store_true")
    rp = sub.add_parser("report")
    rp.add_argument("--session-id", required=True)
    rp.add_argument("--commit", action="store_true")
    sub.add_parser("summary")
    sub.add_parser("verify")
    sub.add_parser("replay")
    args = ap.parse_args(argv)
    disp = {"candidate": _cmd_candidate, "session": _cmd_session, "framework": _cmd_framework,
            "evaluate": _cmd_evaluate, "compare": _cmd_compare, "report": _cmd_report,
            "summary": _cmd_summary, "verify": _cmd_verify, "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
