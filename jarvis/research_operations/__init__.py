"""jarvis.research_operations — Research Operations & Workflow Orchestration Layer (P18). **조정·계획·추적 전용.**

연구 워크플로·작업·의존(DAG)·실행 계획·런·이벤트·리포트를 조정·기록만 한다. Research Workflows·Task Registry·
Dependencies·Execution Plans·Runs·Operation Reports·Lineage 를 소유한다.

**거래하지 않는다. 전략을 배포하지 않는다. 권한을 변경하지 않는다.** execution/broker/portfolio/permission/
deployment/live import·호출 없음. ORCHESTRATE ≠ EXECUTE · PLAN ≠ DEPLOYMENT · SCHEDULE ≠ TRADING. 불변·append-
only·해시체인·이벤트 소싱·결정적·재현. 상위/통합 계층(P10.5/P10.6/P10.7/P10.8/P17)은 READ ONLY. 물리 원장 ro_ 접두사.
"""
from jarvis.research_operations.engine import ResearchOperationsEngine  # noqa: F401
from jarvis.research_operations.models import (  # noqa: F401
    EVENT_TYPES,
    TASK_STATES,
    WORKFLOW_STATES,
    ArtifactRecord,
    CircularDependencyError,
    DanglingDependencyError,
    DependencyRecord,
    ExecutionPlanRecord,
    IllegalTaskTransition,
    IllegalWorkflowTransition,
    ImmutableTaskError,
    ImmutableWorkflowError,
    OperationReportRecord,
    OperationsSummary,
    OrchestrationEventRecord,
    RunRecord,
    TaskEventRecord,
    UnknownTaskError,
    UnknownWorkflowError,
    WorkflowEventRecord,
    can_task_transition,
    can_workflow_transition,
    detect_cycle,
    topological_order,
)
