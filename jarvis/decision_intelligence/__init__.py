"""jarvis.decision_intelligence — Research Decision Intelligence Layer (P10.7). **판단 지원 전용.**

여러 연구 결과(P10.2~P10.6)를 READ ONLY 로 소비해 사람이 검토 가능한 형태로 비교·분석한다. 후보
레지스트리·결정 세션·평가 프레임워크(MCDA)·스코어카드·트레이드오프·결정 리포트·계보를 관리한다.

**Decision Intelligence 는 판단 지원만 수행한다.** 자동 전략 선택·trading permission·deployment·capital
allocation·portfolio mutation·model promotion·execution·broker·risk threshold·permission 변경 없음.
Decision output 은 기록 데이터이며 실제 운영 상태를 바꾸지 않는다. score ≠ approval · VALIDATED ≠
SELECTED · RECOMMENDED ≠ DEPLOYABLE. append-only 해시체인·결정적·재현. 물리 원장은 di_ 접두사.
"""
from jarvis.decision_intelligence.engine import ResearchDecisionEngine  # noqa: F401
from jarvis.decision_intelligence.models import (  # noqa: F401
    ARCHIVED,
    COMPARED,
    COMPLETED,
    CREATED,
    EVALUATING,
    REGISTERED,
    REPORTED,
    SCORED,
    UNDER_REVIEW,
    CandidateEvent,
    DecisionArtifact,
    DecisionIntelligenceReport,
    DecisionReport,
    DecisionSessionEvent,
    EvaluationFramework,
    IllegalTransition,
    ImmutableCandidateError,
    ImmutableFrameworkError,
    Scorecard,
    TradeoffAnalysis,
    UnknownCandidate,
    UnknownFramework,
)
