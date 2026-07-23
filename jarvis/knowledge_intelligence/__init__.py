"""jarvis.knowledge_intelligence — Advanced Research Knowledge Intelligence Layer (P10.27). **분석 전용.**

Research Knowledge Graph 를 상위 인텔리전스로 확장한다. P10.5 Research Knowledge Graph·P10.21 Governance
Memory·P10.26 Research Lifecycle 를 **READ ONLY** 로 참조(파일 기반, import 없음)해 연구 유사도·실패 실험
검색·전략 패밀리 클러스터링·모순 탐지·지식 추천을 수행하고 지식 인사이트·유사도 리포트·클러스터·모순·연구
패턴을 남긴다.

**권고는 정보용일 뿐, 자동 선택·승인·배포 없음.** execution/broker/order/portfolio execution/capital
allocation/live trading/permission/risk controller import·호출 없음. RECOMMENDATION ≠ ACTION · SIMILARITY ≠
SELECTION · CLUSTER ≠ APPROVAL · INSIGHT ≠ DEPLOYMENT. append-only 해시체인·결정적·재현. 물리 원장은 ki_ 접두사.
"""
from jarvis.knowledge_intelligence.engine import KnowledgeIntelligenceEngine  # noqa: F401
from jarvis.knowledge_intelligence.models import (  # noqa: F401
    INSIGHT_TYPES,
    PATTERN_TYPES,
    REFUTES,
    SUPPORTS,
    ClusterRecord,
    ContradictionRecord,
    ImmutableClusterError,
    ImmutableContradictionError,
    ImmutableInsightError,
    ImmutablePatternError,
    ImmutableSimilarityError,
    InvalidInsightType,
    InvalidStance,
    KnowledgeArtifact,
    KnowledgeInsight,
    KnowledgeReport,
    KnowledgeSummary,
    ResearchPattern,
    SimilarityRecord,
)
