"""jarvis.meta_intelligence — Research Meta Intelligence Layer (P10.12). **연구 과정 메타 분석 전용.**

P10.2~P10.11 연구 이력을 READ ONLY 로 소비해 연구 패턴·방법·결과 이력·실패 패턴·연구 품질·메타
인사이트를 통해 "어떤 연구 접근이 신뢰할 findings 를 내는가"를 분석한다.

**연구 이력 분석만 수행한다.** trading signal 생성·strategy 선택·model 승인·capital 배분·deploy 없음.
execution/broker/portfolio execution/live trading/permission/capital allocation import·호출 없음.
META SCORE ≠ TRADING SCORE · RESEARCH QUALITY ≠ PERFORMANCE GUARANTEE · INSIGHT ≠ DECISION.
append-only 해시체인·결정적·재현. 물리 원장은 mi_ 접두사.
"""
from jarvis.meta_intelligence.engine import ResearchMetaEngine  # noqa: F401
from jarvis.meta_intelligence.models import (  # noqa: F401
    ANALYZED,
    ARCHIVED,
    CLASSIFIED,
    CONFIRMED,
    DISCOVERED,
    FAILED,
    GENERATED,
    HIGH_CONFIDENCE,
    INCONCLUSIVE,
    LOW_CONFIDENCE,
    MEDIUM_CONFIDENCE,
    RECORDED,
    REVIEWED,
    SUCCESS,
    WARNING,
    FailurePattern,
    IllegalTransition,
    ImmutableFailureError,
    ImmutableMethodError,
    ImmutablePatternError,
    InsightEvent,
    InvalidEvolutionLink,
    MetaArtifact,
    MetaReport,
    MetaSummary,
    OutcomeEvent,
    PatternEvent,
    ResearchMethod,
    ResearchQualityScore,
    UnknownInsight,
    UnknownOutcome,
    UnknownPattern,
)
