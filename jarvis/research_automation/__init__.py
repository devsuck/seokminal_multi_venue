"""jarvis.research_automation — Research Automation Orchestration Layer (P22). **자동화 조정·기록 전용.**

기존 연구 컴포넌트를 조정(스케줄·의존·파이프라인·실행 기록)만 한다. Research Workflow Registry·Automation Pipeline
Definition·Research Task Graph·Workflow Execution History·Dependency Resolution·Automation Audit Trail·Reports·
Lineage 를 소유한다.

**실행 계층이 아니다. 거래·주문·자본 배분·전략 배포·모델 수정·권한 변경·라이브 승인을 하지 않는다.** execution/broker/
portfolio_live/permission_control/risk_execution import·호출 없음. ORCHESTRATE ≠ EXECUTE · COMPLETED ≠ VALIDATED ·
VALIDATED ≠ DEPLOYED · RECOMMENDED ≠ ENABLED. 불변·append-only·해시체인·이벤트 소싱·결정적·재현. 상위 계층
(P10.2~P21)은 READ ONLY. 물리 원장 ra_ 접두사.
"""
from jarvis.research_automation.engine import ResearchAutomationEngine  # noqa: F401
from jarvis.research_automation.models import (  # noqa: F401
    EVENT_TYPES,
    PIPELINE_STATES,
    TASK_STATES,
    WORKFLOW_STATES,
    ArtifactRecord,
    AutomationEventRecord,
    AutomationReportRecord,
    AutomationSummary,
    CircularDependencyError,
    DanglingDependencyError,
    DependencyRecord,
    IllegalPipelineTransition,
    IllegalTaskTransition,
    IllegalWorkflowTransition,
    ImmutablePipelineError,
    ImmutableTaskError,
    ImmutableWorkflowError,
    PipelineEventRecord,
    RunRecord,
    TaskEventRecord,
    UnknownEntityError,
    WorkflowEventRecord,
    can_pipeline_transition,
    can_task_transition,
    can_workflow_transition,
    detect_cycle,
    topological_order,
)
