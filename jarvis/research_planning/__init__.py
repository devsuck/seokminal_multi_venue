"""jarvis.research_planning — Research Planning Intelligence Layer (P10.15). **연구 계획 전용.**

P10.5·P10.7·P10.8·P10.11·P10.12·P10.13·P10.14 를 READ ONLY 로 소비해 역사적 근거로 미래 연구 방향을
조직한다. 연구 기회·로드맵·실험 청사진·의존 분석·자원 추정·우선순위를 기록한다.

**실험 자동 시작·strategy 선택·resource 배분·agent 실행·model 배포 없음.** execution/broker/portfolio
execution/live trading/permission/capital allocation import·호출 없음. PLAN ≠ EXECUTION · PRIORITY ≠
APPROVAL · OPPORTUNITY ≠ GUARANTEED VALUE. append-only 해시체인·결정적·재현. 물리 원장은 rp_ 접두사.
"""
from jarvis.research_planning.engine import ResearchPlanningEngine  # noqa: F401
from jarvis.research_planning.models import (  # noqa: F401
    ANALYZED,
    ARCHIVED,
    COMPLEXITY_HIGH,
    COMPLEXITY_LOW,
    COMPLEXITY_MEDIUM,
    HIGH,
    IDENTIFIED,
    LOW,
    MEDIUM,
    PLANNED,
    DependencyEdge,
    IllegalTransition,
    ImmutableBlueprintError,
    ImmutableHypothesisError,
    ImmutableOpportunityError,
    ImmutablePlanError,
    InvalidDependency,
    OpportunityEvent,
    PlanningArtifact,
    PlanningHypothesis,
    PlanningReport,
    PlanningSummary,
    PriorityAnalysis,
    ResearchBlueprint,
    ResearchPlan,
    UnknownOpportunity,
    UnknownPlan,
)
