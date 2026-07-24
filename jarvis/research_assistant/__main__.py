"""`python -m jarvis.research_assistant <cmd>` — 개인 연구 어시스턴트 CLI. **분석만, 결정·승인·집행 없음.**

  daily                    일일 요약(소스별 활동)
  experiments [--limit N]  최근 실험 요약(지표 통계)
  failures                 실패 분석(클러스터·검토 제안)
  knowledge                지식 리캡
  progress                 연구 진행 요약
  areas                    잠재 연구 영역(가능한 다음 검토 — 결정 아님)
  report [--scope] [--commit]   번들 리포트 스냅샷
  summary / verify / replay

기존 원장 READ ONLY 분석. 투자 결정·전략 승인·행동 실행 없음.
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
    from jarvis.research_assistant.engine import ResearchAssistantEngine
    return ResearchAssistantEngine()


def _cmd_daily(a) -> int:
    _p(_eng().daily_summary().to_dict())
    return 0


def _cmd_experiments(a) -> int:
    _p(_eng().experiment_summary(a.limit).to_dict())
    return 0


def _cmd_failures(a) -> int:
    _p(_eng().failure_analysis().to_dict())
    return 0


def _cmd_knowledge(a) -> int:
    _p(_eng().knowledge_recap().to_dict())
    return 0


def _cmd_progress(a) -> int:
    _p(_eng().progress_summary().to_dict())
    return 0


def _cmd_areas(a) -> int:
    _p({**_eng().potential_areas().to_dict(),
        "note": "가능한 다음 검토 제안일 뿐 — 결정/승인 아님, 사람 검토 필요"})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_report(a.scope or "DAILY", _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_assistant.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_assistant.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_assistant")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("experiments")
    ex.add_argument("--limit", type=int, default=20)
    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="DAILY")
    rp.add_argument("--commit", action="store_true")
    for name in ("daily", "failures", "knowledge", "progress", "areas", "summary", "verify",
                 "replay"):
        sub.add_parser(name)
    args = ap.parse_args(argv)
    disp = {"daily": _cmd_daily, "experiments": _cmd_experiments, "failures": _cmd_failures,
            "knowledge": _cmd_knowledge, "progress": _cmd_progress, "areas": _cmd_areas,
            "report": _cmd_report, "summary": _cmd_summary, "verify": _cmd_verify,
            "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
