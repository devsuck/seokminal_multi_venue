"""jarvis.workflow_automation — Workflow Automation Layer (P44). **자율 실행 없음.**

연구 워크플로를 조율한다: 워크플로 생애주기·태스크·의존성·사람 검토 요청·메타데이터.

**자율 실행 없음 — 사람 승인 필수(Human approval remains required).** execution/broker/live_trading/
portfolio_execution import·호출 없음. WORKFLOW AUTOMATION ≠ AUTONOMOUS EXECUTION. 엔진은 execute()/trade()/
deploy()/allocate()/approve() 를 노출하지 않는다. 불변·append-only·해시체인·이벤트 소싱·결정적·재현. 상위 계층은
READ ONLY. 원장 wf_ 접두사. 기존 P1~P43 불변.
"""
from jarvis.workflow_automation.engine import WorkflowAutomationEngine  # noqa: F401
from jarvis.workflow_automation.models import (  # noqa: F401
    TASK_KINDS,
    TASK_STATES,
    WORKFLOW_STATES,
    ApprovalRequestRecord,
    ArtifactRecord,
    DependencyCycleError,
    DependencyRecord,
    IllegalTaskTransition,
    IllegalWorkflowTransition,
    TaskEventRecord,
    UnknownEntityError,
    WorkflowEventRecord,
    WorkflowMetadataRecord,
    WorkflowReportRecord,
    WorkflowSummary,
    can_task_transition,
    can_workflow_transition,
    topological_order,
)
