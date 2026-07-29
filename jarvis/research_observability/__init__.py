"""jarvis.research_observability — Research Monitoring & Observability Layer (P10.18). **관찰 전용.**

P9.8~P10.17 전 계층을 **READ ONLY** 로 참조(파일 기반, import 없음)해 연구 시스템 건강을 관찰한다. 연구 건강
레지스트리·지표 레지스트리·모니터링 스냅샷·이상 관찰 레지스트리·품질 신호 이력·연구 활동 타임라인·관측
리포트·모니터링 계보를 제공하며 연구 활동·품질 변화·비정상 패턴·열화 신호·운영 가시성을 추적한다.

**복구 실행·연구 객체 수정·strategy 변경·parameter 조정·workflow 재시작·배포 없음.** execution/broker/order/
portfolio execution/capital allocation/live trading/permission/risk controller import·호출 없음. OBSERVATION
≠ ACTION · DETECTION ≠ CORRECTION · WARNING ≠ INTERVENTION · MONITORING ≠ EXECUTION. append-only 해시체인·
결정적·재현. 물리 원장은 mh_ 접두사(Monitoring Health Intelligence; ob_ 는 P10.10 소유이므로 미사용).
"""
from jarvis.research_observability.engine import ResearchObservabilityEngine  # noqa: F401
from jarvis.research_observability.models import (  # noqa: F401
    ACKNOWLEDGED,
    ANOMALY_CATEGORIES,
    ARCHIVED,
    CLEARED,
    DEGRADED,
    HEALTHY,
    HEALTH_STATES,
    METRIC_TYPES,
    OBSERVED,
    UNKNOWN,
    WARNING,
    ActivityEvent,
    AnomalyEvent,
    HealthRecord,
    IllegalTransition,
    ImmutableAnomalyError,
    ImmutableHealthError,
    ImmutableMetricError,
    InvalidAnomalyCategory,
    InvalidHealthStatus,
    InvalidMetricType,
    MetricRecord,
    ObservabilityArtifact,
    ObservabilityReport,
    ObservabilitySummary,
    ObservationSnapshot,
    QualitySignal,
    UnknownAnomaly,
    UnknownSnapshot,
)
