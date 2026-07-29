"""jarvis.research_reliability — Research Self-Healing & Reliability Engineering Layer (P24). **기록 전용.**

연구 인프라 장애를 탐지·기록, 복구 계획·시도를 기록, 무결성을 검증, 신뢰성 이력을 유지, 반복 장애를 분석한다. Research
Reliability Registry·Failure Incident Records·Recovery Plans·Recovery Attempts·Integrity Checks·Reliability
Metrics·Postmortem Records·Reliability Reports·Reliability Lineage 를 소유한다.

**실행 복구 시스템이 아니다. 거래 시스템 재시작·프로덕션 수정·자동 배포·권한 변경·전략 실행·모델 자동 수정을 하지 않는다.**
execution/broker/live_trading/portfolio_execution import·호출 없음. RECORD ≠ REPAIR · INCIDENT ≠ EXECUTION ·
RECOVERY = RESEARCH-PROCESS RECOVERY(≠ LIVE SYSTEM). 불변·append-only·해시체인·이벤트 소싱·결정적·재현. 상위 계층
(P10~P23)은 READ ONLY. 원장 rel_ 접두사.
"""
from jarvis.research_reliability.engine import ResearchReliabilityEngine  # noqa: F401
from jarvis.research_reliability.models import (  # noqa: F401
    CHECK_RESULTS,
    INCIDENT_CATEGORIES,
    INCIDENT_STATES,
    INTEGRITY_CHECK_TYPES,
    POSTMORTEM_STATES,
    RECOVERY_RESULTS,
    RELIABILITY_METRICS,
    SEVERITIES,
    ArtifactRecord,
    IllegalIncidentTransition,
    IllegalPostmortemTransition,
    IncidentEventRecord,
    IntegrityCheckRecord,
    PostmortemEventRecord,
    RecoveryEventRecord,
    RecoveryPlanRecord,
    ReliabilityMetricRecord,
    ReliabilityReportRecord,
    ReliabilitySummary,
    ReviewerRequired,
    UnknownEntityError,
    can_incident_transition,
    can_postmortem_transition,
    ratio,
)
