"""jarvis.meta_research_intelligence — Meta Research Intelligence Layer (P30). **관찰 전용.**

연구 과정 자체를 연구한다: 연구 효율·검증 품질·실패 빈도·연구 속도·지식 재사용 분석. Meta Metrics·Meta Reports·
Research Quality Records·Optimization Opportunities·Meta Lineage 를 소유한다.

**자동 최적화 없음 — 관찰만.** execution/broker/live_trading/portfolio_execution import·호출 없음. OBSERVATION ≠
OPTIMIZATION · META ≠ EXECUTION · OPPORTUNITY ≠ APPLIED. 불변·append-only·해시체인·결정적·재현. 상위 계층(P10~P29)은
READ ONLY. 원장 mri_ 접두사.
"""
from jarvis.meta_research_intelligence.engine import MetaResearchIntelligenceEngine  # noqa: F401
from jarvis.meta_research_intelligence.models import (  # noqa: F401
    META_METRIC_NAMES,
    OBSERVATION_ASPECTS,
    OPPORTUNITY_AREAS,
    QUALITY_DIMENSIONS,
    ArtifactRecord,
    MetaMetricRecord,
    MetaObservationRecord,
    MetaReportRecord,
    MetaSummary,
    OptimizationOpportunityRecord,
    QualityRecord,
    classify_quality,
    opportunity_priority,
    ratio,
)
