"""jarvis.research_reviewer — AI Research Reviewer Layer (P11.5). **평가·기록 전용.**

연구 품질 AI 비평/리뷰어. 통계적 품질·강건성·재현성·리스크·신규성 5개 차원을 결정적으로 평가해 리뷰 리포트
(PASS·WARNING·REJECT_RESEARCH)를 내고 Reviews·Critiques·Evidence·Reviewer Reports 를 남긴다.

**연구 거부는 전략 삭제가 아니다. 자동 결정 없음.** 평결은 권고일 뿐 어떤 실행/승인/삭제도 하지 않는다.
execution/broker/order/portfolio execution/capital allocation/live trading/permission/risk controller import·
호출 없음. REVIEW ≠ DECISION · REJECT_RESEARCH ≠ DELETE_STRATEGY · VERDICT ≠ ACTION. 불변·append-only 해시체인·
결정적·재현. 물리 원장은 rvw_ 접두사.
"""
from jarvis.research_reviewer.engine import ResearchReviewerEngine  # noqa: F401
from jarvis.research_reviewer.models import (  # noqa: F401
    DIMENSIONS,
    EVIDENCE_TYPES,
    SEVERITIES,
    VERDICTS,
    CritiqueRecord,
    EvidenceRecord,
    ImmutableCritiqueError,
    ImmutableEvidenceError,
    ImmutableReportError,
    ImmutableReviewError,
    InvalidDimension,
    InvalidEvidenceType,
    InvalidScore,
    InvalidSeverity,
    MissingDimensions,
    ReviewRecord,
    ReviewerReportRecord,
    ReviewerSummary,
    UnknownCritiqueError,
    UnknownReviewError,
)
