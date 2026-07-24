"""`python -m jarvis.local_automation <cmd>` — 로컬 연구 자동화 CLI. **워크플로 보조, 거래·배포·배분 없음.**

  job      --name --kind                                   잡 등록(REGISTERED) [--commit]
  enable   --job / disable --job / archive --job           잡 상태 전이 [--commit]
  schedule --job --cadence [--disabled]                    스케줄 설정 [--commit]
  run      --job [--commit]                                잡 1회 실행 기록(record-only)
  due      --tick N                                        해당 틱 실행 예정 잡
  log      --job --level --message                         자동화 로그 [--commit]
  report [--scope] / summary / verify / replay

자동 거래·자동 배포·자동 자본 배분 없음. AUTOMATION = WORKFLOW ASSISTANCE.
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
    from jarvis.local_automation.engine import LocalAutomationEngine
    return LocalAutomationEngine()


def _cmd_job(a) -> int:
    _p({"committed": a.commit,
        "job": _eng().register_job(a.name, a.kind, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_enable(a) -> int:
    _p(_eng().enable_job(a.job, now=_now(), commit=a.commit).to_dict())
    return 0


def _cmd_disable(a) -> int:
    _p(_eng().disable_job(a.job, now=_now(), commit=a.commit).to_dict())
    return 0


def _cmd_archive(a) -> int:
    _p(_eng().archive_job(a.job, now=_now(), commit=a.commit).to_dict())
    return 0


def _cmd_schedule(a) -> int:
    _p(_eng().set_schedule(a.job, a.cadence, not a.disabled, _now(), commit=a.commit).to_dict())
    return 0


def _cmd_run(a) -> int:
    _p({"committed": a.commit,
        "run": _eng().run_job(a.job, None, _now(), commit=a.commit).to_dict(),
        "note": "record-only workflow step · is_binding=False"})
    return 0


def _cmd_due(a) -> int:
    _p({"tick": a.tick, "due_jobs": _eng().due_jobs(a.tick)})
    return 0


def _cmd_log(a) -> int:
    _p(_eng().log_activity(a.job, a.level, a.message, _now(), commit=a.commit).to_dict())
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_report(a.scope or "SYSTEM", _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def _cmd_verify(a) -> int:
    from jarvis.local_automation.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.local_automation.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.local_automation")
    sub = ap.add_subparsers(dest="cmd", required=True)

    jo = sub.add_parser("job")
    jo.add_argument("--name", required=True)
    jo.add_argument("--kind", required=True)
    jo.add_argument("--commit", action="store_true")

    for name in ("enable", "disable", "archive"):
        p = sub.add_parser(name)
        p.add_argument("--job", required=True)
        p.add_argument("--commit", action="store_true")

    sc = sub.add_parser("schedule")
    sc.add_argument("--job", required=True)
    sc.add_argument("--cadence", required=True)
    sc.add_argument("--disabled", action="store_true")
    sc.add_argument("--commit", action="store_true")

    ru = sub.add_parser("run")
    ru.add_argument("--job", required=True)
    ru.add_argument("--commit", action="store_true")

    du = sub.add_parser("due")
    du.add_argument("--tick", type=int, required=True)

    lg = sub.add_parser("log")
    lg.add_argument("--job", required=True)
    lg.add_argument("--level", required=True)
    lg.add_argument("--message", required=True)
    lg.add_argument("--commit", action="store_true")

    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="SYSTEM")
    rp.add_argument("--commit", action="store_true")

    for name in ("summary", "verify", "replay"):
        sub.add_parser(name)

    args = ap.parse_args(argv)
    disp = {"job": _cmd_job, "enable": _cmd_enable, "disable": _cmd_disable,
            "archive": _cmd_archive, "schedule": _cmd_schedule, "run": _cmd_run, "due": _cmd_due,
            "log": _cmd_log, "report": _cmd_report, "summary": _cmd_summary, "verify": _cmd_verify,
            "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
