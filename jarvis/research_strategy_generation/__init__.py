"""jarvis.research_strategy_generation — Research Strategy Generation Intelligence Layer (P29). **생성 전용.**

**REVIVED 2026-08-20** — historical_candidate_bridge를 통해 research_discovery(mode=historical)에서 호출됨.

역사적 지식(P10~P28)에서 연구 전략 후보·가설을 생성한다. Strategy Candidates·Hypotheses·Generation Sessions·
Novelty Analysis·Evidence·Generation Reports 를 소유한다.

**후보를 만든다 — 선택·승인·배포·실행·거래·자본 배분을 하지 않는다.** execution/broker/live_trading/
portfolio_execution import·호출 없음. GENERATED ≠ SELECTED · CANDIDATE ≠ STRATEGY · CANDIDATE ≠ DEPLOYMENT.
불변·append-only·해시체인·이벤트 소싱·결정적·재현. 상위 계층(P10~P28)은 READ ONLY. 원장 rsg_ 접두사.
"""
from jarvis.research_strategy_generation.engine import ResearchStrategyGenerationEngine  # noqa: F401
from jarvis.research_strategy_generation.models import (  # noqa: F401
    CANDIDATE_CATEGORIES,
    CANDIDATE_STATES,
    EVIDENCE_TYPES,
    NOVELTY_LEVELS,
    SESSION_STATES,
    ArtifactRecord,
    CandidateEventRecord,
    EvidenceRecord,
    GenerationReportRecord,
    GenerationSummary,
    HypothesisRecord,
    IllegalCandidateTransition,
    IllegalSessionTransition,
    NoveltyRecord,
    SessionEventRecord,
    UnknownEntityError,
    can_candidate_transition,
    can_session_transition,
    classify_novelty,
    novelty_score,
)
