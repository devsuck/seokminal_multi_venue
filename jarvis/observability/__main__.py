"""`python -m jarvis.observability <cmd>` — 운영 인텔리전스 CLI. **모니터·측정·보고 전용.**

  register  --name [--kind]                      모니터 대상 등록(UNKNOWN) [--commit]
  health    --target --to [--note]               건강 전이 관찰(검증) [--commit]
  metric    --key --value [--unit --target]      지표 기록 [--commit]
  perf      --name --duration [--unit]           성능 스냅샷 [--commit]
  alert     --type --severity --subject [--detail]  알림 기록(is_actionable=False) [--commit]
  collect   / targets / overview / failures / integrity / security / performance
  verify / replay / summary

거래·주문·배포·자동 복구·자동 결정 없음. OBSERVE ≠ EXECUTE · ALERT ≠ REMEDIATION.
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
    from jarvis.observability.engine import ObservabilityEngine
    return ObservabilityEngine()


def _cmd_register(a) -> int:
    _p({"committed": a.commit,
        "target": _eng().register_target(a.name, a.kind, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_health(a) -> int:
    _p({"committed": a.commit,
        "event": _eng().observe_health(a.target, a.to, a.note or "", _now(),
                                      commit=a.commit).to_dict()})
    return 0


def _cmd_metric(a) -> int:
    _p({"committed": a.commit,
        "metric": _eng().record_metric(a.key, a.value, a.unit or "", a.target or "", {}, _now(),
                                      commit=a.commit).to_dict()})
    return 0


def _cmd_perf(a) -> int:
    _p({"committed": a.commit,
        "perf": _eng().record_performance(a.name, a.duration, a.unit or "s", {}, _now(),
                                         commit=a.commit).to_dict()})
    return 0


def _cmd_alert(a) -> int:
    _p({"committed": a.commit,
        "alert": _eng().raise_alert(a.type, a.severity, a.subject, a.detail or "", {}, _now(),
                                   commit=a.commit).to_dict(),
        "note": "is_actionable=False · ALERT ≠ REMEDIATION"})
    return 0


def _cmd_collect(a) -> int:
    _p({"committed": a.commit,
        "metrics": [m.to_dict() for m in _eng().collect_source_metrics(_now(), commit=a.commit)]})
    return 0


def _cmd_targets(a) -> int:
    eng = _eng()
    _p({"targets": [{"target_id": t, "health": eng.current_health(t)} for t in eng.list_targets()]})
    return 0


def _cmd_overview(a) -> int:
    _p(_eng().system_overview(_now()).to_dict())
    return 0


def _cmd_failures(a) -> int:
    _p(_eng().failure_timeline(_now()).to_dict())
    return 0


def _cmd_integrity(a) -> int:
    _p(_eng().integrity_summary(_now()).to_dict())
    return 0


def _cmd_security(a) -> int:
    _p(_eng().security_summary(_now()).to_dict())
    return 0


def _cmd_performance(a) -> int:
    _p(_eng().performance_summary(_now()).to_dict())
    return 0


def _cmd_verify(a) -> int:
    from jarvis.observability.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.observability.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.observability")
    sub = ap.add_subparsers(dest="cmd", required=True)

    rg = sub.add_parser("register")
    rg.add_argument("--name", required=True)
    rg.add_argument("--kind", default="RESEARCH_LAYER")
    rg.add_argument("--commit", action="store_true")

    he = sub.add_parser("health")
    he.add_argument("--target", required=True)
    he.add_argument("--to", required=True)
    he.add_argument("--note", default="")
    he.add_argument("--commit", action="store_true")

    me = sub.add_parser("metric")
    me.add_argument("--key", required=True)
    me.add_argument("--value", type=float, required=True)
    me.add_argument("--unit", default="")
    me.add_argument("--target", default="")
    me.add_argument("--commit", action="store_true")

    pf = sub.add_parser("perf")
    pf.add_argument("--name", required=True)
    pf.add_argument("--duration", type=float, required=True)
    pf.add_argument("--unit", default="s")
    pf.add_argument("--commit", action="store_true")

    al = sub.add_parser("alert")
    al.add_argument("--type", required=True)
    al.add_argument("--severity", default="WARNING")
    al.add_argument("--subject", required=True)
    al.add_argument("--detail", default="")
    al.add_argument("--commit", action="store_true")

    co = sub.add_parser("collect")
    co.add_argument("--commit", action="store_true")

    sub.add_parser("targets")
    sub.add_parser("overview")
    sub.add_parser("failures")
    sub.add_parser("integrity")
    sub.add_parser("security")
    sub.add_parser("performance")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")

    args = ap.parse_args(argv)
    disp = {"register": _cmd_register, "health": _cmd_health, "metric": _cmd_metric,
            "perf": _cmd_perf, "alert": _cmd_alert, "collect": _cmd_collect, "targets": _cmd_targets,
            "overview": _cmd_overview, "failures": _cmd_failures, "integrity": _cmd_integrity,
            "security": _cmd_security, "performance": _cmd_performance, "verify": _cmd_verify,
            "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
