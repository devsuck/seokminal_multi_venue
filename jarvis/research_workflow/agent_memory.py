"""Agent Memory Integration (P137) — 에이전트를 지식 계층에 연결한다. **직접 원장 쓰기 없음.**

연구 전: Director 가 Previous Knowledge 수신(semantic_recall). 연구 중: 에이전트가 Relevant History 수신.
연구 후: Writer 가 Final Lesson 저장(learning_engine → 기존 rmi_). **직접 원장 쓰기 없음** — 기존 엔진 경유.
**재사용**: semantic_recall(P133)·multi_agent_workflow(P128)·learning_engine(P136).

원칙(문서 §Constitution, §P137): 통합·조율만. 결정적. 거래·집행 없음. 사람 결정.
"""
from __future__ import annotations


def knowledge_informed_research(objective: str, *, company: str = "", assistant=None,
                                now: str = "", commit: bool = False) -> dict:
    """지식 연결 연구: (전)Director가 지식 수신 → (중)다중에이전트 → (후)교훈 저장. 결정적·읽기전용(commit 시 저장).

    Before: semantic_recall 로 Previous Knowledge. During: multi_agent_workflow. After: learning_engine 로
    Final Lesson 저장(기존 rmi_, 직접 원장 쓰기 없음). commit=False=프리뷰.
    """
    obj = (objective or "").strip()
    if assistant is None:
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        assistant = ResearchAssistantEngine()

    # BEFORE — Director 가 Previous Knowledge 수신
    from jarvis.research_workflow.semantic_recall import recall_context
    prior_knowledge = recall_context(obj, assistant=assistant)

    # DURING — 다중 에이전트 연구(지식 컨텍스트를 목표에 주입)
    from jarvis.research_workflow.multi_agent_workflow import run as run_workflow
    workflow = run_workflow(obj, company=company, assistant=assistant, now=now, commit=commit)

    # AFTER — Writer 가 Final Lesson 저장(learning_engine → 기존 rmi_, 직접 쓰기 아님)
    review = workflow.get("review", {})
    spec = (workflow.get("specialist_memos", {}).get("strategy", {}) or {}).get("experiment", {})
    from jarvis.research_workflow.learning_engine import ResearchLearningEngine
    lesson = ResearchLearningEngine().learn(
        backtest={"strategy_name": spec.get("strategy_name", obj), "metrics": spec.get("metrics", {})},
        outcome=("FAILURE" if review.get("verdict") == "BLOCK" else "PARTIAL"),
        assistant=assistant, now=now, commit=commit)

    return {"objective": obj,
            "before": {"previous_knowledge": prior_knowledge,
                       "prior_research_count": prior_knowledge.get("prior_research_count", 0),
                       "tried_before": prior_knowledge.get("tried_before", False)},
            "during": {"pipeline": workflow.get("pipeline", []), "review": review,
                       "report_confidence": workflow.get("report", {}).get("confidence")},
            "after": {"final_lesson": lesson.get("lesson", {}), "stored": lesson.get("stored", {})},
            "human_review_queue": workflow.get("human_review_queue", []),
            "committed": commit, "direct_ledger_writes": False,
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("지식 연결 연구(읽기전용) — Director는 사전 지식, 에이전트는 이력, Writer는 교훈 저장. "
                     "직접 원장 쓰기 없음(기존 rmi_/rwf_ 경유). 사람이 모든 결정.")}
