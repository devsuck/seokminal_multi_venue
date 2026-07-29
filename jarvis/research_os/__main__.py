"""`python -m jarvis.research_os <cmd>` — 연구 OS 오케스트레이션 CLI. **관찰·조직·기록 전용.**

  layer     --name [--version --prefix --activate] [--commit]
  workflow  --name [--nodes n1,n2] [--commit]
  event     --layer --event-type --reference-id [--commit]
  snapshot  --name [--epoch --metrics-json] [--commit]
  health    [--snapshot-ref --metrics-json] [--commit]
  lineage   --from-node --from-type --edge-type --to-node --to-type [--commit]
  report    [--metrics-json] [--commit]   # == health
  verify / replay / summary

실제 실행·실험 시작·전략 선택·모델 배포·config 변경·자본 배분 없음 — 관찰·조직·기록만.
ORCHESTRATION ≠ EXECUTION · VISIBILITY ≠ CONTROL · STATUS ≠ APPROVAL · INSIGHT ≠ ACTION.
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
    from jarvis.research_os.engine import ResearchOSEngine
    return ResearchOSEngine()


def _split(s: str) -> list:
    return [x.strip() for x in s.split(",") if x.strip()] if s else []


def _cmd_layer(a) -> int:
    l = _eng().register_layer(a.name, a.version or "1.0", a.prefix or "", [], a.activate, _now(),
                              commit=a.commit)
    _p({"committed": a.commit, "layer": l.to_dict(), "note": "레지스트리 — 실행 아님"})
    return 0


def _cmd_workflow(a) -> int:
    nodes = [{"id": n, "type": "DATASET"} for n in _split(a.nodes)] if a.nodes else []
    w = _eng().register_workflow(a.name, nodes, [], [], _now(), commit=a.commit)
    _p({"committed": a.commit, "workflow": w.to_dict(), "note": "관찰 그래프 — VISIBILITY ≠ CONTROL"})
    return 0


def _cmd_event(a) -> int:
    e = _eng().record_event(a.layer, a.event_type, a.reference_id, "", _now(), commit=a.commit)
    _p({"committed": a.commit, "event": e.to_dict()})
    return 0


def _cmd_snapshot(a) -> int:
    metrics = json.loads(a.metrics_json) if a.metrics_json else {}
    s = _eng().build_ecosystem_snapshot(a.name, a.epoch or "", metrics, _now(), commit=a.commit)
    _p({"committed": a.commit, "snapshot": s.to_dict()})
    return 0


def _cmd_health(a) -> int:
    metrics = json.loads(a.metrics_json) if a.metrics_json else {}
    h = _eng().generate_health_report(a.snapshot_ref or "GLOBAL", metrics, _now(),
                                      commit=a.commit)
    _p({"committed": a.commit, "health": h.to_dict(), "note": "정보용 — 자동 교정 없음"})
    return 0


def _cmd_lineage(a) -> int:
    eng = _eng()
    ln = eng.add_lineage(a.from_node, a.from_type, a.edge_type, a.to_node, a.to_type, _now(),
                         commit=a.commit)
    _p({"committed": a.commit, "lineage": ln.to_dict(), "cycle": eng.lineage_cycle()})
    return 0


def _cmd_report(a) -> int:
    metrics = json.loads(a.metrics_json) if a.metrics_json else {}
    h = _eng().generate_health_report("GLOBAL", metrics, _now(), commit=a.commit)
    _p({"committed": a.commit, "report": h.to_dict()})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_os.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_os.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_os")
    sub = ap.add_subparsers(dest="cmd", required=True)
    la = sub.add_parser("layer")
    la.add_argument("--name", required=True)
    la.add_argument("--version", default="1.0")
    la.add_argument("--prefix", default="")
    la.add_argument("--activate", action="store_true")
    la.add_argument("--commit", action="store_true")
    wf = sub.add_parser("workflow")
    wf.add_argument("--name", required=True)
    wf.add_argument("--nodes", default="")
    wf.add_argument("--commit", action="store_true")
    ev = sub.add_parser("event")
    ev.add_argument("--layer", required=True)
    ev.add_argument("--event-type", required=True)
    ev.add_argument("--reference-id", required=True)
    ev.add_argument("--commit", action="store_true")
    sn = sub.add_parser("snapshot")
    sn.add_argument("--name", required=True)
    sn.add_argument("--epoch", default="")
    sn.add_argument("--metrics-json", default="")
    sn.add_argument("--commit", action="store_true")
    he = sub.add_parser("health")
    he.add_argument("--snapshot-ref", default="GLOBAL")
    he.add_argument("--metrics-json", default="")
    he.add_argument("--commit", action="store_true")
    li = sub.add_parser("lineage")
    for f in ("from-node", "from-type", "edge-type", "to-node", "to-type"):
        li.add_argument(f"--{f}", required=True)
    li.add_argument("--commit", action="store_true")
    rp = sub.add_parser("report")
    rp.add_argument("--metrics-json", default="")
    rp.add_argument("--commit", action="store_true")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"layer": _cmd_layer, "workflow": _cmd_workflow, "event": _cmd_event,
            "snapshot": _cmd_snapshot, "health": _cmd_health, "lineage": _cmd_lineage,
            "report": _cmd_report, "verify": _cmd_verify, "replay": _cmd_replay,
            "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
