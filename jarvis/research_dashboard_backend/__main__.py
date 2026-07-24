"""`python -m jarvis.research_dashboard_backend <cmd>` — 연구 대시보드 백엔드 CLI. **백엔드 집계, UI 없음.**

  panel     --type --name [--description]                   패널 등록 [--commit]
  snapshot  --type                                          집계 스냅샷(결정 아님) [--commit]
  widget    --type --metric --value [--unit]                위젯/지표 [--commit]
  aggregate --panel                                         즉시 집계(통계/헬스/진행/...)
  report [--scope] / verify / summary / replay

UI·결정·실행·거래·배포 없음. BACKEND ONLY · AGGREGATION ≠ DECISION.
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
    from jarvis.research_dashboard_backend.engine import ResearchDashboardBackendEngine
    return ResearchDashboardBackendEngine()


def _cmd_panel(a) -> int:
    _p({"committed": a.commit,
        "panel": _eng().register_panel(a.type, a.name, a.description or "", _now(),
                                     commit=a.commit).to_dict()})
    return 0


def _cmd_snapshot(a) -> int:
    _p({"committed": a.commit,
        "snapshot": _eng().create_snapshot(a.type, _now(), commit=a.commit).to_dict(),
        "note": "is_decision=False"})
    return 0


def _cmd_widget(a) -> int:
    _p({"committed": a.commit,
        "widget": _eng().record_widget(a.type, a.metric, a.value, a.unit or "count", _now(),
                                     commit=a.commit).to_dict()})
    return 0


def _cmd_aggregate(a) -> int:
    e = _eng()
    disp = {"STATISTICS": e.aggregate_statistics, "TIMELINE": e.build_timeline,
            "HEALTH": e.aggregate_health, "KNOWLEDGE_SUMMARY": e.knowledge_summary,
            "RESEARCH_PROGRESS": e.research_progress, "MONITORING": e.monitoring_summary}
    fn = disp.get(a.panel)
    if not fn:
        _p({"error": f"unknown panel {a.panel}"})
        return 1
    _p(fn())
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_report(a.scope or "SYSTEM", _now(), commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_dashboard_backend.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def _cmd_replay(a) -> int:
    from jarvis.research_dashboard_backend.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_dashboard_backend")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("panel")
    pa.add_argument("--type", required=True)
    pa.add_argument("--name", required=True)
    pa.add_argument("--description", default="")
    pa.add_argument("--commit", action="store_true")

    sn = sub.add_parser("snapshot")
    sn.add_argument("--type", required=True)
    sn.add_argument("--commit", action="store_true")

    wi = sub.add_parser("widget")
    wi.add_argument("--type", required=True)
    wi.add_argument("--metric", required=True)
    wi.add_argument("--value", type=float, required=True)
    wi.add_argument("--unit", default="count")
    wi.add_argument("--commit", action="store_true")

    ag = sub.add_parser("aggregate")
    ag.add_argument("--panel", required=True)

    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="SYSTEM")
    rp.add_argument("--commit", action="store_true")

    sub.add_parser("verify")
    sub.add_parser("summary")
    sub.add_parser("replay")

    args = ap.parse_args(argv)
    disp = {"panel": _cmd_panel, "snapshot": _cmd_snapshot, "widget": _cmd_widget,
            "aggregate": _cmd_aggregate, "report": _cmd_report, "verify": _cmd_verify,
            "summary": _cmd_summary, "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
