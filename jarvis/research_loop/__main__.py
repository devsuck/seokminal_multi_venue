"""`python -m jarvis.research_loop <cmd>` — 연구 루프 CLI. **사람 승인 필수, 자동 실행/집행 없음.**

  create   --title [--observation]                루프 생성(OBSERVATION) [--commit]
  advance  --loop --to                            단계 전이(EXECUTION 은 승인 게이트) [--commit]
  review   --loop --decision --reviewer [--note]  사람 검토 기록(APPROVED/REJECTED) [--commit]
  status   --loop                                 현재 단계 + 승인 상태
  report [--scope] / summary / verify / replay

자동 승인·자동 실행·거래 집행 없음. 사람이 결정한다.
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
    from jarvis.research_loop.engine import ResearchLoopEngine
    return ResearchLoopEngine()


def _cmd_create(a) -> int:
    _p({"committed": a.commit,
        "loop": _eng().create_loop(a.title, a.observation or "", _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_advance(a) -> int:
    _p(_eng().advance(a.loop, a.to, "", _now(), commit=a.commit).to_dict())
    return 0


def _cmd_review(a) -> int:
    _p({"committed": a.commit,
        "review": _eng().record_human_review(a.loop, a.decision, a.reviewer, a.note or "", _now(),
                                             commit=a.commit).to_dict(),
        "note": "사람 결정의 기록 — 엔진이 승인하지 않는다"})
    return 0


def _cmd_status(a) -> int:
    eng = _eng()
    _p({"loop": a.loop, "stage": eng.stage(a.loop), "approval": eng.approval_status(a.loop)})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_report(a.scope or "SYSTEM", _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_loop.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_loop.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_loop")
    sub = ap.add_subparsers(dest="cmd", required=True)

    cr = sub.add_parser("create")
    cr.add_argument("--title", required=True)
    cr.add_argument("--observation", default="")
    cr.add_argument("--commit", action="store_true")

    av = sub.add_parser("advance")
    av.add_argument("--loop", required=True)
    av.add_argument("--to", required=True)
    av.add_argument("--commit", action="store_true")

    rv = sub.add_parser("review")
    rv.add_argument("--loop", required=True)
    rv.add_argument("--decision", required=True)
    rv.add_argument("--reviewer", required=True)
    rv.add_argument("--note", default="")
    rv.add_argument("--commit", action="store_true")

    st = sub.add_parser("status")
    st.add_argument("--loop", required=True)

    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="SYSTEM")
    rp.add_argument("--commit", action="store_true")

    for name in ("summary", "verify", "replay"):
        sub.add_parser(name)

    args = ap.parse_args(argv)
    disp = {"create": _cmd_create, "advance": _cmd_advance, "review": _cmd_review,
            "status": _cmd_status, "report": _cmd_report, "summary": _cmd_summary,
            "verify": _cmd_verify, "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
