"""jarvis.research_insight_intelligence — Research Insight Intelligence & Interpretation Layer (P28). **해석 지능 전용.**

P27 장기 연구 메모리를 연구 통찰·맥락 설명·관계 해석·연구 방향 신호·지식 요약으로 변환한다. Research Insight Registry·
Insight Extraction Events·Context Analysis·Evidence Interpretation·Research Gap Records·Knowledge Summaries·
Insight Relationships·Interpretation Reports·Insight Lineage 를 소유한다.

**전략 선택·가설 승인·모델 배포·실험 실행·거래·자본 배분을 하지 않는다.** execution/broker/live_trading/
portfolio_execution import·호출 없음. INSIGHT ≠ DECISION · INSIGHT ≠ RECOMMENDATION · INSIGHT ≠ STRATEGY.
불변·append-only·해시체인·이벤트 소싱·결정적·재현. 상위 계층(P10~P27)은 READ ONLY. 원장 rii_ 접두사.
"""
from jarvis.research_insight_intelligence.engine import ResearchInsightEngine  # noqa: F401
from jarvis.research_insight_intelligence.models import (  # noqa: F401
    EVIDENCE_TYPES,
    GAP_TYPES,
    INSIGHT_CATEGORIES,
    INSIGHT_STATES,
    RELATION_TYPES,
    ArtifactRecord,
    ContextRecord,
    EvidenceLinkRecord,
    IllegalInsightTransition,
    InsightEventRecord,
    InsightSummary,
    InterpretationRecord,
    InterpretationReportRecord,
    RelationshipRecord,
    ResearchGapRecord,
    UnknownEntityError,
    can_insight_transition,
    interpret_confidence,
    jaccard,
)
