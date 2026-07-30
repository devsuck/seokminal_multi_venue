"""jarvis.research_validation — Research Validation & Reproducibility Governance (P10.9). **평가 기록 전용.**

**ARCHIVED (Phase1 STEP3-B, 2026-07-31):** no active real-import caller found; fully unrelated to the protected jarvis.research_workflow / research/autoresearch validation engine (no shared code paths, disambiguated during Phase1 audit). Retained (not removed) per explicit user instruction citing possible future migration. Migration: no active consumer identified; re-evaluate for full removal in a later phase.

P10.2~P10.8 연구 계층을 READ ONLY 로 소비해 검증 세션·재현성 체크리스트·증거·리플레이 검증·계보
무결성·검증 점수·감사 요약을 기록한다.

**연구 품질 평가 기록만 수행한다.** execution/broker/portfolio mutation/capital allocation/strategy
deployment/model promotion/permission/config/autonomy 변경 없음. VALIDATED ≠ APPROVED · VALIDATED ≠
DEPLOYABLE · score ≠ approval · score ≠ deployment. append-only 해시체인·결정적·재현. 물리 원장 rv_ 접두사.
"""
from jarvis.research_validation.engine import ResearchValidationEngine  # noqa: F401
from jarvis.research_validation.models import (  # noqa: F401
    ARCHIVED,
    COMPLETED,
    CREATED,
    FAILED,
    NON_REPRODUCIBLE,
    PASS,
    REPRODUCIBLE,
    REVIEWED,
    RUNNING,
    WARNING,
    EvidenceRecord,
    IllegalTransition,
    ImmutableValidationError,
    LineageReport,
    ReplayReport,
    ReproducibilityChecklist,
    UnknownValidation,
    ValidationArtifact,
    ValidationAuditSummary,
    ValidationEvent,
    ValidationScore,
    ValidationSession,
)
