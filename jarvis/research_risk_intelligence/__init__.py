"""jarvis.research_risk_intelligence — Research Risk Intelligence Layer (P10.25). **연구 과정 리스크 분석 전용.**

**투자 실행 리스크 아님.** P10.2 Strategy Governance·P10.3 Alpha Intelligence·P10.4 Portfolio Research·
P10.7 Decision Intelligence·P10.8 Simulation 을 **READ ONLY** 로 참조(파일 기반, import 없음)해 과적합·데이터
누수·거짓 발견·복잡도·검증 취약·재현성 리스크를 분석한다. 리스크 레지스트리·리스크 평가·리스크 요인·리스크
리포트·리스크 계보를 제공한다.

**리스크 한도 변경·자본 결정·전략 거부·배포 결정 없음.** execution/broker/order/portfolio execution/capital
allocation/live trading/permission/risk controller import·호출 없음. RISK ANALYSIS ≠ RISK LIMIT CHANGE ·
ASSESSMENT ≠ CAPITAL DECISION · FINDING ≠ STRATEGY REJECTION · SCORE ≠ DEPLOYMENT DECISION. append-only
해시체인·결정적·재현. 물리 원장은 rr_ 접두사.
"""
from jarvis.research_risk_intelligence.engine import ResearchRiskIntelligenceEngine  # noqa: F401
from jarvis.research_risk_intelligence.models import (  # noqa: F401
    ANALYZING,
    ASSESSED,
    CRITICAL,
    PASS,
    RESULTS,
    REVIEWED,
    RISK_CATEGORIES,
    UNKNOWN,
    WARNING,
    IllegalTransition,
    ImmutableAssessmentError,
    ImmutableFactorError,
    InvalidRiskCategory,
    RiskArtifact,
    RiskAssessment,
    RiskEvent,
    RiskFactor,
    RiskReport,
    RiskSummary,
    UnknownRisk,
)
from jarvis.research_risk_intelligence.failure_reasoning import (  # noqa: F401,E402
    RISK_CATEGORIES,
    FailureScenario,
    StrategyRiskReasoner,
    StrategyRiskReport,
)
