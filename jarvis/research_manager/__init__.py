"""jarvis.research_manager — Autonomous Research Manager Layer (P12.9). **계획·추적·모니터링 전용.**

연구 워크플로 조정 — 계획·추적·모니터링만. Research Task Registry·Research Plans·Dependencies·Progress Tracking
을 소유한다(+reports/artifacts).

**실행 관리자가 아니다. 거래 시작·주문 실행·모델 배포를 하지 않는다.** execution/broker/portfolio/risk/permission/
deployment/live import·호출 없음. MANAGE ≠ EXECUTION · PLAN ≠ DEPLOYMENT · TRACK ≠ TRADING. 불변·append-only
해시체인·이벤트 소싱·결정적·재현. 상위 계층은 READ ONLY. 물리 원장은 rmgr_ 접두사.
"""
from jarvis.research_manager.engine import AutonomousResearchManagerEngine  # noqa: F401
from jarvis.research_manager.models import (  # noqa: F401
    PLAN_STATES,
    TASK_STATES,
    ArtifactRecord,
    CircularDependencyError,
    DanglingDependencyError,
    DependencyRecord,
    IllegalPlanTransition,
    ImmutableDependencyError,
    ImmutablePlanError,
    ImmutableTaskError,
    ManagerSummary,
    PlanEventRecord,
    ProgressRecord,
    StatusReportRecord,
    TaskRecord,
    UnknownPlanError,
    UnknownTaskError,
)
