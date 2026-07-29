"""jarvis.production_readiness — Production Readiness & Deployment Governance Layer (P21). **검증·승인 기록·감사 전용.**

연구 결과가 운영으로 넘어가기 전 배포 준비성 검증·승인 기록·전환 조건을 기록·검증·감사만 한다. Production Readiness
Registry·Deployment Candidate Registry·Readiness Checklist·Approval Requirements·Release Evaluation·Deployment
Risk Assessment·Transition History·Reports 를 소유한다.

**배포하지 않는다. 실제 주문·live trading·portfolio mutation·capital allocation·자동 배포·자동 승인을 하지 않는다.**
execution/broker/portfolio_manager/risk_engine/permission_manager import·호출 없음. VALIDATED ≠ DEPLOYED · READY ≠
LIVE. READY_FOR_DEPLOYMENT 는 연구 상태일 뿐 배포하지 않는다. 불변·append-only·해시체인·이벤트 소싱·결정적·재현. 상위
계층(P9.8~P20)은 READ ONLY. 물리 원장 pd_ 접두사.
"""
from jarvis.production_readiness.engine import ProductionReadinessEngine  # noqa: F401
from jarvis.production_readiness.models import (  # noqa: F401
    CANDIDATE_STATES,
    CHECKLIST_CATEGORIES,
    CHECK_STATUSES,
    REQUIREMENT_TYPES,
    REVIEW_STATES,
    RISK_LEVELS,
    ApprovalRequired,
    ArtifactRecord,
    DeploymentCandidateRecord,
    IllegalCandidateTransition,
    IllegalReviewTransition,
    ImmutableCandidateError,
    MissingEvidenceError,
    ReadinessCheckRecord,
    ReadinessReportRecord,
    ReadinessSummary,
    RequirementRecord,
    ReviewerRequired,
    ReviewEventRecord,
    RiskAssessmentRecord,
    TransitionRecord,
    UnknownEntityError,
    can_candidate_transition,
    can_review_transition,
)
