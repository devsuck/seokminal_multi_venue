"""Portfolio Research Intelligence 자료형 (P10.4) — 포트폴리오 구성 연구·백테스트·리스크 분석 전용.

**실제 자본 배분·주문·portfolio mutation·live trading·자동 배포 없음.** portfolio 는 연구 객체이고
allocation study 는 이론적 가중치(실제 자본 아님). Construction/backtest/risk 는 연구 평가값 ·
VALIDATED ≠ deployment. 불변·append-only 해시체인·결정적. 기록·분석 목적만. 물리 원장은 pr_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

GENESIS = "GENESIS"

# ── Portfolio Research Lifecycle 상태머신 ──
DRAFT = "DRAFT"
CONSTRUCTED = "CONSTRUCTED"
BACKTESTED = "BACKTESTED"
RISK_ANALYZED = "RISK_ANALYZED"
VALIDATED = "VALIDATED"
ARCHIVED = "ARCHIVED"

LIFECYCLE_STATES = (DRAFT, CONSTRUCTED, BACKTESTED, RISK_ANALYZED, VALIDATED, ARCHIVED)

ALLOWED_TRANSITIONS = {
    "": {DRAFT},
    DRAFT: {CONSTRUCTED},
    CONSTRUCTED: {BACKTESTED},
    BACKTESTED: {RISK_ANALYZED},
    RISK_ANALYZED: {VALIDATED},
    VALIDATED: {ARCHIVED},
    ARCHIVED: set(),
}

# ── Risk verdict ──
PASS = "PASS"
WARNING = "WARNING"
FAILED = "FAILED"

# ── Comparison 추천(기록용 — 자동 선택 아님) ──
A_PREFERRED = "A_PREFERRED"
B_PREFERRED = "B_PREFERRED"
INCONCLUSIVE = "INCONCLUSIVE"

# ── Artifact 유형 ──
ART_PORTFOLIO = "PORTFOLIO"
ART_HYPOTHESIS = "HYPOTHESIS"
ART_CONSTRUCTION = "CONSTRUCTION"
ART_BACKTEST = "BACKTEST"
ART_RISK = "RISK_ANALYSIS"

# ── 연구 구성 방법 라벨(서술 — 실제 배분 아님) ──
CONSTRUCTION_METHODS = ("equal_weight", "risk_parity", "max_sharpe", "min_variance",
                        "signal_weighted", "hierarchical")

_EPS = 1e-9


class IllegalTransition(Exception):
    """차단된 포트폴리오 연구 생명주기 전이."""


class ImmutablePortfolioError(Exception):
    """불변 포트폴리오 연구 위반."""


class ImmutableVersionError(Exception):
    """불변 포트폴리오 버전 위반(동일 portfolio+version 내용 상이)."""


def can_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, set())


def _clamp(x, lo=0.0, hi=100.0):
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


def portfolio_hash(portfolio_id: str, name: str, author: str, objective: str,
                   description: str) -> str:
    return _digest({"portfolio_id": portfolio_id, "name": name, "author": author,
                    "objective": objective, "description": description})


def version_hash(portfolio_id: str, version: str, construction_method: str,
                 signal_universe: list, constraints: dict, dataset_version: str) -> str:
    return _digest({"portfolio_id": portfolio_id, "version": version,
                    "construction_method": construction_method,
                    "signal_universe": sorted(signal_universe or []),
                    "constraints": constraints, "dataset_version": dataset_version})


def version_key(portfolio_id: str, version: str) -> str:
    return f"{portfolio_id}@{version}"


def version_event_id(vkey: str, from_state: str, to_state: str) -> str:
    return "PVE:" + hashlib.sha1(
        input_digest(vkey, from_state, to_state).encode()).hexdigest()[:12]


def hypothesis_id(portfolio_id: str, statement: str) -> str:
    return "PHY:" + hashlib.sha1(input_digest(portfolio_id, statement).encode()).hexdigest()[:12]


def study_id(vkey: str, method: str, weights_hash: str) -> str:
    return "PCS:" + hashlib.sha1(
        input_digest(vkey, method, weights_hash).encode()).hexdigest()[:12]


def backtest_id(study_id_: str, metrics_hash: str) -> str:
    return "PBT:" + hashlib.sha1(input_digest(study_id_, metrics_hash).encode()).hexdigest()[:12]


def risk_analysis_id(study_id_: str, metrics_hash: str) -> str:
    return "PRA:" + hashlib.sha1(input_digest(study_id_, metrics_hash).encode()).hexdigest()[:12]


def comparison_id(portfolio_a: str, portfolio_b: str) -> str:
    return "PCM:" + hashlib.sha1(
        input_digest(portfolio_a, portfolio_b).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "PRA_:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── 연구 검증 헬퍼 ──
def normalize_weights(weights: dict) -> dict:
    total = sum(abs(float(w)) for w in (weights or {}).values())
    if total < _EPS:
        return dict(weights or {})
    return {k: round(float(v) / total, 8) for k, v in weights.items()}


def concentration_hhi(weights: dict) -> float:
    """Herfindahl-Hirschman 집중도(0~1, 높을수록 집중). 연구 지표."""
    norm = normalize_weights(weights)
    return round(sum(w * w for w in norm.values()), 8) if norm else 0.0


def risk_verdict(metrics: dict) -> str:
    """리스크 지표 → PASS/WARNING/FAILED (연구 라벨 — 배분/배포 아님)."""
    max_w = abs(float(metrics.get("max_weight", 0.0)))
    n = int(metrics.get("n_holdings", 0))
    conc = float(metrics.get("concentration", 0.0))
    var95 = abs(float(metrics.get("var_95", 0.0)))
    if n < 2 or max_w > 0.5:
        return FAILED
    if max_w > 0.3 or conc > 0.5 or var95 > 0.1:
        return WARNING
    return PASS


def comparison_recommendation(sharpe_a: float, sharpe_b: float, margin: float = 0.1) -> str:
    if abs(sharpe_a - sharpe_b) < margin:
        return INCONCLUSIVE
    return A_PREFERRED if sharpe_a > sharpe_b else B_PREFERRED


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
class PortfolioMetadata:
    portfolio_id: str
    name: str
    description: str
    author: str
    objective: str                  # 연구 목표 라벨(max_sharpe/risk_parity 등)
    created_at: str
    portfolio_hash: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PortfolioVersion:
    version_id: str
    version_key: str
    portfolio_id: str
    version: str
    author: str
    construction_method: str
    signal_universe: list           # 연구 대상 신호 참조(P10.3 signal_id 문자열)
    constraints: dict
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
class PortfolioHypothesis:
    hypothesis_id: str
    portfolio_id: str
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
class ConstructionStudy:
    """신호 배분 연구 — **이론적 가중치(실제 자본 배분 아님).**"""
    study_id: str
    portfolio_id: str
    version: str
    method: str
    weights: dict                   # {signal_id: weight} 연구 가중치(정규화)
    rebalance_frequency: str
    concentration: float
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PortfolioBacktest:
    backtest_id: str
    study_id: str
    portfolio_id: str
    total_return: float
    volatility: float
    sharpe: float
    max_drawdown: float
    turnover: float
    diversification: float
    benchmark_comparison: dict
    period: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RiskAnalysis:
    analysis_id: str
    study_id: str
    portfolio_id: str
    metrics: dict                   # var_95/cvar_95/concentration/max_weight/n_holdings/...
    risk_verdict: str               # PASS | WARNING | FAILED (연구 라벨)
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PortfolioComparison:
    comparison_id: str
    portfolio_a: str
    portfolio_b: str
    metrics_a: dict
    metrics_b: dict
    deltas: dict
    recommendation: str             # 기록만 — 자동 선택 아님
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PortfolioArtifact:
    artifact_id: str
    artifact_type: str
    ref_id: str
    parent_artifact: str
    portfolio_id: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PortfolioResearchReport:
    timestamp: str
    portfolio_count: int
    version_count: int
    state_distribution: dict
    hypothesis_count: int
    construction_count: int
    backtest_count: int
    risk_analysis_count: int
    risk_pass: int
    risk_warning: int
    risk_failed: int
    comparison_count: int

    def to_dict(self) -> dict:
        return asdict(self)
