"""jarvis.research_memory_intelligence — Research Knowledge Evolution & Memory Intelligence Layer (P27). **지식 메모리 전용.**

역사적 연구 지식을 진화하는 메모리 시스템으로 결합한다. Research Memory Registry·Knowledge Memories·Research Lessons·
Pattern Records·Failure Memories·Success Memories·Knowledge Evolution Events·Memory Retrieval Records·Evolution
Reports·Memory Lineage 를 소유한다.

**지식 메모리 시스템이다 — 결정하지 않는다. 거래 결정·전략 배포·실험 실행·모델 수정·연구 산출 승인·자본 배분을 하지 않는다.**
execution/broker/live_trading/portfolio_execution import·호출 없음. MEMORY ASSISTS RESEARCH · MEMORY DOES NOT
DECIDE. 진화는 새 append 이벤트로만(과거 메모리 변경 없음). 불변·append-only·해시체인·이벤트 소싱·결정적·재현. 상위
계층(P10~P26)은 READ ONLY. 원장 rmi_ 접두사. P10.5 KG·P20 Research Memory 소유권 불변(중복 없음).
"""
from jarvis.research_memory_intelligence.engine import ResearchMemoryIntelligenceEngine  # noqa: F401
from jarvis.research_memory_intelligence.models import (  # noqa: F401
    CHANGE_TYPES,
    MEMORY_CATEGORIES,
    MEMORY_STATES,
    PATTERN_TYPES,
    ArtifactRecord,
    EvolutionEventRecord,
    EvolutionReportRecord,
    FailureRecord,
    IllegalMemoryTransition,
    LessonRecord,
    MemoryEventRecord,
    MemoryIntelligenceSummary,
    PatternRecord,
    RetrievalRecord,
    SuccessRecord,
    UnknownEntityError,
    can_memory_transition,
    evolve_confidence,
    jaccard,
)
