"""jarvis.observability — Observability & Operations Intelligence Layer (P17). **모니터·측정·분석·보고 전용.**

시스템 건강·연구 파이프라인·성능·데이터 품질·감사 가시성을 관찰·기록만 한다. System Metrics·Pipeline Health·Health
Events·Alert Events·Performance Snapshots·Availability·Audit Observations·Artifacts 를 소유한다.

**동작을 실행하지 않는다. 거래·주문·배포·자동 복구·자동 결정·자동 승인을 하지 않는다.** execution/broker/portfolio/
permission/deployment/live import·호출 없음. OBSERVE ≠ EXECUTE · MONITOR ≠ CONTROL · ALERT ≠ REMEDIATION. 불변·
append-only·해시체인·이벤트 소싱·결정적·재현. 상위 계층(P9~P16)은 READ ONLY. 물리 원장은 obs_ 접두사.
"""
from jarvis.observability.engine import ObservabilityEngine  # noqa: F401
from jarvis.observability.models import (  # noqa: F401
    ALERT_TYPES,
    HEALTH_STATES,
    QUALITY_CODES,
    SEVERITIES,
    AlertRecord,
    ArtifactRecord,
    AuditObservationRecord,
    AvailabilityRecord,
    DashboardRecord,
    ForbiddenObservabilityAction,
    HealthEventRecord,
    IllegalHealthTransition,
    ImmutableTargetError,
    MetricRecord,
    ObservabilitySummary,
    ObservationRecord,
    PerfSnapshotRecord,
    UnknownTargetError,
    can_transition,
    classify_health,
)
