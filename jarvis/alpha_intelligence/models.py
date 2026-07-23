"""Alpha Discovery & Signal Intelligence 자료형 (P10.3) — alpha 신호 발견·후보 관리·검증 기록 전용.

**실제 trading signal 실행·주문 생성·portfolio 영향·자본 배분·자동 선택/배포 없음.** signal 은 연구
객체일 뿐 trading instruction 이 아님. Alpha score/rank 는 연구 평가값. VALIDATED ≠ trading enabled.
불변·append-only 해시체인·결정적. record_hash = 정렬 canonical json sha256(체인 필드 제외). 기록·분석만.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

GENESIS = "GENESIS"

# ── Signal Lifecycle 상태머신 ──
IDEA = "IDEA"
HYPOTHESIS = "HYPOTHESIS"
RESEARCHING = "RESEARCHING"
EVALUATED = "EVALUATED"
VALIDATED = "VALIDATED"
ARCHIVED = "ARCHIVED"

LIFECYCLE_STATES = (IDEA, HYPOTHESIS, RESEARCHING, EVALUATED, VALIDATED, ARCHIVED)

ALLOWED_TRANSITIONS = {
    "": {IDEA},
    IDEA: {HYPOTHESIS},
    HYPOTHESIS: {RESEARCHING},
    RESEARCHING: {EVALUATED},
    EVALUATED: {VALIDATED},
    VALIDATED: {ARCHIVED},
    ARCHIVED: set(),
}

# ── Evaluation 결과 ──
PASS = "PASS"
WARNING = "WARNING"
FAILED = "FAILED"

# ── Artifact 유형 ──
ART_SIGNAL = "SIGNAL"
ART_FEATURE = "FEATURE"
ART_HYPOTHESIS = "HYPOTHESIS"
ART_EXPERIMENT = "EXPERIMENT"
ART_EVALUATION = "EVALUATION"

_ROBUSTNESS_KEYS = ("out_of_sample_pass", "walk_forward_pass", "parameter_sensitivity_pass",
                    "market_regime_pass", "cost_sensitivity_pass")
_EPS = 1e-12


class IllegalTransition(Exception):
    """차단된 신호 생명주기 전이."""


class ImmutableSignalError(Exception):
    """불변 신호 위반."""


class ImmutableVersionError(Exception):
    """불변 신호 버전 위반(동일 signal+version 내용 상이)."""


class ImmutableFeatureError(Exception):
    """불변 피처 정의 위반."""


def can_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, set())


def _clamp(x, lo=0, hi=100):
    return max(lo, min(hi, x))


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


def signal_hash(signal_id: str, name: str, author: str, category: str, description: str) -> str:
    return _digest({"signal_id": signal_id, "name": name, "author": author,
                    "category": category, "description": description})


def version_hash(signal_id: str, version: str, formula_description: str, parameters: dict,
                 feature_dependencies: list, dataset_version: str) -> str:
    return _digest({"signal_id": signal_id, "version": version,
                    "formula_description": formula_description, "parameters": parameters,
                    "feature_dependencies": sorted(feature_dependencies or []),
                    "dataset_version": dataset_version})


def feature_hash(feature_id: str, name: str, source_dataset: str, formula: str,
                 calculation_version: str) -> str:
    return _digest({"feature_id": feature_id, "name": name, "source_dataset": source_dataset,
                    "formula": formula, "calculation_version": calculation_version})


def version_key(signal_id: str, version: str) -> str:
    return f"{signal_id}@{version}"


def version_event_id(vkey: str, from_state: str, to_state: str) -> str:
    return "SVE:" + hashlib.sha1(
        input_digest(vkey, from_state, to_state).encode()).hexdigest()[:12]


def hypothesis_id(signal_id: str, statement: str) -> str:
    return "AHY:" + hashlib.sha1(input_digest(signal_id, statement).encode()).hexdigest()[:12]


def experiment_id(vkey: str, hyp_id: str, params_hash: str, evaluation_period: str) -> str:
    return "AEX:" + hashlib.sha1(
        input_digest(vkey, hyp_id, params_hash, evaluation_period).encode()).hexdigest()[:12]


def evaluation_id(experiment_id_: str, metrics_hash: str) -> str:
    return "AEV:" + hashlib.sha1(
        input_digest(experiment_id_, metrics_hash).encode()).hexdigest()[:12]


def ranking_id(input_hash_: str) -> str:
    return "ARK:" + hashlib.sha1(input_hash_.encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "SGA:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── 평가 verdict(연구 라벨 — trading enabled 아님) ──
def evaluation_verdict(robustness: dict, sharpe: float) -> str:
    if not robustness.get("out_of_sample_pass", False) or not robustness.get("walk_forward_pass", False):
        return FAILED
    soft = all(robustness.get(k, True) for k in
               ("parameter_sensitivity_pass", "market_regime_pass", "cost_sensitivity_pass"))
    if not soft or sharpe < 0.5:
        return WARNING
    return PASS


# ── Alpha 점수(연구 평가값 — trading decision 아님) ──
def performance_score(sharpe: float) -> int:
    return int(_clamp(round((float(sharpe) / 2.0) * 100.0)))


def robustness_score(robustness: dict) -> int:
    passed = sum(1 for k in _ROBUSTNESS_KEYS if robustness.get(k, False))
    return int(round(passed / len(_ROBUSTNESS_KEYS) * 100.0))


def stability_score(max_drawdown: float, volatility: float) -> int:
    dd_pen = abs(float(max_drawdown)) * 300.0
    vol_pen = abs(float(volatility)) * 50.0
    return int(_clamp(round(100.0 - dd_pen - vol_pen)))


def overall_score(perf: int, robust: int, stability: int) -> int:
    return int(round(0.5 * perf + 0.3 * robust + 0.2 * stability))


def detect_cycle(edges: list) -> list:
    graph: dict = {}
    for a, b in edges:
        graph.setdefault(a, set()).add(b)
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict = {}
    path: list = []

    def dfs(node) -> list:
        color[node] = GRAY
        path.append(node)
        for nxt in sorted(graph.get(node, ())):
            c = color.get(nxt, WHITE)
            if c == GRAY:
                return path[path.index(nxt):] + [nxt]
            if c == WHITE:
                r = dfs(nxt)
                if r:
                    return r
        path.pop()
        color[node] = BLACK
        return []

    for node in sorted(graph):
        if color.get(node, WHITE) == WHITE:
            r = dfs(node)
            if r:
                return r
    return []


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class SignalMetadata:
    signal_id: str
    name: str
    description: str
    author: str
    category: str
    created_at: str
    signal_hash: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SignalVersion:
    """버전 생명주기 이벤트(이벤트 소싱). 현재 상태 = 마지막 to_state."""
    version_id: str
    version_key: str
    signal_id: str
    version: str
    author: str
    formula_description: str
    parameters: dict
    feature_dependencies: list
    dataset_version: str
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
class AlphaHypothesis:
    hypothesis_id: str
    signal_id: str
    version: str
    statement: str
    rationale: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FeatureDefinition:
    feature_hash: str
    feature_id: str
    name: str
    description: str
    source_dataset: str
    formula: str
    calculation_version: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SignalExperiment:
    experiment_id: str
    signal_id: str
    version: str
    hypothesis_id: str
    feature_dependencies: list
    dataset_version: str
    parameters: dict
    evaluation_period: str
    benchmark: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SignalEvaluation:
    evaluation_id: str
    experiment_id: str
    signal_id: str
    performance: dict                # return/volatility/sharpe/max_drawdown/turnover
    robustness: dict                 # oos/walk-forward/param/regime/cost
    verdict: str                     # PASS | WARNING | FAILED (연구 라벨)
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AlphaRanking:
    ranking_id: str
    timestamp: str
    rankings: list                   # [{signal_id, performance_score, robustness_score,
                                     #   stability_score, overall_score, rank}]
    note: str = "research_ranking_only_no_auto_selection"
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SignalArtifact:
    artifact_id: str
    artifact_type: str
    ref_id: str
    parent_artifact: str
    signal_id: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AlphaReport:
    timestamp: str
    signal_count: int
    version_count: int
    state_distribution: dict
    feature_count: int
    hypothesis_count: int
    experiment_count: int
    evaluation_count: int
    evaluation_pass: int
    evaluation_warning: int
    evaluation_failed: int
    ranking_count: int

    def to_dict(self) -> dict:
        return asdict(self)
