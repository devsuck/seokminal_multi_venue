"""jarvis.research_conflict_resolution — Research Conflict Resolution Layer (P11.9). **리뷰·분석 전용.**

여러 AI 연구 에이전트가 서로 다른 결론·가설·평가·권고를 낼 때 이견을 기록·분석·해소하는 계층. Conflict
Registry·Conflict Cases·Conflicting Claims·Evidence References·Agent Positions·Resolution Sessions·Resolution
Outcomes·Minority Opinions·Consensus Records·Conflict Reports·Artifact Lineage 를 소유한다.

**거래 전략 선택·배포 승인·연구 결과 수정·에이전트 무시·행위 실행을 하지 않는다.** 원본 주장·증거 출처·
에이전트 신원·추론 이력·소수의견을 보존하며 삭제·덮어쓰기가 없다. execution/broker/portfolio/risk/permission/
deployment/live import·호출 없음. CONFLICT ≠ EXECUTION · RESOLUTION ≠ APPROVAL · CONSENSUS ≠ DEPLOYMENT.
불변·append-only 해시체인·이벤트 소싱·결정적·재현. 상위 P11.1/P11.5/P11.6/P11.7/P11.8 은 READ ONLY. 물리 원장은 crf_.
"""
from jarvis.research_conflict_resolution.engine import ResearchConflictResolutionEngine  # noqa: F401
from jarvis.research_conflict_resolution.models import (  # noqa: F401
    CONFLICT_STATES,
    EVIDENCE_TYPES,
    RESOLUTION_TYPES,
    ArtifactRecord,
    ClaimRecord,
    ConflictClosedError,
    ConflictEventRecord,
    ConflictReportRecord,
    ConflictSummary,
    ConsensusRecord,
    EvidenceRecord,
    IllegalConflictTransition,
    ImmutableClaimError,
    ImmutableEvidenceError,
    ImmutableMinorityError,
    ImmutableOutcomeError,
    ImmutablePositionError,
    InvalidEvidenceType,
    InvalidResolutionType,
    MinorityRecord,
    OutcomeRecord,
    PositionRecord,
    RegistryRecord,
    SessionRecord,
    UnknownClaimError,
    UnknownConflictError,
    UnknownRegistryError,
)
