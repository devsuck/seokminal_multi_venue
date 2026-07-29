"""jarvis.research_coordinator — Autonomous Research Coordinator (P11.7). **조율·기록 전용.**

다중 연구 에이전트를 조율하는 계층. 연구 태스크 배정·의존성 조율·진행 모니터링·워크로드 재분배·정체 탐지·조율
리포트를 수행하고 Coordinator Registry·Research Plans·Task Assignments·Dependency Graph·Progress Tracker·
Scheduling Metadata·Workload Metadata·Coordination Events·Escalation Records·Completion Reports·Coordinator
Lineage 를 소유한다.

**연구를 실행하지 않는다. 거래하지 않는다. 배포하지 않는다. 어떤 상위 상태도 변경하지 않는다.** 순환 의존성은
거부되고 완료 태스크는 불변이며 태스크 결과·연구 결론은 결코 수정되지 않는다. execution/broker/portfolio/risk/
permission/deployment/live import·호출 없음. COORDINATION ≠ EXECUTION · ASSIGNMENT ≠ TRADE · REBALANCE ≠
DEPLOYMENT · REPORT ≠ APPROVAL. 불변·append-only 해시체인·이벤트 소싱·결정적·재현. 물리 원장은 rco_ 접두사.
"""
from jarvis.research_coordinator.engine import ResearchCoordinatorEngine  # noqa: F401
from jarvis.research_coordinator.models import (  # noqa: F401
    ALLOWED_TASK_TRANSITIONS,
    ALLOWED_TRANSITIONS,
    PLAN_STATES,
    SEVERITIES,
    TASK_STATES,
    ArtifactRecord,
    AssignmentEventRecord,
    CompletedTaskError,
    CompletionReportRecord,
    CoordinationEventRecord,
    CoordinatorRecord,
    CoordinatorSummary,
    DependencyCycleError,
    DependencyRecord,
    EscalationRecord,
    IllegalPlanTransition,
    IllegalTaskTransition,
    ImmutableCoordinatorError,
    InvalidSeverity,
    PlanClosedError,
    PlanEventRecord,
    ProgressRecord,
    ScheduleRecord,
    SelfDependencyError,
    UnknownCoordinatorError,
    UnknownPlanError,
    UnknownTaskError,
    WorkloadRecord,
)
