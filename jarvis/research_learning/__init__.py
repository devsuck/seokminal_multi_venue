"""jarvis.research_learning — Research Learning Loop Layer (P12.8). **관찰·분석·기록 전용.**

통제된 피드백 분석 — "무엇이 통했나 / 무엇이 실패했나 / 무엇을 조사해야 하나"를 분석한다. Learning Loop Registry·
Observation Records·Lesson Records·Feedback Records·Improvement Candidates 를 소유한다(+patterns/reports/artifacts).

**자동 개선을 하지 않는다.** 개선 후보는 기록만 하며(applied=False 고정) 절대 자동 적용하지 않는다. execution/broker/
portfolio/risk/permission/deployment/live import·호출 없음. LEARNING ≠ MODIFICATION · LESSON ≠ APPLICATION ·
CANDIDATE ≠ EXECUTION. 불변·append-only 해시체인·이벤트 소싱·결정적·재현. 상위 P12.7·P10.2~P10.8 은 READ ONLY.
물리 원장은 rll_ 접두사(기존 rl_ 계층과 구별).
"""
from jarvis.research_learning.engine import ResearchLearningLoopEngine  # noqa: F401
from jarvis.research_learning.models import (  # noqa: F401
    LEARNING_STATES,
    OBS_VERDICTS,
    ArtifactRecord,
    FeedbackRecord,
    ForbiddenAutoActionError,
    IllegalLearningTransition,
    ImmutableFeedbackError,
    ImmutableImprovementError,
    ImmutableLessonError,
    ImmutableLoopError,
    ImmutableObservationError,
    ImprovementCandidateRecord,
    InvalidVerdict,
    LearningReportRecord,
    LearningSummary,
    LessonRecord,
    LoopEventRecord,
    ObservationRecord,
    PatternRecord,
    UnknownLoopError,
)
