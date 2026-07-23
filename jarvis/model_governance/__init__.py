"""jarvis.model_governance — Model Governance & AI Oversight Layer (P9.9). **관리·감사 전용.**

모델/버전을 불변으로 등록하고 생명주기(DRAFT→TRAINED→EVALUATED→APPROVED→DEPLOYED_CANDIDATE→
RETIRED)·학습메타·평가·승인·배포기록·drift 를 관리한다. append-only 해시체인·결정적·재현가능.

**모델 실행·학습 실행·배포 실행·trading decision 없음.** live execution/broker/portfolio/risk거버너/
order 생성/자동 배포 없음. APPROVED/DEPLOYED_CANDIDATE 는 기록일 뿐 실제 모델/거래 시스템 무영향.
물리 원장은 mg_ 접두사(기존 approvals/drift_reports 원장과 충돌 회피).
"""
from jarvis.model_governance.engine import ModelGovernanceEngine  # noqa: F401
from jarvis.model_governance.models import (  # noqa: F401
    APPROVED,
    CRITICAL_DRIFT,
    DEPLOYED_CANDIDATE,
    DRAFT,
    EVALUATED,
    NO_DRIFT,
    REJECTED,
    RETIRED,
    TRAINED,
    WARNING_DRIFT,
    ApprovalError,
    DeploymentRecord,
    EvaluationReport,
    IllegalTransition,
    ImmutableModelError,
    ImmutableVersionError,
    ModelApproval,
    ModelDriftReport,
    ModelGovernanceReport,
    ModelMetadata,
    ModelVersion,
    TrainingRun,
)
