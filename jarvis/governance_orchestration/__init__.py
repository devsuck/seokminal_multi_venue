"""jarvis.governance_orchestration — Research Governance Orchestration Layer (P10.23). **관찰·집계 전용.**

전 거버넌스·연구 인텔리전스 계층(P9.8~P10.22)을 **READ ONLY** 로 참조(파일 기반, import 없음)해 계층
레지스트리·시스템 상태 스냅샷·거버넌스 건강 요약·의존 지도·교차계층 충돌 기록·오케스트레이션 리포트·연구 OS
상태를 제공하는 최상위 조정 계층이다.

**실행 계층 아님 — 거래·주문·portfolio 수정·capital 배분·strategy 배포·promote·activate·permission/config
변경 없음.** execution/broker/order/portfolio execution/capital allocation/live trading/permission/risk
controller import·호출 없음. ORCHESTRATION ≠ EXECUTION · MONITORING ≠ CONTROL · STATUS ≠ APPROVAL ·
AGGREGATION ≠ ACTION. append-only 해시체인·결정적·재현. 물리 원장은 go_ 접두사(research_orchestration/or_ 는
P10.17 소유이므로 미사용).
"""
from jarvis.governance_orchestration.engine import GovernanceOrchestrationEngine  # noqa: F401
from jarvis.governance_orchestration.models import (  # noqa: F401
    ARCHIVED,
    CONNECTED,
    CREATED,
    GENERATED,
    MONITORED,
    REGISTERED,
    VERIFIED,
    ConflictRecord,
    DependencyEdge,
    HealthSummary,
    IllegalTransition,
    ImmutableLayerError,
    ImmutableStatusError,
    InvalidConflictCategory,
    InvalidDependencyGraph,
    LayerEvent,
    LayerStatusRecord,
    OrchestrationArtifact,
    OrchestrationReport,
    OrchestrationSummary,
    SystemSnapshotEvent,
    UnknownLayer,
    UnknownSnapshot,
)
