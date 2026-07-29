"""`python -m jarvis.research_monitoring <cmd>` — 연구 모니터링·관측성 CLI. **관찰 전용.**

  metric   --name --value [--type --layer --ref]     지표 기록 [--commit]
  health   --component --score                        헬스 체크 [--commit]
  observe  --layer [--ref]                            파이프라인 관찰(READ ONLY) [--commit]
  anomaly  --rule --ref [--severity --desc]           이상 탐지 기록(자동 조치 없음) [--commit]
  snapshot [--scope]                                  결정적 스냅샷 [--commit]
  report   [--scope] / verify / summary / replay

거래·에이전트 제어·워크플로 수정·권한 변경·전략 승인·모델 배포 없음. OBSERVE ≠ CONTROL · HEALTH ≠ APPROVAL.
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
    from jarvis.research_monitoring.engine import ResearchMonitoringEngine
    return ResearchMonitoringEngine()


def _cmd_metric(a) -> int:
    _p({"committed": a.commit,
        "metric": _eng().register_metric(a.name, a.value, a.type or "GAUGE", a.layer or "",
                                        a.ref or "", _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_health(a) -> int:
    _p({"committed": a.commit,
        "health": _eng().record_health_check(a.component, a.score, {}, _now(),
                                            commit=a.commit).to_dict(),
        "note": "HEALTH ≠ APPROVAL"})
    return 0


def _cmd_observe(a) -> int:
    _p({"committed": a.commit, "observed": _eng().observe_pipeline(a.layer, a.ref or "", _now(),
                                                                  commit=a.commit)})
    return 0


def _cmd_anomaly(a) -> int:
    _p({"committed": a.commit,
        "anomaly": _eng().detect_anomaly(a.rule, a.ref, a.severity or "LOW", a.desc or "", _now(),
                                        commit=a.commit).to_dict(),
        "note": "is_actionable=False · detection only"})
    return 0


def _cmd_snapshot(a) -> int:
    _p({"committed": a.commit,
        "snapshot": _eng().create_snapshot(a.scope or "SYSTEM", _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_report(a.scope or "SYSTEM", _now(), commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_monitoring.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def _cmd_replay(a) -> int:
    from jarvis.research_monitoring.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_monitoring")
    sub = ap.add_subparsers(dest="cmd", required=True)

    me = sub.add_parser("metric")
    me.add_argument("--name", required=True)
    me.add_argument("--value", type=float, required=True)
    me.add_argument("--type", default="GAUGE")
    me.add_argument("--layer", default="")
    me.add_argument("--ref", default="")
    me.add_argument("--commit", action="store_true")

    he = sub.add_parser("health")
    he.add_argument("--component", required=True)
    he.add_argument("--score", type=float, required=True)
    he.add_argument("--commit", action="store_true")

    ob = sub.add_parser("observe")
    ob.add_argument("--layer", required=True)
    ob.add_argument("--ref", default="")
    ob.add_argument("--commit", action="store_true")

    an = sub.add_parser("anomaly")
    an.add_argument("--rule", required=True)
    an.add_argument("--ref", required=True)
    an.add_argument("--severity", default="LOW")
    an.add_argument("--desc", default="")
    an.add_argument("--commit", action="store_true")

    sn = sub.add_parser("snapshot")
    sn.add_argument("--scope", default="SYSTEM")
    sn.add_argument("--commit", action="store_true")

    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="SYSTEM")
    rp.add_argument("--commit", action="store_true")

    sub.add_parser("verify")
    sub.add_parser("summary")
    sub.add_parser("replay")

    args = ap.parse_args(argv)
    disp = {"metric": _cmd_metric, "health": _cmd_health, "observe": _cmd_observe,
            "anomaly": _cmd_anomaly, "snapshot": _cmd_snapshot, "report": _cmd_report,
            "verify": _cmd_verify, "summary": _cmd_summary, "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
