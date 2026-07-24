"""jarvis.research_literature — Research Literature Intelligence (P11.3). **읽기·기록 전용.**

외부 지식(논문)과 연구 시스템을 연결한다. 논문 메타데이터·개념 추출·전략 아이디어 추출·인용 그래프·연구 비교를
수행하고 Papers·Concepts·Citations·Knowledge Links·Comparisons 를 남긴다. 연구 OS 는 **READ ONLY** 로만 참조
(파일 기반, import 없음).

**자동 전략 생성 없음 — 전략 아이디어는 정보용 개념일 뿐이다.** execution/broker/order/portfolio execution/
capital allocation/live trading/permission/risk controller import·호출 없음. LITERATURE ≠ STRATEGY · IDEA ≠
DEPLOYMENT · CITATION ≠ EXECUTION. 불변·append-only 해시체인·결정적·재현. 물리 원장은 rli_ 접두사.
"""
from jarvis.research_literature.engine import ResearchLiteratureEngine  # noqa: F401
from jarvis.research_literature.models import (  # noqa: F401
    CONCEPT_TYPES,
    LINK_TYPES,
    STRATEGY_IDEA,
    CitationRecord,
    ComparisonRecord,
    ConceptRecord,
    ImmutableCitationError,
    ImmutableComparisonError,
    ImmutableConceptError,
    ImmutableLinkError,
    ImmutablePaperError,
    InvalidConceptType,
    InvalidLinkType,
    KnowledgeLinkRecord,
    LiteratureSummary,
    PaperRecord,
    SelfCitationError,
    UnknownConceptError,
    UnknownPaperError,
)
