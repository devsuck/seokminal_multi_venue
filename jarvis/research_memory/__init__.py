"""jarvis.research_memory — Research Memory Intelligence Layer (P10.14). **연구 기억 보존·검색 전용.**

P10.5·P10.7·P10.8·P10.11·P10.12·P10.13 을 READ ONLY 로 소비해 성공 패턴·실패 실험·발견 인사이트·
재사용 방법론·연구 교훈·역사적 맥락을 장기 기억으로 보존·검색·연결한다.

**연구 실행·trading signal 생성·strategy 선택·model 수정·deploy·자동 학습 갱신·자동 의사결정 없음.**
execution/broker/portfolio execution/risk execution/permission/capital allocation import·호출 없음.
MEMORY ≠ DECISION · RECALL ≠ APPROVAL · SIMILARITY ≠ VALIDATION. append-only 해시체인·결정적·재현.
물리 원장은 rm_ 접두사.
"""
from jarvis.research_memory.engine import ResearchMemoryEngine  # noqa: F401
from jarvis.research_memory.models import (  # noqa: F401
    ARCHIVED,
    CONNECTED,
    FAILURE,
    HIGH,
    INSIGHT,
    LESSON,
    LOW,
    MEDIUM,
    METHOD,
    PATTERN,
    RETRIEVED,
    STORED,
    IllegalTransition,
    ImmutableLessonError,
    ImmutableMemoryError,
    ImmutablePatternError,
    InvalidConnection,
    MemoryArtifact,
    MemoryCluster,
    MemoryConnection,
    MemoryEvent,
    MemoryPattern,
    MemoryReport,
    MemorySummary,
    ResearchLesson,
    RetrievalRecord,
    UnknownMemory,
)
