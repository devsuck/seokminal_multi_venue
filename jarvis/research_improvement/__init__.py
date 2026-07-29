"""jarvis.research_improvement — Research Self-Improvement Loop Layer (P11.10). **분석·기록 전용.**

이전 연구 활동을 분석해 개선 기회를 기록하는 계층 — 연구 프로세스 평가·워크플로 개선 발굴·반복 실수 탐지·
효율 분석·지식 재사용 분석·방법론 개선 추적. Improvement Registry·Research Cycle Records·Performance
Observations·Process Metrics·Failure Patterns·Improvement Proposals·Learning Records·Iteration History·
Improvement Reviews·Improvement Reports·Artifact Lineage 를 소유한다.

**이전 연구·전략·모델을 수정하지 않고 배포 승인·자동 실험 실행·설정 변경을 하지 않는다.** ACCEPTED 는 연구
프로세스 수용일 뿐 — 전략/모델/배포 승인·거래 활성화가 아니다. execution/broker/portfolio/risk/permission/
deployment/live import·호출 없음. IMPROVEMENT ≠ EXECUTION · ACCEPTED ≠ DEPLOYMENT · PROPOSAL ≠ APPROVAL.
불변·append-only 해시체인·이벤트 소싱·결정적·재현. 상위 P10.2~P10.8·P11.1~P11.9 는 READ ONLY. 물리 원장은 rimp_.
"""
from jarvis.research_improvement.engine import ResearchImprovementEngine  # noqa: F401
from jarvis.research_improvement.models import (  # noqa: F401
    CATEGORIES,
    DECISIONS,
    IMPROVEMENT_STATES,
    ArtifactRecord,
    CircularLearningError,
    CycleRecord,
    DanglingReferenceError,
    FailureRecord,
    IllegalImprovementTransition,
    ImmutableCycleError,
    ImmutableFailureError,
    ImmutableImprovementError,
    ImmutableLearningError,
    ImmutableObservationError,
    ImmutableReportError,
    ImmutableReviewError,
    ImprovementEventRecord,
    ImprovementReportRecord,
    ImprovementSummary,
    InvalidCategory,
    InvalidDecision,
    IterationRecord,
    LearningRecord,
    MetricRecord,
    MissingSourceError,
    ObservationRecord,
    RegistryRecord,
    ReviewRecord,
    UnknownCycleError,
    UnknownImprovementError,
    UnknownRegistryError,
)
