"""jarvis.research_experience_memory — Research Memory & Experience Layer (P12.7). **기억·기록·검색 전용.**

장기 연구 기억 — 성공/실패 실험·연구 교훈·검증 결과·에이전트 경험·의사결정 결과를 저장·검색·분석한다. Memory
Registry·Experience Records·Failure Memory·Success Patterns·Research Episodes·Retrieval Index·Memory Summary
를 소유한다.

**실행 능력 없음 — 기억·기록·검색만.** execution/broker/portfolio/risk/permission/deployment/live import·호출
없음. MEMORY ≠ EXECUTION · SIMILARITY ≠ RECOMMENDATION · VALIDATED ≠ DEPLOYED. 유사도는 메타데이터 전용이며 자동
추천을 하지 않는다. 불변·append-only 해시체인·이벤트 소싱·결정적·재현. 상위 P10.2~P10.8·P12.1~P12.6 은 READ ONLY.
물리 원장은 rxm_ 접두사(기존 rm_/rmem_ 계층과 구별).
"""
from jarvis.research_experience_memory.engine import ResearchExperienceMemoryEngine  # noqa: F401
from jarvis.research_experience_memory.models import (  # noqa: F401
    MEMORY_STATES,
    MEMORY_TYPES,
    SIM_KEYS,
    ArtifactRecord,
    DanglingReferenceError,
    EpisodeRecord,
    ExperienceRecord,
    FailureRecord,
    IllegalMemoryTransition,
    ImmutableEpisodeError,
    ImmutableExperienceError,
    ImmutableFailureError,
    ImmutableMemoryError,
    ImmutablePatternError,
    InvalidMemoryType,
    MemoryEventRecord,
    MemorySummary,
    PatternRecord,
    RetrievalRecord,
    SummaryRecord,
    UnknownEpisodeError,
    UnknownMemoryError,
)
