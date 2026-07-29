"""`python -m jarvis.research_observatory <cmd>` — 연구 관측·컨트롤 플레인 CLI. **관측 전용.**

  snapshot   --name [--epoch] [--commit]
  collect    --snapshot-id [--commit]
  dependency --snapshot-id [--commit]
  timeline   --snapshot-id [--commit]
  trend      --snapshot-id [--commit]
  dashboard  --snapshot-id [--commit]
  report     --snapshot-id [--commit]
  verify / summary

실제 선택·승인·배포·실행·자본배분·권한/config 변경 없음 — 관찰·집계·기록만.
OBSERVED ≠ APPROVED · OBSERVED ≠ DEPLOYED · OBSERVED ≠ EXECUTED.
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
    from jarvis.research_observatory.engine import ResearchObservatoryEngine
    return ResearchObservatoryEngine()


def _cmd_snapshot(a) -> int:
    s = _eng().create_snapshot(a.name, a.epoch or "", _now(), commit=a.commit)
    _p({"committed": a.commit, "snapshot": s.to_dict(), "note": "관측 스냅샷 — 운영 상태 무변경"})
    return 0


def _cmd_collect(a) -> int:
    ms = _eng().collect(a.snapshot_id, _now(), commit=a.commit)
    _p({"committed": a.commit, "metrics": [m.to_dict() for m in ms]})
    return 0


def _cmd_dependency(a) -> int:
    eng = _eng()
    ds = eng.dependency_map(a.snapshot_id, _now(), commit=a.commit)
    _p({"committed": a.commit, "dependencies": [d.to_dict() for d in ds],
        "cycle": eng.dependency_cycle(a.snapshot_id)})
    return 0


def _cmd_timeline(a) -> int:
    ts = _eng().build_timeline(a.snapshot_id, _now(), commit=a.commit)
    _p({"committed": a.commit, "timeline": [t.to_dict() for t in ts]})
    return 0


def _cmd_trend(a) -> int:
    ts = _eng().trend_analysis(a.snapshot_id, _now(), commit=a.commit)
    _p({"committed": a.commit, "trends": [t.to_dict() for t in ts],
        "note": "자동 의사결정 없음 — 서술 방향 라벨만"})
    return 0


def _cmd_dashboard(a) -> int:
    d = _eng().dashboard(a.snapshot_id, _now(), commit=a.commit)
    _p({"committed": a.commit, "dashboard": d.to_dict(), "note": "관찰 정보만"})
    return 0


def _cmd_report(a) -> int:
    r = _eng().generate_report(a.snapshot_id, _now(), commit=a.commit)
    _p({"committed": a.commit, "report": r.to_dict()})
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_observatory.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_observatory")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sn = sub.add_parser("snapshot")
    sn.add_argument("--name", required=True)
    sn.add_argument("--epoch", default="")
    sn.add_argument("--commit", action="store_true")
    for name in ("collect", "dependency", "timeline", "trend", "dashboard", "report"):
        p = sub.add_parser(name)
        p.add_argument("--snapshot-id", required=True)
        p.add_argument("--commit", action="store_true")
    sub.add_parser("summary")
    sub.add_parser("verify")
    args = ap.parse_args(argv)
    disp = {"snapshot": _cmd_snapshot, "collect": _cmd_collect, "dependency": _cmd_dependency,
            "timeline": _cmd_timeline, "trend": _cmd_trend, "dashboard": _cmd_dashboard,
            "report": _cmd_report, "summary": _cmd_summary, "verify": _cmd_verify}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
