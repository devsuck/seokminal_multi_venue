"""jarvis.research_governance — Strategy Research & Experiment Governance (P10.2). **연구 관리 전용.**

전략/버전을 불변으로 등록하고 생명주기(DRAFT→RESEARCHING→BACKTESTED→VALIDATED→REVIEWED→
ARCHIVED)·가설·실험·백테스트·검증·비교·아티팩트 계보를 관리한다. append-only 해시체인·결정적·재현.

**주문 생성·전략 실행·자본 배분·live trading·모델/전략 자동 승인 없음.** execution/broker/portfolio/
risk/permission import·변경 없음. VALIDATED 는 연구 결과 상태일 뿐 trading permission 아님. 기록·분석만.
물리 원장은 rg_ 접두사(기존 registry.jsonl 과 분리).
"""
from jarvis.research_governance.engine import ResearchGovernanceEngine  # noqa: F401
from jarvis.research_governance.models import (  # noqa: F401
    ARCHIVED,
    BACKTESTED,
    DRAFT,
    FAILED,
    PASS,
    RESEARCHING,
    REVIEWED,
    VALIDATED,
    WARNING,
    BacktestRecord,
    ExperimentComparison,
    ExperimentRun,
    IllegalTransition,
    ImmutableStrategyError,
    ImmutableVersionError,
    ResearchArtifact,
    ResearchGovernanceReport,
    ResearchHypothesis,
    StrategyMetadata,
    StrategyVersion,
    ValidationReport,
)
