"""`python -m jarvis.local_runtime <cmd>` — 로컬 연구 런타임 CLI. **클라우드 없음, 거래·집행 없음.**

  start [--boot] [--commit]      로컬 런타임 시작(기본 read-only; --boot 시 기존 boot() 통합 실행)
  restart [--boot] [--commit]    재시작(멱등)
  stop [--commit]                정지 마커
  sync [--dry-run]               기존 실험 이력 → 연구 원장 멱등 백필(자문 전용, 거래·집행 없음)
  status                         통합 상태(기존 status() + 런타임 + 헬스 + 모듈 발견)
  health                         헬스 체크
  validate                       환경 검증
  discover                       모듈 발견(카테고리별)
  logs / events / summary / verify / replay

로컬 실행 전용. 외부 서비스 의존 없음. 자기 집행 권한 확장 없음.
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
    from jarvis.local_runtime.engine import LocalRuntimeEngine
    return LocalRuntimeEngine()


def _cmd_start(a) -> int:
    _p(_eng().start(_now(), run_boot=a.boot, commit=a.commit).to_dict())
    return 0


def _cmd_restart(a) -> int:
    _p(_eng().restart(_now(), run_boot=a.boot, commit=a.commit).to_dict())
    return 0


def _cmd_stop(a) -> int:
    _p(_eng().stop(_now(), commit=a.commit).to_dict())
    return 0


def _cmd_sync(a) -> int:
    """기존 실험 이력 → 연구 원장 멱등 백필. --dry-run 은 미리보기(원장 무변경)."""
    from jarvis.research_workflow import backfill
    if getattr(a, "dry_run", False):
        p = backfill.plan()
        _p({k: v for k, v in p.items() if k != "records"})
    else:
        _p(backfill.run_backfill(commit=True))
    return 0


def _cmd_status(a) -> int:
    _p(_eng().status(_now()).to_dict())
    return 0


def _cmd_health(a) -> int:
    eng = _eng()
    _p({"status": eng.health_status(), "checks": [c.to_dict() for c in eng.health_checks()]})
    return 0


def _cmd_validate(a) -> int:
    eng = _eng()
    _p({"status": eng.environment_status(),
        "checks": [c.to_dict() for c in eng.validate_environment()]})
    return 0


def _cmd_discover(a) -> int:
    _p(_eng().discover_modules().to_dict())
    return 0


def _cmd_logs(a) -> int:
    _p(_eng().logs())
    return 0


def _cmd_events(a) -> int:
    _p(_eng().events())
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def _cmd_verify(a) -> int:
    from jarvis.local_runtime.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.local_runtime.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.local_runtime")
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name in ("start", "restart"):
        p = sub.add_parser(name)
        p.add_argument("--boot", action="store_true")
        p.add_argument("--commit", action="store_true")
    ps = sub.add_parser("stop")
    ps.add_argument("--commit", action="store_true")
    psync = sub.add_parser("sync")
    psync.add_argument("--dry-run", action="store_true")
    for name in ("status", "health", "validate", "discover", "logs", "events", "summary",
                 "verify", "replay"):
        sub.add_parser(name)

    args = ap.parse_args(argv)
    disp = {"start": _cmd_start, "restart": _cmd_restart, "stop": _cmd_stop, "sync": _cmd_sync,
            "status": _cmd_status, "health": _cmd_health, "validate": _cmd_validate,
            "discover": _cmd_discover, "logs": _cmd_logs, "events": _cmd_events,
            "summary": _cmd_summary, "verify": _cmd_verify, "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
