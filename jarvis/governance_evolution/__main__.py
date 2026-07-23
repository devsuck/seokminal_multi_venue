"""`python -m jarvis.governance_evolution <cmd>` — 거버넌스 진화 인텔리전스 CLI. **분석·기록 전용.**

  event    --source-layer --event-type --description [--commit]
  state    --layer-reference --maturity-level [--capabilities c1,c2] [--commit]
  maturity --layer-reference [--scores-json --evidence --epoch] [--commit]
  pattern  --sequence t1,t2 [--frequency] [--commit]
  compare  --previous-state --current-state [--commit]
  snapshot --name [--epoch --states s1,s2 --summary-json] [--commit]
  report   [--metrics-json] [--commit]
  verify / replay / summary

실제 거버넌스 규칙 수정·업그레이드 승인·config 변경·배포·실행 없음 — 진화 분석·기록만.
EVOLUTION ANALYSIS ≠ EVOLUTION ACTION · MATURITY SCORE ≠ PERMISSION · TREND DETECTION ≠ CHANGE EXECUTION.
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
    from jarvis.governance_evolution.engine import GovernanceEvolutionEngine
    return GovernanceEvolutionEngine()


def _split(s: str) -> list:
    return [x.strip() for x in s.split(",") if x.strip()] if s else []


def _cmd_event(a) -> int:
    e = _eng().record_event(a.source_layer, a.event_type, a.description, _now(), commit=a.commit)
    _p({"committed": a.commit, "event": e.to_dict(), "note": "진화 이벤트 기록 — 불변"})
    return 0


def _cmd_state(a) -> int:
    s = _eng().create_state(a.layer_reference, a.maturity_level, _split(a.capabilities), _now(),
                            commit=a.commit)
    _p({"committed": a.commit, "state": s.to_dict(), "note": "타임라인 — MATURITY SCORE ≠ PERMISSION"})
    return 0


def _cmd_maturity(a) -> int:
    scores = json.loads(a.scores_json) if a.scores_json else {}
    m = _eng().assess_maturity(a.layer_reference, scores, a.evidence or "", a.epoch or "", _now(),
                               commit=a.commit)
    _p({"committed": a.commit, "maturity": m.to_dict(), "note": "성숙도 평가 — 불변"})
    return 0


def _cmd_pattern(a) -> int:
    freq = a.frequency if a.frequency is not None else None
    p = _eng().analyze_pattern(_split(a.sequence), freq, _now(), commit=a.commit)
    _p({"committed": a.commit, "pattern": p.to_dict(), "note": "PATTERN ≠ ACTION — 분석 전용"})
    return 0


def _cmd_compare(a) -> int:
    c = _eng().compare_states(a.previous_state, a.current_state, _now(), commit=a.commit)
    _p({"committed": a.commit, "comparison": c.to_dict(), "note": "서술적 비교 — 자동 조치 없음"})
    return 0


def _cmd_snapshot(a) -> int:
    summary = json.loads(a.summary_json) if a.summary_json else {}
    s = _eng().create_snapshot(a.name, a.epoch or "", _split(a.states), summary, _now(),
                               commit=a.commit)
    _p({"committed": a.commit, "snapshot": s.to_dict(), "note": "결정적 스냅샷"})
    return 0


def _cmd_report(a) -> int:
    metrics = json.loads(a.metrics_json) if a.metrics_json else {}
    r = _eng().generate_report("GLOBAL", metrics, _now(), commit=a.commit)
    _p({"committed": a.commit, "report": r.to_dict()})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.governance_evolution.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.governance_evolution.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.governance_evolution")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ev = sub.add_parser("event")
    ev.add_argument("--source-layer", required=True)
    ev.add_argument("--event-type", required=True)
    ev.add_argument("--description", required=True)
    ev.add_argument("--commit", action="store_true")
    st = sub.add_parser("state")
    st.add_argument("--layer-reference", required=True)
    st.add_argument("--maturity-level", required=True)
    st.add_argument("--capabilities", default="")
    st.add_argument("--commit", action="store_true")
    ma = sub.add_parser("maturity")
    ma.add_argument("--layer-reference", required=True)
    ma.add_argument("--scores-json", default="")
    ma.add_argument("--evidence", default="")
    ma.add_argument("--epoch", default="")
    ma.add_argument("--commit", action="store_true")
    pt = sub.add_parser("pattern")
    pt.add_argument("--sequence", required=True)
    pt.add_argument("--frequency", type=int, default=None)
    pt.add_argument("--commit", action="store_true")
    cp = sub.add_parser("compare")
    cp.add_argument("--previous-state", required=True)
    cp.add_argument("--current-state", required=True)
    cp.add_argument("--commit", action="store_true")
    sn = sub.add_parser("snapshot")
    sn.add_argument("--name", required=True)
    sn.add_argument("--epoch", default="")
    sn.add_argument("--states", default="")
    sn.add_argument("--summary-json", default="")
    sn.add_argument("--commit", action="store_true")
    rp = sub.add_parser("report")
    rp.add_argument("--metrics-json", default="")
    rp.add_argument("--commit", action="store_true")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"event": _cmd_event, "state": _cmd_state, "maturity": _cmd_maturity,
            "pattern": _cmd_pattern, "compare": _cmd_compare, "snapshot": _cmd_snapshot,
            "report": _cmd_report, "verify": _cmd_verify, "replay": _cmd_replay,
            "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
