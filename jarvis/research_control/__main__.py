"""`python -m jarvis.research_control <cmd>` — 자율 연구 제어 평면 CLI. **관찰·분석·모니터링 전용.**

  init      --name [--kind]                          관찰 대상 상태 등록 [--commit]
  observe   --state [--kind --layer --ref --note]    연구 이벤트 관찰(→OBSERVED) [--commit]
  health    --state --score [--note]                 헬스 관찰 [--commit]
  metric    --state --key --value [--unit]           지표 관찰 [--commit]
  anomaly   --state                                  이상 탐지(기록만, →ANALYZED) [--commit]
  report    --state / archive --state                리포트(→REPORTED) / 보관 [--commit]
  snapshot  / states / verify / replay / summary

자동 복구·배포·결정 없음. OBSERVE ≠ EXECUTION · MONITOR ≠ CONTROL · ANOMALY ≠ RECOVERY.
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
    from jarvis.research_control.engine import AutonomousResearchControlPlaneEngine
    return AutonomousResearchControlPlaneEngine()


def _cmd_init(a) -> int:
    _p({"committed": a.commit,
        "state": _eng().initialize_state(a.name, a.kind, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_observe(a) -> int:
    _p({"committed": a.commit,
        "event": _eng().collect_state(a.state, a.kind, a.layer or "", a.ref or "", a.note or "",
                                     _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_health(a) -> int:
    _p({"committed": a.commit,
        "health": _eng().collect_health(a.state, a.score, a.note or "", _now(),
                                       commit=a.commit).to_dict()})
    return 0


def _cmd_metric(a) -> int:
    _p({"committed": a.commit,
        "metric": _eng().collect_metric(a.state, a.key, a.value, a.unit or "", _now(),
                                       commit=a.commit).to_dict()})
    return 0


def _cmd_anomaly(a) -> int:
    _p({"committed": a.commit,
        "alerts": [x.to_dict() for x in _eng().detect_anomaly(a.state, _now(), commit=a.commit)],
        "note": "ANOMALY ≠ RECOVERY · is_actionable=False"})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_system_report(a.state, "STATE", _now(), commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_archive(a) -> int:
    _p({"committed": a.commit,
        "event": _eng().archive_state(a.state, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_snapshot(a) -> int:
    _p(_eng().create_snapshot(_now(), commit=a.commit).to_dict())
    return 0


def _cmd_states(a) -> int:
    eng = _eng()
    _p({"states": [{"state_id": s, "state": eng.current_state(s)} for s in eng.list_states()]})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_control.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_control.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_control")
    sub = ap.add_subparsers(dest="cmd", required=True)

    it = sub.add_parser("init")
    it.add_argument("--name", required=True)
    it.add_argument("--kind", default="SYSTEM")
    it.add_argument("--commit", action="store_true")

    ob = sub.add_parser("observe")
    ob.add_argument("--state", required=True)
    ob.add_argument("--kind", default="OBSERVATION")
    ob.add_argument("--layer", default="")
    ob.add_argument("--ref", default="")
    ob.add_argument("--note", default="")
    ob.add_argument("--commit", action="store_true")

    he = sub.add_parser("health")
    he.add_argument("--state", required=True)
    he.add_argument("--score", type=float, required=True)
    he.add_argument("--note", default="")
    he.add_argument("--commit", action="store_true")

    me = sub.add_parser("metric")
    me.add_argument("--state", required=True)
    me.add_argument("--key", required=True)
    me.add_argument("--value", type=float, required=True)
    me.add_argument("--unit", default="")
    me.add_argument("--commit", action="store_true")

    an = sub.add_parser("anomaly")
    an.add_argument("--state", required=True)
    an.add_argument("--commit", action="store_true")

    rp = sub.add_parser("report")
    rp.add_argument("--state", required=True)
    rp.add_argument("--commit", action="store_true")

    ar = sub.add_parser("archive")
    ar.add_argument("--state", required=True)
    ar.add_argument("--commit", action="store_true")

    sn = sub.add_parser("snapshot")
    sn.add_argument("--commit", action="store_true")

    sub.add_parser("states")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")

    args = ap.parse_args(argv)
    disp = {"init": _cmd_init, "observe": _cmd_observe, "health": _cmd_health, "metric": _cmd_metric,
            "anomaly": _cmd_anomaly, "report": _cmd_report, "archive": _cmd_archive,
            "snapshot": _cmd_snapshot, "states": _cmd_states, "verify": _cmd_verify,
            "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
