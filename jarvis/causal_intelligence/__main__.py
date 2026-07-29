"""`python -m jarvis.causal_intelligence <cmd>` — 연구 인과 분석 CLI. **연구 증거·기록 전용.**

  variable   --name --type [--source-ref --node-type] [--commit]
  hypothesis --cause --effect --statement [--mechanism --confidence] [--commit]
  relationship --cause --edge-type --effect [--methodology --result] [--commit]
  experiment --hypothesis-id --method [--inputs-json] [--run] [--commit]
  evidence   --experiment-id --metric --value [--interpretation --confidence] [--commit]
  graph      --name [--commit]
  lineage                                # 그래프 순환·고아 검사
  report     --hypothesis-id [--metrics-json] [--commit]
  verify / replay / summary

실제 실행·거래·배포·자본배분·signal 생성 없음 — 연구 증거·기록만.
CAUSAL SCORE ≠ TRADING PERMISSION · RELATIONSHIP ≠ ACTION. BUY/SELL/DEPLOY/ENABLE/ALLOCATE 아님.
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
    from jarvis.causal_intelligence.engine import ResearchCausalEngine
    return ResearchCausalEngine()


def _cmd_variable(a) -> int:
    v = _eng().register_variable(a.name, a.type, a.source_ref or "", a.node_type or "VARIABLE",
                                 {}, _now(), commit=a.commit)
    _p({"committed": a.commit, "variable": v.to_dict(), "note": "연구 변수 — 실행 아님"})
    return 0


def _cmd_hypothesis(a) -> int:
    h = _eng().create_hypothesis(a.cause, a.effect, a.statement, a.mechanism or "",
                                 a.confidence, _now(), commit=a.commit)
    _p({"committed": a.commit, "hypothesis": h.to_dict(), "note": "가설 — CAUSALITY PROVEN 아님"})
    return 0


def _cmd_relationship(a) -> int:
    r = _eng().record_relationship(a.cause, a.edge_type, a.effect, a.methodology or "", "", "",
                                   None, a.result or "", _now(), commit=a.commit)
    _p({"committed": a.commit, "relationship": r.to_dict(), "note": "RELATIONSHIP ≠ ACTION"})
    return 0


def _cmd_experiment(a) -> int:
    eng = _eng()
    inputs = json.loads(a.inputs_json) if a.inputs_json else {}
    x = eng.create_experiment(a.hypothesis_id, a.method, inputs, None, _now(), commit=a.commit)
    if a.run:
        eng.run_experiment(x.experiment_id, _now(), commit=a.commit)
    _p({"committed": a.commit, "experiment": x.to_dict(),
        "note": "intervention_simulation 은 기록만 — 실제 개입 없음"})
    return 0


def _cmd_evidence(a) -> int:
    e = _eng().record_evidence(a.experiment_id, a.metric, a.value, a.interpretation or "",
                               a.confidence, _now(), commit=a.commit)
    _p({"committed": a.commit, "evidence": e.to_dict(), "note": "서술적 증거 — 자동 판단 아님"})
    return 0


def _cmd_graph(a) -> int:
    eng = _eng()
    g = eng.snapshot_graph(a.name, _now(), commit=a.commit)
    _p({"committed": a.commit, "graph": g.to_dict(), "cycle": eng.graph_cycle()})
    return 0


def _cmd_lineage(a) -> int:
    from jarvis.causal_intelligence.verify import graph_validation, lineage_validation
    _p({"graph": graph_validation(), "lineage": lineage_validation(),
        "orphans": _eng().orphan_variables()})
    return 0


def _cmd_report(a) -> int:
    metrics = json.loads(a.metrics_json) if a.metrics_json else {}
    r = _eng().generate_report(a.hypothesis_id, metrics, _now(), commit=a.commit)
    _p({"committed": a.commit, "report": r.to_dict(),
        "note": "CAUSAL SCORE ≠ TRADING PERMISSION"})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.causal_intelligence.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.causal_intelligence.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.causal_intelligence")
    sub = ap.add_subparsers(dest="cmd", required=True)
    va = sub.add_parser("variable")
    va.add_argument("--name", required=True)
    va.add_argument("--type", required=True)
    va.add_argument("--source-ref", default="")
    va.add_argument("--node-type", default="VARIABLE")
    va.add_argument("--commit", action="store_true")
    hy = sub.add_parser("hypothesis")
    for f in ("cause", "effect", "statement"):
        hy.add_argument(f"--{f}", required=True)
    hy.add_argument("--mechanism", default="")
    hy.add_argument("--confidence", type=float, default=0.0)
    hy.add_argument("--commit", action="store_true")
    rl = sub.add_parser("relationship")
    rl.add_argument("--cause", required=True)
    rl.add_argument("--edge-type", required=True)
    rl.add_argument("--effect", required=True)
    rl.add_argument("--methodology", default="")
    rl.add_argument("--result", default="")
    rl.add_argument("--commit", action="store_true")
    ex = sub.add_parser("experiment")
    ex.add_argument("--hypothesis-id", required=True)
    ex.add_argument("--method", required=True)
    ex.add_argument("--inputs-json", default="")
    ex.add_argument("--run", action="store_true")
    ex.add_argument("--commit", action="store_true")
    ev = sub.add_parser("evidence")
    ev.add_argument("--experiment-id", required=True)
    ev.add_argument("--metric", required=True)
    ev.add_argument("--value", type=float, required=True)
    ev.add_argument("--interpretation", default="")
    ev.add_argument("--confidence", type=float, default=0.0)
    ev.add_argument("--commit", action="store_true")
    gr = sub.add_parser("graph")
    gr.add_argument("--name", required=True)
    gr.add_argument("--commit", action="store_true")
    sub.add_parser("lineage")
    rp = sub.add_parser("report")
    rp.add_argument("--hypothesis-id", required=True)
    rp.add_argument("--metrics-json", default="")
    rp.add_argument("--commit", action="store_true")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"variable": _cmd_variable, "hypothesis": _cmd_hypothesis,
            "relationship": _cmd_relationship, "experiment": _cmd_experiment,
            "evidence": _cmd_evidence, "graph": _cmd_graph, "lineage": _cmd_lineage,
            "report": _cmd_report, "verify": _cmd_verify, "replay": _cmd_replay,
            "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
