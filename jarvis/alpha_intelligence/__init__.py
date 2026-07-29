"""jarvis.alpha_intelligence — Alpha Discovery & Signal Intelligence Layer (P10.3). **연구 전용.**

alpha 신호를 발견·후보 관리하고 생명주기(IDEA→HYPOTHESIS→RESEARCHING→EVALUATED→VALIDATED→
ARCHIVED)·피처·가설·실험·평가·랭킹·계보를 관리한다. append-only 해시체인·결정적·재현.

**trading signal 실행·주문 생성·portfolio 영향·자본 배분·자동 선택/배포 없음.** execution/broker/
portfolio/risk/permission import·변경 없음. signal 은 연구 객체 · Alpha score/rank 는 연구 평가값 ·
VALIDATED ≠ trading enabled. 기록·분석 목적만.
"""
from jarvis.alpha_intelligence.engine import AlphaIntelligenceEngine  # noqa: F401
from jarvis.alpha_intelligence.models import (  # noqa: F401
    ARCHIVED,
    EVALUATED,
    FAILED,
    HYPOTHESIS,
    IDEA,
    PASS,
    RESEARCHING,
    VALIDATED,
    WARNING,
    AlphaHypothesis,
    AlphaRanking,
    AlphaReport,
    FeatureDefinition,
    IllegalTransition,
    ImmutableFeatureError,
    ImmutableSignalError,
    ImmutableVersionError,
    SignalArtifact,
    SignalEvaluation,
    SignalExperiment,
    SignalMetadata,
    SignalVersion,
)
