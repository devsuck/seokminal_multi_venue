"""`python -m jarvis.research_observability <cmd>` — 연구 모니터링·관측 CLI. **관찰·기록 전용.**

  metric   --metric-type --value [--source --epoch] [--commit]
  health   --source-layer [--status --metrics-json --epoch] [--commit]
  snapshot --name [--epoch --metrics m1,m2 --health-json] [--commit]
  anomaly  --source --category [--severity --epoch] [--commit]
  activity --scope --activity-type --reference [--detail] [--commit]
  report   [--metrics-json] [--commit]
  verify / replay / summary

실제 복구·수정·strategy 변경·parameter 조정·workflow 재시작·배포·실행 없음 — 건강 관찰·기록만.
OBSERVATION ≠ ACTION · DETECTION ≠ CORRECTION · WARNING ≠ INTERVENTION · MONITORING ≠ EXECUTION.
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
    from jarvis.research_observability.engine import ResearchObservabilityEngine
    return ResearchObservabilityEngine()


def _split(s: str) -> list:
    return [x.strip() for x in s.split(",") if x.strip()] if s else []


def _cmd_metric(a) -> int:
    m = _eng().register_metric(a.metric_type, a.value, a.source or "", a.epoch or "", _now(),
                               commit=a.commit)
    _p({"committed": a.commit, "metric": m.to_dict(), "note": "관찰·기록만"})
    return 0


def _cmd_health(a) -> int:
    metrics = json.loads(a.metrics_json) if a.metrics_json else {}
    h = _eng().record_health(a.source_layer, a.status or "", metrics, a.epoch or "", _now(),
                             commit=a.commit)
    _p({"committed": a.commit, "health": h.to_dict(), "note": "OBSERVATION ≠ ACTION"})
    return 0


def _cmd_snapshot(a) -> int:
    health = json.loads(a.health_json) if a.health_json else {}
    s = _eng().create_snapshot(a.name, a.epoch or "", _split(a.metrics), health, _now(),
                               commit=a.commit)
    _p({"committed": a.commit, "snapshot": s.to_dict(), "note": "결정적 스냅샷"})
    return 0


def _cmd_anomaly(a) -> int:
    an = _eng().record_anomaly(a.source, a.category, a.severity or "MEDIUM", [], a.epoch or "",
                               _now(), commit=a.commit)
    _p({"committed": a.commit, "anomaly": an.to_dict(), "note": "관찰 기록 — 자동 대응 없음"})
    return 0


def _cmd_activity(a) -> int:
    t = _eng().track_activity(a.scope, a.activity_type, a.reference, a.detail or "", _now(),
                              commit=a.commit)
    _p({"committed": a.commit, "activity": t.to_dict()})
    return 0


def _cmd_report(a) -> int:
    metrics = json.loads(a.metrics_json) if a.metrics_json else {}
    r = _eng().generate_report("GLOBAL", metrics, _now(), commit=a.commit)
    _p({"committed": a.commit, "report": r.to_dict()})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_observability.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_observability.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_observability")
    sub = ap.add_subparsers(dest="cmd", required=True)
    me = sub.add_parser("metric")
    me.add_argument("--metric-type", required=True)
    me.add_argument("--value", type=float, required=True)
    me.add_argument("--source", default="")
    me.add_argument("--epoch", default="")
    me.add_argument("--commit", action="store_true")
    he = sub.add_parser("health")
    he.add_argument("--source-layer", required=True)
    he.add_argument("--status", default="")
    he.add_argument("--metrics-json", default="")
    he.add_argument("--epoch", default="")
    he.add_argument("--commit", action="store_true")
    sn = sub.add_parser("snapshot")
    sn.add_argument("--name", required=True)
    sn.add_argument("--epoch", default="")
    sn.add_argument("--metrics", default="")
    sn.add_argument("--health-json", default="")
    sn.add_argument("--commit", action="store_true")
    an = sub.add_parser("anomaly")
    an.add_argument("--source", required=True)
    an.add_argument("--category", required=True)
    an.add_argument("--severity", default="MEDIUM")
    an.add_argument("--epoch", default="")
    an.add_argument("--commit", action="store_true")
    ac = sub.add_parser("activity")
    ac.add_argument("--scope", required=True)
    ac.add_argument("--activity-type", required=True)
    ac.add_argument("--reference", required=True)
    ac.add_argument("--detail", default="")
    ac.add_argument("--commit", action="store_true")
    rp = sub.add_parser("report")
    rp.add_argument("--metrics-json", default="")
    rp.add_argument("--commit", action="store_true")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"metric": _cmd_metric, "health": _cmd_health, "snapshot": _cmd_snapshot,
            "anomaly": _cmd_anomaly, "activity": _cmd_activity, "report": _cmd_report,
            "verify": _cmd_verify, "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
