"""Strategy Research & Experiment Governance 자료형 (P10.2) — 연구 재현성·실험 관리·검증 기록 전용.

**주문 생성·전략 실행·자본 배분·live trading·자동 승인 없음.** 전략/버전/가설/실험/백테스트/검증/
비교/아티팩트 계보만 — 기록·분석 목적. VALIDATED 는 연구 결과 상태일 뿐 trading permission 아님.
불변·append-only 해시체인·결정적. record_hash = 정렬 canonical json sha256(체인 필드 제외).
물리 원장은 rg_ 접두사(기존 registry.jsonl 과 개념·물리 분리).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

GENESIS = "GENESIS"

# ── Strategy Lifecycle 상태머신 ──
DRAFT = "DRAFT"
RESEARCHING = "RESEARCHING"
BACKTESTED = "BACKTESTED"
VALIDATED = "VALIDATED"
REVIEWED = "REVIEWED"
ARCHIVED = "ARCHIVED"

LIFECYCLE_STATES = (DRAFT, RESEARCHING, BACKTESTED, VALIDATED, REVIEWED, ARCHIVED)

ALLOWED_TRANSITIONS = {
    "": {DRAFT},
    DRAFT: {RESEARCHING},
    RESEARCHING: {BACKTESTED},
    BACKTESTED: {VALIDATED},
    VALIDATED: {REVIEWED},
    REVIEWED: {ARCHIVED},
    ARCHIVED: set(),
}

# ── Validation 결과 ──
PASS = "PASS"
WARNING = "WARNING"
FAILED = "FAILED"

# ── Comparison 추천(기록용 — 자동 선택 아님) ──
A_PREFERRED = "A_PREFERRED"
B_PREFERRED = "B_PREFERRED"
INCONCLUSIVE = "INCONCLUSIVE"

# ── Artifact 유형 ──
ART_STRATEGY = "STRATEGY"
ART_HYPOTHESIS = "HYPOTHESIS"
ART_EXPERIMENT = "EXPERIMENT"
ART_BACKTEST = "BACKTEST"
ART_VALIDATION = "VALIDATION"
ART_COMPARISON = "COMPARISON"

_EPS = 1e-12


class IllegalTransition(Exception):
    """차단된 전략 생명주기 전이."""


class ImmutableStrategyError(Exception):
    """불변 전략 위반."""


class ImmutableVersionError(Exception):
    """불변 전략 버전 위반(동일 strategy+version 내용 상이)."""


def can_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, set())


# ── 해시 ──
def _digest(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def input_digest(*parts) -> str:
    return _digest(list(parts))


def content_hash(record: dict) -> str:
    core = {k: v for k, v in record.items()
            if k not in ("previous_hash", "record_hash", "report_hash")}
    return _digest(core)


def strategy_hash(strategy_id: str, name: str, author: str, asset_class: str,
                  description: str) -> str:
    return _digest({"strategy_id": strategy_id, "name": name, "author": author,
                    "asset_class": asset_class, "description": description})


def version_hash(strategy_id: str, version: str, parameters: dict, dataset_version: str,
                 feature_version: str, model_version: str) -> str:
    return _digest({"strategy_id": strategy_id, "version": version, "parameters": parameters,
                    "dataset_version": dataset_version, "feature_version": feature_version,
                    "model_version": model_version})


def version_key(strategy_id: str, version: str) -> str:
    return f"{strategy_id}@{version}"


def version_event_id(vkey: str, from_state: str, to_state: str) -> str:
    return "SVE:" + hashlib.sha1(
        input_digest(vkey, from_state, to_state).encode()).hexdigest()[:12]


def hypothesis_id(strategy_id: str, statement: str) -> str:
    return "HYP:" + hashlib.sha1(input_digest(strategy_id, statement).encode()).hexdigest()[:12]


def experiment_id(vkey: str, hyp_id: str, params_hash: str, backtest_period: str) -> str:
    return "EXP:" + hashlib.sha1(
        input_digest(vkey, hyp_id, params_hash, backtest_period).encode()).hexdigest()[:12]


def backtest_id(experiment_id_: str, metrics_hash: str) -> str:
    return "BTR:" + hashlib.sha1(
        input_digest(experiment_id_, metrics_hash).encode()).hexdigest()[:12]


def validation_report_id(experiment_id_: str, checks_hash: str) -> str:
    return "VAL:" + hashlib.sha1(
        input_digest(experiment_id_, checks_hash).encode()).hexdigest()[:12]


def comparison_id(experiment_a: str, experiment_b: str) -> str:
    return "CMP:" + hashlib.sha1(
        input_digest(experiment_a, experiment_b).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "ART:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── 검증 상태(6체크 결정적) ──
def validation_status(checks: dict) -> str:
    """검증 체크 → PASS/WARNING/FAILED. **연구 결과 라벨 — trading permission 아님.**

    필수(out-of-sample, walk-forward) 실패 → FAILED. overfitting 경고 또는 비용민감/파라미터
    강건성/벤치마크 미달 → WARNING. 그 외 PASS.
    """
    if not checks.get("out_of_sample_pass", False) or not checks.get("walk_forward_pass", False):
        return FAILED
    if (checks.get("overfitting_warning", False)
            or not checks.get("cost_sensitivity_pass", True)
            or not checks.get("parameter_robustness_pass", True)
            or not checks.get("benchmark_outperforms", True)):
        return WARNING
    return PASS


def comparison_recommendation(sharpe_a: float, sharpe_b: float,
                              margin: float = 0.1) -> str:
    """샤프 비교 기반 추천 라벨(기록만 — 자동 선택 아님)."""
    if abs(sharpe_a - sharpe_b) < margin:
        return INCONCLUSIVE
    return A_PREFERRED if sharpe_a > sharpe_b else B_PREFERRED


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class StrategyMetadata:
    strategy_id: str
    name: str
    description: str
    author: str
    asset_class: str
    created_at: str
    strategy_hash: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class StrategyVersion:
    """버전 생명주기 이벤트(이벤트 소싱). 현재 상태 = 마지막 to_state."""
    version_id: str
    version_key: str
    strategy_id: str
    version: str
    author: str
    parameters: dict
    dataset_version: str
    feature_version: str
    model_version: str
    version_hash: str
    from_state: str
    to_state: str
    status: str
    created_at: str
    actor: str = "system"
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ResearchHypothesis:
    hypothesis_id: str
    strategy_id: str
    statement: str
    rationale: str = ""
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExperimentRun:
    experiment_id: str
    strategy_id: str
    version: str
    hypothesis_id: str
    hypothesis: str
    dataset_version: str
    feature_version: str
    model_version: str
    parameters: dict
    backtest_period: str
    cost_assumption: dict
    benchmark: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class BacktestRecord:
    backtest_id: str
    experiment_id: str
    total_return: float
    volatility: float
    sharpe: float
    max_drawdown: float
    turnover: float
    benchmark_comparison: dict
    backtest_period: str
    cost_assumption: dict
    result_summary: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ValidationReport:
    report_id: str
    experiment_id: str
    checks: dict
    validation_status: str          # PASS | WARNING | FAILED (연구 결과 — 거래 인가 아님)
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExperimentComparison:
    comparison_id: str
    experiment_a: str
    experiment_b: str
    metrics_a: dict
    metrics_b: dict
    deltas: dict
    recommendation: str             # A/B_PREFERRED | INCONCLUSIVE (기록만 — 자동 선택 아님)
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ResearchArtifact:
    artifact_id: str
    artifact_type: str
    ref_id: str
    parent_artifact: str
    strategy_id: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ResearchGovernanceReport:
    timestamp: str
    strategy_count: int
    version_count: int
    state_distribution: dict
    experiment_count: int
    backtest_count: int
    validation_count: int
    validation_pass: int
    validation_warning: int
    validation_failed: int
    comparison_count: int

    def to_dict(self) -> dict:
        return asdict(self)
