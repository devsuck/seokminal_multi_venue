"""jarvis.governance_evolution — Research Governance Evolution Intelligence Layer (P10.22). **분석 전용.**

P9.8~P10.21 전 계층을 **READ ONLY** 로 참조(파일 기반, import 없음)해 거버넌스 생태계가 시간에 따라 어떻게
변화하는지 분석한다. 진화 이벤트 레지스트리·거버넌스 상태 타임라인·성숙도 평가·변화 패턴 분석·진화 스냅샷·
역사적 비교·진화 리포트·진화 계보를 제공하며 성숙도 성장·반복 구조 변화·역량 진화·역사적 전이·장기 추세를 추적한다.

**거버넌스 규칙 수정·변경 적용·업그레이드 승인·config 변경·시스템 배포 없음.** execution/broker/order/portfolio
execution/capital allocation/live trading/permission/risk controller import·호출 없음. EVOLUTION ANALYSIS ≠
EVOLUTION ACTION · MATURITY SCORE ≠ PERMISSION · TREND DETECTION ≠ CHANGE EXECUTION · RECOMMENDATION ≠
IMPLEMENTATION. append-only 해시체인·결정적·재현. 물리 원장은 ge_ 접두사.
"""
from jarvis.governance_evolution.engine import GovernanceEvolutionEngine  # noqa: F401
from jarvis.governance_evolution.models import (  # noqa: F401
    DEFINED,
    DEVELOPING,
    EVENT_TYPES,
    INITIAL,
    MANAGED,
    MATURITY_DIMENSIONS,
    MATURITY_LEVELS,
    OPTIMIZING,
    EvolutionArtifact,
    EvolutionEvent,
    EvolutionPattern,
    EvolutionReport,
    EvolutionSnapshot,
    EvolutionSummary,
    GovernanceStateEvent,
    HistoricalComparison,
    IllegalTransition,
    ImmutableEventError,
    ImmutableMaturityError,
    ImmutablePatternError,
    InvalidEventType,
    InvalidMaturityLevel,
    MaturityAssessment,
    UnknownState,
)
