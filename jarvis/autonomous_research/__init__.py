"""jarvis.autonomous_research — Autonomous Research Loop & Continuous Improvement Layer (P25). **연구 지능 전용.**

이전 연구 결과를 분석, 개선 기회를 식별, 연구 제안을 생성, 실험 계획을 작성, 개선 사이클을 추적, 실패·성공에서 학습한다.
Autonomous Research Loop Registry·Improvement Cycle Records·Research Opportunity Detection·Research Proposal
Records·Experiment Recommendation Records·Learning Feedback Records·Evolution Reports·Research Intelligence
Lineage 를 소유한다.

**루프는 지식을 만든다 — 거래 행위를 만들지 않는다. 실험 자동 실행·전략 배포·모델 승인·거래·자본 배분·프로덕션 수정을
하지 않는다.** execution/broker/live_trading/portfolio_execution import·호출 없음. LOOP CREATES KNOWLEDGE ≠
TRADING ACTIONS · PROPOSAL ≠ APPROVAL · PLAN ≠ EXECUTION. 불변·append-only·해시체인·이벤트 소싱·결정적·재현.
상위 계층(P10~P24)은 READ ONLY. 원장 ar_ 접두사.
"""
from jarvis.autonomous_research.engine import AutonomousResearchEngine  # noqa: F401
from jarvis.autonomous_research.models import (  # noqa: F401
    CYCLE_STATES,
    LEARNING_KINDS,
    OPPORTUNITY_PATTERNS,
    PRIORITY_LEVELS,
    PROPOSAL_STATES,
    RISK_LEVELS,
    ArtifactRecord,
    CycleEventRecord,
    EvolutionReportRecord,
    ExperimentPlanRecord,
    IllegalCycleTransition,
    IllegalProposalTransition,
    LearningEventRecord,
    LearningFeedbackRecord,
    OpportunityRecord,
    ProposalEventRecord,
    ResearchLoopSummary,
    ReviewerRequired,
    UnknownEntityError,
    can_cycle_transition,
    can_proposal_transition,
    classify_priority,
    priority_score,
)
