"""jarvis.continuous_learning — Research Memory & Continuous Learning Layer (P20). **기억·분석 전용.**

과거 연구 경험·가설·성공/실패 실험·재사용 지식을 저장·검색·분석만 한다. Research Memories·Experiment Memories·Failure
Memories·Success Patterns·Research Lessons·Retrieval Indexes·Similarity·Learning Statistics 를 소유한다.

**메모리·분석 계층일 뿐이다. 거래·라이브 신호·모델 수정·전략 배포·자본 배분·자동 승인을 하지 않는다.** execution/broker/
portfolio/permission/deployment/live import·호출 없음. REMEMBER ≠ EXECUTE · RETRIEVE ≠ RECOMMEND · CONFIDENCE ≠
APPROVAL. 불변·append-only·해시체인·이벤트 소싱·결정적·재현. 상위 계층(P10.x/P18/P19)은 READ ONLY. 물리 원장 cl_ 접두사.
"""
from jarvis.continuous_learning.engine import ContinuousLearningEngine  # noqa: F401
from jarvis.continuous_learning.models import (  # noqa: F401
    FAILURE_TYPES,
    LESSON_STATES,
    MEMORY_STATES,
    MEMORY_TYPES,
    ArtifactRecord,
    ExperimentMemoryRecord,
    FailureRecord,
    IllegalTransition,
    ImmutableRecordError,
    LearningMetricRecord,
    LessonEventRecord,
    MemoryEventRecord,
    MemorySummary,
    RetrievalEventRecord,
    ReviewerRequired,
    SuccessPatternRecord,
    UnknownEntityError,
    can_lesson_transition,
    can_memory_transition,
    jaccard,
    metadata_similarity,
)
