"""jarvis.research_task_planner — Autonomous Research Task Planner (P11.2). **계획 전용.**

AI 에이전트가 연구 워크플로를 계획하는 계층. 입력=연구 목표, 출력=연구 태스크 그래프(DAG). 계획 생애주기
REQUESTED→PLANNED→RUNNING→COMPLETED→REVIEWED. Tasks·Plans·Dependencies·Schedules·Reports 를 소유한다.

**계획만 한다 — 실행 없음. 자동 승인·자동 배포 없음.** 그래프는 REQUESTED 에서만 편집 가능하며 PLANNED 이후
불변(동결). 의존성 순환은 거부되어 DAG 를 유지한다. execution/broker/order/portfolio execution/capital
allocation/live trading/permission/risk controller import·호출 없음. PLAN ≠ EXECUTE · SCHEDULE ≠ DEPLOY ·
GRAPH ≠ APPROVAL. 불변·append-only 해시체인·결정적·재현. 물리 원장은 rtp_ 접두사.
"""
from jarvis.research_task_planner.engine import ResearchTaskPlannerEngine  # noqa: F401
from jarvis.research_task_planner.models import (  # noqa: F401
    ALLOWED_PLAN_TRANSITIONS,
    PLAN_STATES,
    TASK_KINDS,
    DependencyCycleError,
    DependencyRecord,
    IllegalPlanTransition,
    ImmutableDependencyError,
    ImmutablePlanError,
    ImmutableReportError,
    ImmutableScheduleError,
    ImmutableTaskError,
    InvalidTaskKind,
    PlanEventRecord,
    PlanFrozenError,
    PlanReportRecord,
    PlannerSummary,
    ScheduleRecord,
    SelfDependencyError,
    TaskRecord,
    UnknownPlanError,
    UnknownTaskError,
)
