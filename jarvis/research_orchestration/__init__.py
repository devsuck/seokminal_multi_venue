"""jarvis.research_orchestration — Research Orchestration & Workflow Intelligence Layer (P10.17).

연구 과정 가시성·조정 전용. P9.8~P10.16 전 계층을 **READ ONLY** 로 참조(파일 기반, import 없음)해 연구
워크플로 레지스트리·파이프라인 정의·태스크·의존 그래프·실행 이력·이벤트 이력·병목 레지스트리·오케스트레이션
리포트·연구 계보를 관리한다. **연구를 실행하지 않는다.**

execution/broker/order/portfolio execution/capital allocation/live trading/permission/risk controller
import·호출 없음. strategy·signal 실행·portfolio 수정·order 생성·capital 배분·model 배포·자동 연구 트리거·
자동 최적화·config/permission 변경 없음. WORKFLOW STATE ≠ EXECUTION STATE · TASK READY ≠ RUNNING PROCESS ·
WORKFLOW COMPLETED ≠ DEPLOYMENT · ORCHESTRATION ≠ AUTOMATION. append-only 해시체인·결정적·재현. 원장 or_.
"""
from jarvis.research_orchestration.engine import ResearchOrchestrationEngine  # noqa: F401
from jarvis.research_orchestration.models import (  # noqa: F401
    ACKNOWLEDGED,
    ARCHIVED,
    BLOCKED,
    BOTTLENECK_CATEGORIES,
    COMPLETED,
    CREATED,
    IN_PROGRESS,
    OPEN,
    PAUSED,
    PLANNED,
    READY,
    RESOLVED,
    RUNNING,
    BottleneckEvent,
    DependencyEdge,
    IllegalTransition,
    ImmutablePipelineError,
    ImmutableTaskError,
    ImmutableWorkflowError,
    InvalidBottleneckCategory,
    InvalidDependencyGraph,
    OrchestrationArtifact,
    OrchestrationEvent,
    OrchestrationReport,
    OrchestrationSummary,
    PipelineVersion,
    TaskEvent,
    UnknownBottleneck,
    UnknownTask,
    UnknownWorkflow,
    WorkflowEvent,
    WorkflowRun,
)
