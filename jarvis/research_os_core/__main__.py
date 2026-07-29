"""`python -m jarvis.research_os_core <cmd>` — Phase 10 최종 연구 운영 환경 CLI. **관측 전용.**

  discover                       모듈 카탈로그(10대 도메인 × P9.8~P10.29) 완전 발견·등록 [--commit]
  register --name --domain [...]  모듈 등록 [--commit]
  snapshot [--scope]             OS 시스템 스냅샷 [--commit]
  health   [--scope]             OS 헬스(글로벌 상태) [--commit]
  report   [--scope --metrics-json] 글로벌 연구 리포트 [--commit]
  verify                         전체 무결성 검증
  modules  [--domain]            등록 모듈 목록
  replay / summary

실제 실행·거래·배포·할당·변경 없음 — 관측·집계·리포트만.
OBSERVE ≠ EXECUTE · SNAPSHOT ≠ DEPLOY · HEALTH ≠ ACTION · REPORT ≠ TRADE.
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
    from jarvis.research_os_core.engine import ResearchOSCoreEngine
    return ResearchOSCoreEngine()


def _cmd_discover(a) -> int:
    ms = _eng().discover_modules(_now(), commit=a.commit)
    _p({"committed": a.commit, "discovered": [m.name for m in ms], "count": len(ms)})
    return 0


def _cmd_register(a) -> int:
    m = _eng().register_module(a.name, a.domain, a.phase or "", a.ledger_file or "",
                               a.id_field or "", _now(), commit=a.commit)
    _p({"committed": a.commit, "module": m.to_dict()})
    return 0


def _cmd_snapshot(a) -> int:
    s = _eng().build_os_snapshot(a.scope or "GLOBAL", _now(), commit=a.commit)
    _p({"committed": a.commit, "snapshot": s.to_dict()})
    return 0


def _cmd_health(a) -> int:
    h = _eng().calculate_os_health(a.scope or "GLOBAL", _now(), commit=a.commit)
    _p({"committed": a.commit, "health": h.to_dict(), "note": "HEALTH ≠ ACTION"})
    return 0


def _cmd_report(a) -> int:
    metrics = json.loads(a.metrics_json) if a.metrics_json else {}
    r = _eng().generate_global_report(a.scope or "GLOBAL", metrics, _now(), commit=a.commit)
    _p({"committed": a.commit, "report": r.to_dict(), "note": "REPORT ≠ TRADE"})
    return 0


def _cmd_verify(a) -> int:
    res = _eng().verify_all_integrity()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_modules(a) -> int:
    _p({"modules": _eng().list_modules(a.domain or "")})
    return 0


def _cmd_replay(a) -> int:
    from jarvis.research_os_core.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_os_core")
    sub = ap.add_subparsers(dest="cmd", required=True)
    di = sub.add_parser("discover")
    di.add_argument("--commit", action="store_true")
    rg = sub.add_parser("register")
    rg.add_argument("--name", required=True)
    rg.add_argument("--domain", required=True)
    rg.add_argument("--phase", default="")
    rg.add_argument("--ledger-file", default="")
    rg.add_argument("--id-field", default="")
    rg.add_argument("--commit", action="store_true")
    sn = sub.add_parser("snapshot")
    sn.add_argument("--scope", default="GLOBAL")
    sn.add_argument("--commit", action="store_true")
    he = sub.add_parser("health")
    he.add_argument("--scope", default="GLOBAL")
    he.add_argument("--commit", action="store_true")
    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="GLOBAL")
    rp.add_argument("--metrics-json", default="")
    rp.add_argument("--commit", action="store_true")
    sub.add_parser("verify")
    md = sub.add_parser("modules")
    md.add_argument("--domain", default="")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"discover": _cmd_discover, "register": _cmd_register, "snapshot": _cmd_snapshot,
            "health": _cmd_health, "report": _cmd_report, "verify": _cmd_verify,
            "modules": _cmd_modules, "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
