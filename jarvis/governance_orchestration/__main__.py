"""`python -m jarvis.governance_orchestration <cmd>` — 거버넌스 오케스트레이션 CLI. **관찰·집계·기록 전용.**

  layer      --name [--layer-type --source-prefix] [--commit]
  status     --layer-reference [--status --metrics-json --epoch] [--commit]
  dependency --from-layer --to-layer [--commit]
  snapshot   --name [--epoch --metrics-json] [--commit]
  conflict   --layer-a --layer-b --category [--severity --detail] [--commit]
  health     [--metrics-json --epoch] [--commit]
  report     [--metrics-json] [--commit]
  verify / replay / summary

실제 실행·거래·배포·config·permission 변경 없음 — 전 계층 관찰·집계만.
ORCHESTRATION ≠ EXECUTION · MONITORING ≠ CONTROL · STATUS ≠ APPROVAL · AGGREGATION ≠ ACTION.
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
    from jarvis.governance_orchestration.engine import GovernanceOrchestrationEngine
    return GovernanceOrchestrationEngine()


def _cmd_layer(a) -> int:
    l = _eng().register_layer(a.name, a.layer_type or "governance", a.source_prefix or "", _now(),
                              commit=a.commit)
    _p({"committed": a.commit, "layer": l.to_dict(), "note": "레지스트리 — 실행 아님"})
    return 0


def _cmd_status(a) -> int:
    metrics = json.loads(a.metrics_json) if a.metrics_json else {}
    s = _eng().ingest_layer_status(a.layer_reference, a.status or "UNKNOWN", metrics, a.epoch or "",
                                   _now(), commit=a.commit)
    _p({"committed": a.commit, "status": s.to_dict(), "note": "STATUS ≠ APPROVAL"})
    return 0


def _cmd_dependency(a) -> int:
    eng = _eng()
    d = eng.build_dependency_map([(a.from_layer, a.to_layer, "DEPENDS_ON")], _now(),
                                 commit=a.commit)
    _p({"committed": a.commit, "dependency": d[0].to_dict() if d else None,
        "cycle": eng.dependency_cycle()})
    return 0


def _cmd_snapshot(a) -> int:
    metrics = json.loads(a.metrics_json) if a.metrics_json else {}
    s = _eng().create_system_snapshot(a.name, a.epoch or "", metrics, _now(), commit=a.commit)
    _p({"committed": a.commit, "snapshot": s.to_dict(), "note": "MONITORING ≠ CONTROL"})
    return 0


def _cmd_conflict(a) -> int:
    c = _eng().detect_conflicts([(a.layer_a, a.layer_b, a.category, a.severity or "MEDIUM",
                                  a.detail or "", [])], _now(), commit=a.commit)
    _p({"committed": a.commit, "conflicts": [x.to_dict() for x in c], "note": "탐지·기록만"})
    return 0


def _cmd_health(a) -> int:
    metrics = json.loads(a.metrics_json) if a.metrics_json else {}
    h = _eng().generate_health_report("GLOBAL", metrics, a.epoch or "", _now(), commit=a.commit)
    _p({"committed": a.commit, "health": h.to_dict(), "note": "정보용 — 집행 없음"})
    return 0


def _cmd_report(a) -> int:
    metrics = json.loads(a.metrics_json) if a.metrics_json else {}
    r = _eng().generate_report("GLOBAL", metrics, _now(), commit=a.commit)
    _p({"committed": a.commit, "report": r.to_dict()})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.governance_orchestration.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.governance_orchestration.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.governance_orchestration")
    sub = ap.add_subparsers(dest="cmd", required=True)
    la = sub.add_parser("layer")
    la.add_argument("--name", required=True)
    la.add_argument("--layer-type", default="governance")
    la.add_argument("--source-prefix", default="")
    la.add_argument("--commit", action="store_true")
    st = sub.add_parser("status")
    st.add_argument("--layer-reference", required=True)
    st.add_argument("--status", default="UNKNOWN")
    st.add_argument("--metrics-json", default="")
    st.add_argument("--epoch", default="")
    st.add_argument("--commit", action="store_true")
    dp = sub.add_parser("dependency")
    dp.add_argument("--from-layer", required=True)
    dp.add_argument("--to-layer", required=True)
    dp.add_argument("--commit", action="store_true")
    sn = sub.add_parser("snapshot")
    sn.add_argument("--name", required=True)
    sn.add_argument("--epoch", default="")
    sn.add_argument("--metrics-json", default="")
    sn.add_argument("--commit", action="store_true")
    cf = sub.add_parser("conflict")
    cf.add_argument("--layer-a", required=True)
    cf.add_argument("--layer-b", required=True)
    cf.add_argument("--category", required=True)
    cf.add_argument("--severity", default="MEDIUM")
    cf.add_argument("--detail", default="")
    cf.add_argument("--commit", action="store_true")
    he = sub.add_parser("health")
    he.add_argument("--metrics-json", default="")
    he.add_argument("--epoch", default="")
    he.add_argument("--commit", action="store_true")
    rp = sub.add_parser("report")
    rp.add_argument("--metrics-json", default="")
    rp.add_argument("--commit", action="store_true")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"layer": _cmd_layer, "status": _cmd_status, "dependency": _cmd_dependency,
            "snapshot": _cmd_snapshot, "conflict": _cmd_conflict, "health": _cmd_health,
            "report": _cmd_report, "verify": _cmd_verify, "replay": _cmd_replay,
            "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
