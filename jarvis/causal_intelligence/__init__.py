"""jarvis.causal_intelligence — Research Causal Intelligence Layer (P10.11). **연구 인과 분석 전용.**

P10.2~P10.8 연구 계층을 READ ONLY 로 소비해 변수·가설·관계연구·실험·증거·인과 그래프·리포트를 통해
연구 객체 간 인과 관계·의존·설명 가능성을 분석한다.

**모든 산출은 연구 증거일 뿐이다.** trading 실행·signal 생성·portfolio 배분·model 배포·자동 의사결정
없음. execution/broker/portfolio execution/risk governor/permission manager/live trading import·호출
없음. VALIDATED ≠ CAUSALITY PROVEN · CAUSAL SCORE ≠ TRADING PERMISSION · RELATIONSHIP ≠ ACTION.
append-only 해시체인·결정적·재현. 물리 원장은 ci_ 접두사.
"""
from jarvis.causal_intelligence.engine import ResearchCausalEngine  # noqa: F401
from jarvis.causal_intelligence.models import (  # noqa: F401
    ANALYZED,
    ARCHIVED,
    COMPLETED,
    CONNECTED,
    CREATED,
    DRAFT,
    EVIDENCED,
    INCONCLUSIVE,
    MODERATE,
    REGISTERED,
    REVIEWED,
    RUNNING,
    SNAPSHOTTED,
    STRONG,
    TESTING,
    WEAK,
    CausalArtifact,
    CausalCycleError,
    CausalReport,
    CausalSummary,
    Evidence,
    ExperimentEvent,
    GraphEvent,
    HypothesisEvent,
    IllegalTransition,
    ImmutableHypothesisError,
    ImmutableVariableError,
    RelationshipStudy,
    UnknownExperiment,
    UnknownHypothesis,
    UnknownVariable,
    Variable,
)
