"""jarvis.research_os — Research Operating System Orchestration Layer (P11). **관찰·조직 전용.**

P9.8~P10.15 전 연구 인텔리전스 생태계를 READ ONLY 로 소비해 통합 연구 상태·교차계층 계보 지도·연구
생명주기 가시성·시스템 건강·의존 인식·연구 활동 타임라인을 제공하는 최상위 조정 계층이다.

**연구 실행·실험 시작·strategy 선택·model 배포·config 수정·capital 배분 없음.** execution/broker/
portfolio execution/risk execution/permission mutation/capital allocation import·호출 없음.
ORCHESTRATION ≠ EXECUTION · VISIBILITY ≠ CONTROL · STATUS ≠ APPROVAL · INSIGHT ≠ ACTION.
append-only 해시체인·결정적·재현. 물리 원장은 ros_ 접두사.
"""
from jarvis.research_os.engine import ResearchOSEngine  # noqa: F401
from jarvis.research_os.models import (  # noqa: F401
    ACTIVE,
    ARCHIVED,
    COMPLETED,
    CREATED,
    DEGRADED,
    DEPRECATED,
    HEALTHY,
    REGISTERED,
    TRACKING,
    VERIFIED,
    WARNING,
    CrossLayerEvent,
    DependencyEdge,
    HealthReport,
    IllegalTransition,
    ImmutableLayerError,
    ImmutableWorkflowError,
    InvalidWorkflowGraph,
    LayerEvent,
    LineageEdge,
    OrchestrationArtifact,
    OrchestrationSummary,
    SnapshotEvent,
    UnknownLayer,
    UnknownSnapshot,
    UnknownWorkflow,
    WorkflowEvent,
)
