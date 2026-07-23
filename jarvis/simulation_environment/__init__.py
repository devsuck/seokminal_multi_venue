"""jarvis.simulation_environment — Research Simulation Environment Layer (P10.8). **비실행 분석 전용.**

연구 결과(P10.2~P10.7)를 READ ONLY 로 소비해 다양한 조건(시나리오·파라미터·레짐·스트레스)에서 재현·
검증한다. 시나리오 레지스트리·시뮬레이션 런·파라미터/레짐 시나리오·스트레스 정의·결과·비교·계보를
관리한다.

**Simulation 은 분석 환경이다.** order 생성·trade 실행·portfolio 변경·capital allocation·broker 접근·
live trading·strategy deployment·model promotion 없음. execution/broker/order/portfolio mutation/
risk governor/permission import·호출 없음. 결과는 결정적으로 파생된 평가값(연구 기록)이며 자동 판단·
선택·배포를 하지 않는다. score ≠ selection · result ≠ deployment. append-only 해시체인·결정적·재현.
물리 원장은 sim_ 접두사(execution paper-sim 의 simulation_ 과 구별).
"""
from jarvis.simulation_environment.engine import ResearchSimulationEngine  # noqa: F401
from jarvis.simulation_environment.models import (  # noqa: F401
    ARCHIVED,
    COMPLETED,
    CONFIGURED,
    CREATED,
    CUSTOM,
    HIGH_VOLATILITY,
    LOW_LIQUIDITY,
    MARKET_STRESS,
    NORMAL,
    PARAMETER_SHIFT,
    REVIEWED,
    RUNNING,
    USED,
    IllegalTransition,
    ImmutableRunError,
    ImmutableScenarioError,
    MarketRegimeScenario,
    ParameterScenario,
    ScenarioEvent,
    SimulationArtifact,
    SimulationComparison,
    SimulationEnvironmentReport,
    SimulationResult,
    SimulationRunEvent,
    UnknownRun,
    UnknownScenario,
)
