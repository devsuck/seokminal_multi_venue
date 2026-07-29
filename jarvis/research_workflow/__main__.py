"""`python -m jarvis.research_workflow <cmd>` — 워크플로 조율 CLI. **조율만, 실행 없음.**

  run --request "..."                워크플로 조율(외부입력 없으면 BLOCKED 부분완료)
  decision --question "..."          Decision Memo(모든 섹션)
  explain --topic "..."              증거 사슬(설명가능성)
  session-list                       연구 세션 목록
  verify                             rwf_ 해시체인 무결성

기록은 --commit 시에만. 거래·집행 없음. 사람 결정 필수.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _p(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _cmd_run(a) -> int:
    from jarvis.research_workflow.orchestrator import WorkflowOrchestrator
    st = WorkflowOrchestrator().run(a.request, {"topic": a.topic} if a.topic else None,
                                    now=_now(), commit=a.commit)
    _p(st.to_dict())
    return 0


def _cmd_decision(a) -> int:
    from jarvis.research_workflow.decision_support import DecisionSupportEngine
    _p(DecisionSupportEngine().build_memo(a.question, topic=a.topic).to_dict())
    return 0


def _cmd_explain(a) -> int:
    from jarvis.research_workflow.explainability import ExplainabilityEngine
    _p(ExplainabilityEngine().evidence_chain(a.topic).to_dict())
    return 0


def _cmd_session_list(a) -> int:
    from jarvis.research_workflow.session_manager import ResearchSessionManager
    _p(ResearchSessionManager().list_sessions())
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_workflow.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_workflow")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--request", required=True)
    r.add_argument("--topic")
    r.add_argument("--commit", action="store_true")
    d = sub.add_parser("decision")
    d.add_argument("--question", required=True)
    d.add_argument("--topic")
    e = sub.add_parser("explain")
    e.add_argument("--topic", required=True)
    sub.add_parser("session-list")
    sub.add_parser("verify")
    args = ap.parse_args(argv)
    disp = {"run": _cmd_run, "decision": _cmd_decision, "explain": _cmd_explain,
            "session-list": _cmd_session_list, "verify": _cmd_verify}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
