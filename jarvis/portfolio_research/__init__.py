"""jarvis.portfolio_research — Portfolio Research Intelligence Layer (P10.4). **연구 전용.**

포트폴리오 구성 연구·백테스트·리스크 분석을 관리한다. 생명주기(DRAFT→CONSTRUCTED→BACKTESTED→
RISK_ANALYZED→VALIDATED→ARCHIVED)·가설·구성연구(이론적 가중치)·백테스트·리스크분석·비교·계보.
append-only 해시체인·결정적·재현.

**실제 자본 배분·주문·portfolio mutation·live trading·자동 배포 없음.** execution/broker/portfolio/
risk/permission import·변경 없음. portfolio 는 연구 객체 · allocation study 는 이론적 가중치 ·
VALIDATED ≠ deployment. P9.8~P10.3 을 READ ONLY 로 참조. 기록·분석 목적만. 물리 원장은 pr_ 접두사.
"""
from jarvis.portfolio_research.engine import PortfolioResearchEngine  # noqa: F401
from jarvis.portfolio_research.models import (  # noqa: F401
    ARCHIVED,
    BACKTESTED,
    CONSTRUCTED,
    DRAFT,
    FAILED,
    PASS,
    RISK_ANALYZED,
    VALIDATED,
    WARNING,
    ConstructionStudy,
    IllegalTransition,
    ImmutablePortfolioError,
    ImmutableVersionError,
    PortfolioArtifact,
    PortfolioBacktest,
    PortfolioComparison,
    PortfolioHypothesis,
    PortfolioMetadata,
    PortfolioResearchReport,
    PortfolioVersion,
    RiskAnalysis,
)
