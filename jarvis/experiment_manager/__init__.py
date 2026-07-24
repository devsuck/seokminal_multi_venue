"""jarvis.experiment_manager — Autonomous Experiment Manager (P11.4). **제안 전용.**

AI 보조 실험 생성. 실험 제안·계획·연구 요청·결과 수집을 생성하고 Experiments·Plans·Requests·Results·Reports 를
남긴다. 생애주기 PROPOSED→REVIEWED→APPROVED_FOR_RESEARCH→COMPLETED.

**라이브 전략 실행은 허용되지 않는다. 실행·배포 없음.** APPROVED_FOR_RESEARCH 는 거래 승인이 아니다 — 연구 요청은
항상 research_only=True·trading_approval=False. execution/broker/order/portfolio execution/capital allocation/
live trading/permission/risk controller import·호출 없음. PROPOSAL ≠ EXECUTION · APPROVED_FOR_RESEARCH ≠
TRADING_APPROVAL · RESULT ≠ DEPLOYMENT. 불변·append-only 해시체인·결정적·재현. 물리 원장은 exm_ 접두사.
"""
from jarvis.experiment_manager.engine import ExperimentManagerEngine  # noqa: F401
from jarvis.experiment_manager.models import (  # noqa: F401
    ALLOWED_TRANSITIONS,
    EXPERIMENT_STATES,
    OUTCOMES,
    ExperimentEventRecord,
    ExperimentPlanRecord,
    ExperimentReportRecord,
    ExperimentResultRecord,
    ExperimentStateError,
    ExperimentSummary,
    ForbiddenExecutionError,
    IllegalExperimentTransition,
    ImmutablePlanError,
    ImmutableRequestError,
    ImmutableResultError,
    InvalidOutcome,
    ResearchRequestRecord,
    UnknownExperimentError,
)
