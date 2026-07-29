"""jarvis.model_management — Model Management Layer (P43). **라이브 배포 없음.**

AI/ML 모델 생애주기를 관리한다: 모델·모델 버전·검증 결과·성능 이력·모델 메타데이터.

**라이브 배포 없음 — 연구용 관리만.** execution/broker/live_trading/portfolio_execution import·호출 없음.
MANAGED ≠ DEPLOYED · AVAILABLE_FOR_RESEARCH ≠ LIVE. 불변·append-only·해시체인·이벤트 소싱·결정적·재현. 상위 계층은
READ ONLY. 원장 mdl_ 접두사. 기존 P1~P42 불변.
"""
from jarvis.model_management.engine import ModelManagementEngine  # noqa: F401
from jarvis.model_management.models import (  # noqa: F401
    MODEL_STATES,
    MODEL_TYPES,
    VALIDATION_CHECKS,
    ArtifactRecord,
    IllegalModelTransition,
    ModelEventRecord,
    ModelMetadataRecord,
    ModelReportRecord,
    ModelSummary,
    ModelVersionRecord,
    PerformanceRecord,
    UnknownEntityError,
    ValidationResultRecord,
    can_model_transition,
    metric_delta,
)
