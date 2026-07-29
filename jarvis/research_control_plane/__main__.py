"""`python -m jarvis.research_control_plane <cmd>` — 중앙 관측·조율 평면 CLI. **관측·기록 전용.**

  discover                                     상위 카탈로그(P9.8~P10.27)에서 컴포넌트 발견·등록 [--commit]
  register --name --phase --category [...]     컴포넌트 등록 [--commit]
  status   [--component | --all]               계층 상태 수집 [--commit]
  map      --edges-json '[["a","b"]]'          시스템 맵 구성 [--commit]
  issues                                       의존성 이슈 탐지
  health   [--scope]                           헬스 점수 계산 [--commit]
  overview [--scope]                           시스템 개요 스냅샷 [--commit]
  dashboard[--scope]                           거버넌스 대시보드 데이터 [--commit]
  report   [--scope --metrics-json]            컨트롤 리포트 [--commit]
  verify / replay / summary

실제 실행·배포·할당·권한/설정 변경 없음 — 관측·집계·리포트만.
OBSERVE ≠ EXECUTE · STATUS ≠ CONTROL · HEALTH ≠ ACTION · REPORT ≠ DEPLOYMENT.
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
    from jarvis.research_control_plane.engine import ResearchControlPlaneEngine
    return ResearchControlPlaneEngine()


def _cmd_discover(a) -> int:
    cs = _eng().discover_components(_now(), commit=a.commit)
    _p({"committed": a.commit, "discovered": [c.name for c in cs], "count": len(cs)})
    return 0


def _cmd_register(a) -> int:
    c = _eng().register_component(a.name, a.layer or a.name, a.phase or "", a.category or "OTHER",
                                  a.ledger_file or "", a.id_field or "", _now(), commit=a.commit)
    _p({"committed": a.commit, "component": c.to_dict()})
    return 0


def _cmd_status(a) -> int:
    e = _eng()
    if a.all:
        ss = e.collect_all_status(_now(), commit=a.commit)
        _p({"committed": a.commit, "status": [s.to_dict() for s in ss]})
    else:
        s = e.collect_status(a.component, _now(), commit=a.commit)
        _p({"committed": a.commit, "status": s.to_dict()})
    return 0


def _cmd_map(a) -> int:
    edges = [(x[0], x[1]) for x in json.loads(a.edges_json)] if a.edges_json else []
    ds = _eng().build_system_map(edges, _now(), commit=a.commit)
    _p({"committed": a.commit, "dependencies": [d.to_dict() for d in ds]})
    return 0


def _cmd_issues(a) -> int:
    _p(_eng().detect_dependency_issue())
    return 0


def _cmd_health(a) -> int:
    h = _eng().calculate_health_score(a.scope or "GLOBAL", _now(), commit=a.commit)
    _p({"committed": a.commit, "health": h.to_dict(), "note": "HEALTH ≠ ACTION"})
    return 0


def _cmd_overview(a) -> int:
    o = _eng().build_system_overview(a.scope or "GLOBAL", _now(), commit=a.commit)
    _p({"committed": a.commit, "overview": o.to_dict()})
    return 0


def _cmd_dashboard(a) -> int:
    d = _eng().build_dashboard(a.scope or "GLOBAL", _now(), commit=a.commit)
    _p({"committed": a.commit, "dashboard": d.to_dict()})
    return 0


def _cmd_report(a) -> int:
    metrics = json.loads(a.metrics_json) if a.metrics_json else {}
    r = _eng().generate_control_report(a.scope or "GLOBAL", metrics, _now(), commit=a.commit)
    _p({"committed": a.commit, "report": r.to_dict(), "note": "REPORT ≠ DEPLOYMENT"})
    return 0


def _cmd_verify(a) -> int:
    res = _eng().verify_state()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_control_plane.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_control_plane")
    sub = ap.add_subparsers(dest="cmd", required=True)
    di = sub.add_parser("discover")
    di.add_argument("--commit", action="store_true")
    rg = sub.add_parser("register")
    rg.add_argument("--name", required=True)
    rg.add_argument("--layer", default="")
    rg.add_argument("--phase", default="")
    rg.add_argument("--category", default="OTHER")
    rg.add_argument("--ledger-file", default="")
    rg.add_argument("--id-field", default="")
    rg.add_argument("--commit", action="store_true")
    st = sub.add_parser("status")
    st.add_argument("--component", default="")
    st.add_argument("--all", action="store_true")
    st.add_argument("--commit", action="store_true")
    mp = sub.add_parser("map")
    mp.add_argument("--edges-json", required=True)
    mp.add_argument("--commit", action="store_true")
    sub.add_parser("issues")
    he = sub.add_parser("health")
    he.add_argument("--scope", default="GLOBAL")
    he.add_argument("--commit", action="store_true")
    ov = sub.add_parser("overview")
    ov.add_argument("--scope", default="GLOBAL")
    ov.add_argument("--commit", action="store_true")
    db = sub.add_parser("dashboard")
    db.add_argument("--scope", default="GLOBAL")
    db.add_argument("--commit", action="store_true")
    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="GLOBAL")
    rp.add_argument("--metrics-json", default="")
    rp.add_argument("--commit", action="store_true")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"discover": _cmd_discover, "register": _cmd_register, "status": _cmd_status,
            "map": _cmd_map, "issues": _cmd_issues, "health": _cmd_health,
            "overview": _cmd_overview, "dashboard": _cmd_dashboard, "report": _cmd_report,
            "verify": _cmd_verify, "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
