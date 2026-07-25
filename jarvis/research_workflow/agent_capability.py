"""Research Agent Architecture (P121) — AI 연구 조직 구조. **분석만, 결정 없음.**

역할 계층: Research Director → Specialist Agents(Market/Company/Strategy) → Critic(Reviewer) → Report(Writer).
모든 에이전트는 **RESEARCH_ONLY**(분석 전용) — 트레이딩/집행/투자결정 에이전트가 아니다. 기존 엔진만 조율하고
새 지능/메모리/DB/원장을 만들지 않는다. AgentCapabilityMap 은 각 에이전트의 목적·입력·출력·사용엔진을 문서화.

원칙(문서 §Constitution, §P121): 통합·조율만. 결정적. 거래·집행 없음. 사람 승인 필수.
"""
from __future__ import annotations

# 에이전트 역량 지도(정적 참조) — Agent·Purpose·Input·Output·Used Engines·Role·Level
AGENT_CAPABILITY_MAP = (
    {"agent": "ResearchDirector", "role": "director", "level": "RESEARCH_ONLY",
     "purpose": "연구 목표 접수·워크플로 선택·전문가 태스크 배정·진행 추적·상태 요약",
     "input": "research objective(text)",
     "output": "Research Plan {objective, hypothesis, required_data, assigned_agents, validation_plan}",
     "used_engines": ["hypothesis_generator", "experiment_planner", "research_prioritizer",
                      "session_manager"]},
    {"agent": "MarketAnalyst", "role": "specialist", "level": "RESEARCH_ONLY",
     "purpose": "시장 상황 요약·관련 이벤트 식별·컨텍스트 제공",
     "input": "topic·events",
     "output": "Market Research Memo {regime, events, opportunities, context}",
     "used_engines": ["market_cockpit", "regime", "event_stream", "opportunity_discovery",
                      "news_pipeline"]},
    {"agent": "CompanyAnalyst", "role": "specialist", "level": "RESEARCH_ONLY",
     "purpose": "재무 변화·실적·비즈니스 이벤트·경쟁 지위 분석",
     "input": "company·financials·headlines",
     "output": "Company Research Memo {fundamentals, earnings, events, competitive}",
     "used_engines": ["fundamental_pipeline", "earnings_intelligence", "news_pipeline",
                      "insider_flow"]},
    {"agent": "StrategyResearcher", "role": "specialist", "level": "RESEARCH_ONLY",
     "purpose": "가설 수립·실험 설계·과거 연구 분석",
     "input": "topic·hypothesis",
     "output": "Strategy Research Plan {hypotheses, experiment, backtest_job, validation}",
     "used_engines": ["hypothesis_generator", "experiment_planner", "backtest_bridge",
                      "paper_validation"]},
    {"agent": "ResearchReviewer", "role": "critic", "level": "RESEARCH_ONLY",
     "purpose": "bias·overfitting·missing evidence·weak assumptions·validation quality 평가",
     "input": "experiment spec·metrics",
     "output": "Research Review {critique, quality, risk, verdict}",
     "used_engines": ["research_critic", "quality_monitor", "failure_reasoning(risk)",
                      "failure_taxonomy"]},
    {"agent": "ResearchWriter", "role": "report", "level": "RESEARCH_ONLY",
     "purpose": "연구 리포트 작성(질문·증거·역사·분석·리스크·누락증거·다음단계 + 신뢰도·한계)",
     "input": "director plan·specialist memos·review",
     "output": "Research Report(7 sections + confidence + limitations)",
     "used_engines": ["research_assistant.recall", "decision_support", "explainability"]},
)

# 역할 계층(director → specialist → critic → report)
ROLE_HIERARCHY = ("director", "specialist", "critic", "report")

# 기존 에이전트 프레임워크(P121 감사) — 재사용/참조(중복 생성 금지)
EXISTING_AGENT_FRAMEWORK = (
    {"name": "jarvis/agents (research/critic/backtest/datagate)", "kind": "permission-bounded principals",
     "level": "RESEARCH_ONLY..PAPER_ONLY", "note": "함수형 에이전트 — propose/review/run/check"},
    {"name": "research_council.ResearchCouncilEngine", "kind": "event-sourced council(cnl_)",
     "level": "advisory", "note": "심의/합의 기록 — 결정 아님"},
    {"name": "research_assistant.council + council_evolution.deliberate", "kind": "7-perspective memo",
     "level": "advisory", "note": "관점 심의 — 논거만 생산"},
    {"name": "research_workflow.ResearchCritic (P75)", "kind": "8-dimension critic",
     "level": "advisory", "note": "P126 ResearchReviewer 가 확장"},
)


def capability_map() -> dict:
    """AgentCapabilityMap(읽기전용) — 역할 계층 + 각 에이전트 목적·입력·출력·사용엔진 + 기존 프레임워크 감사."""
    by_role: dict = {}
    for a in AGENT_CAPABILITY_MAP:
        by_role.setdefault(a["role"], []).append(a["agent"])
    return {"agents": list(AGENT_CAPABILITY_MAP), "count": len(AGENT_CAPABILITY_MAP),
            "role_hierarchy": list(ROLE_HIERARCHY), "by_role": by_role,
            "existing_framework": list(EXISTING_AGENT_FRAMEWORK),
            "all_analysis_only": True, "level": "RESEARCH_ONLY",
            "is_advisory": True, "is_decision": False,
            "note": ("AI 연구 조직 구조(읽기전용) — 분석 전용 에이전트. 트레이딩/집행/결정 에이전트 아님. "
                     "기존 엔진 재사용, 새 지능/메모리/DB/원장 없음. 사람 승인 필수.")}
