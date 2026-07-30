"""jarvis.research_monitoring — Research Monitoring & Observability Layer (P23). **관찰 전용.**

**ARCHIVED (Phase1 STEP3-B, 2026-07-31):** no active real-import caller found; only historically referenced by security_audit's dynamic AUDIT_TARGETS scan (outside default testpaths). Migration: if security_audit scanning is revived, this is a listed consumer; otherwise safe candidate for full removal in a later phase.

연구 생태계의 건강·품질·활동·무결성을 관찰·기록만 한다. Research Monitoring Registry·Health Metrics·Pipeline
Observations·Activity Events·Quality Signals·System Anomalies·Snapshots·Observability Reports·Lineage 를 소유한다.

**관찰 전용이다. 거래·에이전트 제어·워크플로 수정·권한 변경·전략 승인·모델 배포·자본 배분을 하지 않는다.** execution/
broker/live_portfolio/permission_control import·호출 없음. OBSERVE ≠ CONTROL · HEALTH ≠ APPROVAL · HEALTH ≠
DEPLOYMENT PERMISSION. 불변·append-only·해시체인·이벤트 소싱·결정적·재현. 상위 계층(P9.8~P22)은 READ ONLY. 원장 rmon_ 접두사.
"""
from jarvis.research_monitoring.engine import ResearchMonitoringEngine  # noqa: F401
from jarvis.research_monitoring.models import (  # noqa: F401
    ANOMALY_RULES,
    HEALTH_STATUSES,
    METRIC_TYPES,
    SESSION_STATES,
    SEVERITIES,
    ActivityEventRecord,
    AnomalyRecord,
    ArtifactRecord,
    HealthCheckRecord,
    IllegalSessionTransition,
    ImmutableSessionError,
    MonitoringMetricRecord,
    MonitoringSummary,
    ObservabilityReportRecord,
    ObservationRecord,
    SessionEventRecord,
    SnapshotRecord,
    UnknownEntityError,
    aggregate_health,
    can_session_transition,
    classify_health,
)
