"""Research Simulation Environment 자료형 (P10.8) — 연구 결과 재현·검증 비실행 시뮬레이션 전용.

연구 결과(P10.2~P10.7)를 **READ ONLY** 로 소비해 다양한 조건(레짐·파라미터·스트레스)에서 재현·검증한다.
**Simulation 은 분석 환경이다.** order 생성·trade 실행·portfolio 변경·capital allocation·broker 접근·
live trading·strategy deployment·model promotion 없음. Simulation 결과는 연구 기록일 뿐이며 자동 판단·
선택·배포를 하지 않는다. score ≠ selection · result ≠ deployment. 불변·append-only 해시체인·결정적.
물리 원장은 sim_ 접두사(execution paper-sim 의 simulation_ 과 구별).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

GENESIS = "GENESIS"
_EPS = 1e-9

# ── Scenario 생명주기 ──
CREATED = "CREATED"
CONFIGURED = "CONFIGURED"
USED = "USED"
ARCHIVED = "ARCHIVED"

SCENARIO_STATES = (CREATED, CONFIGURED, USED, ARCHIVED)
SCENARIO_TRANSITIONS = {
    "": {CREATED},
    CREATED: {CONFIGURED},
    CONFIGURED: {USED},
    USED: {ARCHIVED},
    ARCHIVED: set(),
}

# ── Simulation Run 생명주기 ──
RUNNING = "RUNNING"
COMPLETED = "COMPLETED"
REVIEWED = "REVIEWED"
# CREATED / ARCHIVED 공유

RUN_STATES = (CREATED, RUNNING, COMPLETED, REVIEWED, ARCHIVED)
RUN_TRANSITIONS = {
    "": {CREATED},
    CREATED: {RUNNING},
    RUNNING: {COMPLETED},
    COMPLETED: {REVIEWED},
    REVIEWED: {ARCHIVED},
    ARCHIVED: set(),
}

# ── Scenario 유형 ──
NORMAL = "NORMAL"
HIGH_VOLATILITY = "HIGH_VOLATILITY"
LOW_LIQUIDITY = "LOW_LIQUIDITY"
MARKET_STRESS = "MARKET_STRESS"
PARAMETER_SHIFT = "PARAMETER_SHIFT"
CUSTOM = "CUSTOM"
SCENARIO_TYPES = (NORMAL, HIGH_VOLATILITY, LOW_LIQUIDITY, MARKET_STRESS, PARAMETER_SHIFT, CUSTOM)

# ── Market Regime ──
BULL = "bull"
BEAR = "bear"
SIDEWAYS = "sideways"
REGIME_HIGH_VOL = "high_volatility"
REGIMES = (BULL, BEAR, SIDEWAYS, REGIME_HIGH_VOL)

# ── Parameter / Stress 카테고리 ──
LOOKBACK = "LOOKBACK"
COST_SHOCK = "COST_SHOCK"
RISK_SHOCK = "RISK_SHOCK"
DATASET_SHIFT = "DATASET_SHIFT"
GENERIC = "GENERIC"
PARAMETER_CATEGORIES = (LOOKBACK, COST_SHOCK, RISK_SHOCK, DATASET_SHIFT, GENERIC)

# ── Result 지표 ──
RESULT_METRICS = ("return", "volatility", "sharpe", "max_drawdown", "turnover",
                  "stability_score", "confidence")

# ── Artifact 유형(계보) ──
ART_CANDIDATE = "CANDIDATE"
ART_SCENARIO = "SCENARIO"
ART_RUN = "RUN"
ART_RESULT = "RESULT"
ART_COMPARISON = "COMPARISON"
ART_REPORT = "REPORT"


class IllegalTransition(Exception):
    """차단된 생명주기 전이."""


class ImmutableScenarioError(Exception):
    """불변 시나리오 위반(동일 scenario_id 내용 상이)."""


class ImmutableRunError(Exception):
    """불변 시뮬레이션 런 위반(동일 run_id 입력 상이)."""


class UnknownScenario(Exception):
    """미등록 시나리오 참조."""


class UnknownRun(Exception):
    """미등록 런 참조."""


def _can(table: dict, frm: str, to: str) -> bool:
    return to in table.get(frm, set())


def can_transition_scenario(frm: str, to: str) -> bool:
    return _can(SCENARIO_TRANSITIONS, frm, to)


def can_transition_run(frm: str, to: str) -> bool:
    return _can(RUN_TRANSITIONS, frm, to)


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


def params_hash(params: dict) -> str:
    return _digest(dict(params or {}))


# ── 결정적 ID ──
def scenario_id(name: str, scenario_type: str) -> str:
    return "SSC:" + hashlib.sha1(input_digest(name, scenario_type).encode()).hexdigest()[:12]


def scenario_event_id(sid: str, frm: str, to: str) -> str:
    return "SSE:" + hashlib.sha1(input_digest(sid, frm, to).encode()).hexdigest()[:12]


def run_id(candidate_reference: str, scenario_reference: str, param_hash: str,
           dataset_reference: str, seed: str) -> str:
    return "SRN:" + hashlib.sha1(
        input_digest(candidate_reference, scenario_reference, param_hash, dataset_reference,
                     seed).encode()).hexdigest()[:12]


def run_event_id(rid: str, frm: str, to: str) -> str:
    return "SRE:" + hashlib.sha1(input_digest(rid, frm, to).encode()).hexdigest()[:12]


def parameter_id(name: str, category: str, params: dict) -> str:
    return "SPR:" + hashlib.sha1(
        input_digest(name, category, params_hash(params)).encode()).hexdigest()[:12]


def regime_id(name: str, regime: str) -> str:
    return "SRG:" + hashlib.sha1(input_digest(name, regime).encode()).hexdigest()[:12]


def result_id(run_id_: str) -> str:
    return "SRS:" + hashlib.sha1(input_digest(run_id_).encode()).hexdigest()[:12]


def comparison_id(run_a: str, run_b: str) -> str:
    a, b = sorted((run_a, run_b))
    return "SCM:" + hashlib.sha1(input_digest(a, b).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "SIA:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── 결정적 결과 파생(재현 가능한 시뮬레이션 산출) ──
def derive_metrics(seed_input: str) -> dict:
    """입력(run_id+seed)에서 결정적으로 연구 지표를 파생. 동일 입력 → 동일 산출(재현성).

    **평가값일 뿐 — 실제 거래/체결/손익 아님. 자동 판단 없음.**
    """
    h = hashlib.sha256(seed_input.encode()).hexdigest()  # 64 hex

    def f(i: int) -> float:
        return int(h[i * 8:(i + 1) * 8], 16) / 0xFFFFFFFF

    ret = round(-0.2 + f(0) * 0.6, 6)            # [-0.20, 0.40]
    vol = round(0.05 + f(1) * 0.35, 6)           # [0.05, 0.40]
    sharpe = round((ret / vol) if vol > _EPS else 0.0, 6)
    mdd = round(-(0.02 + f(2) * 0.48), 6)        # [-0.50, -0.02]
    turnover = round(f(3) * 3.0, 6)              # [0, 3]
    stability = round(f(4), 6)                   # [0, 1]
    confidence = round(f(5), 6)                  # [0, 1]
    return {"return": ret, "volatility": vol, "sharpe": sharpe, "max_drawdown": mdd,
            "turnover": turnover, "stability_score": stability, "confidence": confidence}


def compare_symbol(delta: float) -> str:
    """두 값의 차이를 서술 기호로(> / < / ≈). 자동 추천 아님 — 사람 검토용 요약."""
    if delta > 0.05:
        return ">"
    if delta < -0.05:
        return "<"
    return "≈"


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
class ScenarioEvent:
    """시나리오 등록·상태 전이 이벤트(이벤트 소싱). 정체성 불변."""
    event_id: str
    scenario_id: str
    name: str
    scenario_type: str
    description: str
    metadata_hash: str
    from_state: str
    to_state: str
    status: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SimulationRunEvent:
    event_id: str
    run_id: str
    candidate_reference: str        # 외부 연구 후보/전략 참조(문자열만 — READ ONLY)
    scenario_reference: str
    parameter_set: dict
    dataset_reference: str
    seed: str
    run_hash: str
    from_state: str
    to_state: str
    status: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ParameterScenario:
    parameter_id: str
    name: str
    category: str                   # LOOKBACK | COST_SHOCK | RISK_SHOCK | DATASET_SHIFT | GENERIC
    parameters: dict
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MarketRegimeScenario:
    regime_id: str
    name: str
    regime: str                     # bull | bear | sideways | high_volatility
    parameters: dict
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SimulationResult:
    result_id: str
    run_id: str
    metrics: dict                   # return/volatility/sharpe/max_drawdown/turnover/stability/confidence
    deterministic_input: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SimulationComparison:
    comparison_id: str
    run_a: str
    run_b: str
    dimensions: dict                # {performance/stability/risk/sensitivity: {a,b,delta,symbol}}
    note: str                       # 자동 추천 없음 — 서술적 비교만
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SimulationArtifact:
    artifact_id: str
    artifact_type: str
    ref_id: str
    parent_artifact: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SimulationEnvironmentReport:
    timestamp: str
    scenario_count: int
    scenario_state_distribution: dict
    scenario_type_distribution: dict
    run_count: int
    run_state_distribution: dict
    result_count: int
    regime_count: int
    parameter_count: int
    comparison_count: int

    def to_dict(self) -> dict:
        return asdict(self)
