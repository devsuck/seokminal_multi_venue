"""Research Governance Evolution Intelligence 자료형 (P10.22) — 거버넌스 생태계 시간적 변화 분석 전용.

P9.8~P10.21 전 계층을 **READ ONLY** 로 참조(파일 기반, import 없음)해 진화 이벤트 레지스트리·거버넌스 상태
타임라인·성숙도 평가·변화 패턴 분석·진화 스냅샷·역사적 비교·진화 리포트·진화 계보를 제공한다. 거버넌스
성숙도 성장·반복 구조 변화·역량 진화·역사적 전이·장기 추세를 추적한다. **거버넌스 규칙 수정·변경 적용·업그
레이드 승인·config 변경·시스템 배포 없음.** EVOLUTION ANALYSIS ≠ EVOLUTION ACTION · MATURITY SCORE ≠
PERMISSION · TREND DETECTION ≠ CHANGE EXECUTION · RECOMMENDATION ≠ IMPLEMENTATION. 불변·append-only
해시체인·결정적. 물리 원장은 ge_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"
_EPS = 1e-9

# ── 진화 이벤트 유형 ──
E_CAPABILITY_ADDED = "capability_added"
E_GOVERNANCE_CHANGE = "governance_change"
E_VALIDATION_IMPROVEMENT = "validation_improvement"
E_MATURITY_SHIFT = "maturity_shift"
E_PROCESS_TRANSITION = "process_transition"
E_STRUCTURAL_CHANGE = "structural_change"
EVENT_TYPES = (E_CAPABILITY_ADDED, E_GOVERNANCE_CHANGE, E_VALIDATION_IMPROVEMENT, E_MATURITY_SHIFT,
               E_PROCESS_TRANSITION, E_STRUCTURAL_CHANGE)

# ── 성숙도 사다리(순서 있음) ──
INITIAL = "INITIAL"
DEVELOPING = "DEVELOPING"
DEFINED = "DEFINED"
MANAGED = "MANAGED"
OPTIMIZING = "OPTIMIZING"
MATURITY_LEVELS = (INITIAL, DEVELOPING, DEFINED, MANAGED, OPTIMIZING)
_LEVEL_INDEX = {lv: i for i, lv in enumerate(MATURITY_LEVELS)}

# ── 성숙도 평가 차원 ──
D_DATA_QUALITY = "data_quality"
D_REPRODUCIBILITY = "reproducibility"
D_TRANSPARENCY = "transparency"
D_VALIDATION_STRENGTH = "validation_strength"
D_GOVERNANCE_DEPTH = "governance_depth"
D_AUDITABILITY = "auditability"
MATURITY_DIMENSIONS = (D_DATA_QUALITY, D_REPRODUCIBILITY, D_TRANSPARENCY, D_VALIDATION_STRENGTH,
                       D_GOVERNANCE_DEPTH, D_AUDITABILITY)
# 각 차원 동일 가중(합=1.0)
_DIMENSION_WEIGHT = round(1.0 / len(MATURITY_DIMENSIONS), 12)

# ── 진화 건강 점수 가중치(합=1.0) — 정보용, 권한/집행 아님 ──
EVOLUTION_WEIGHTS = {
    "maturity_growth": 0.30,
    "capability_expansion": 0.20,
    "change_stability": 0.20,
    "regression_inverse": 0.20,
    "assessment_coverage": 0.10,
}

# ── 진화 건강 라벨 ──
HEALTHY = "HEALTHY"
WARNING = "WARNING"
DEGRADED = "DEGRADED"

# ── 추세 라벨(정보용) ──
GROWING = "GROWING"
STABLE = "STABLE"
REGRESSING = "REGRESSING"

# ── 패턴 신뢰도 파라미터 ──
_FREQ_SATURATION = 3.0
_SEQ_SATURATION = 3.0

# ── 계보 노드 유형 ──
NODE_LAYER = "LAYER"
NODE_EVENT = "EVENT"
NODE_STATE = "STATE"
NODE_MATURITY = "MATURITY"
NODE_COMPARISON = "COMPARISON"
NODE_REPORT = "REPORT"
NODE_TYPES = (NODE_LAYER, NODE_EVENT, NODE_STATE, NODE_MATURITY, NODE_COMPARISON, NODE_REPORT)

# ── Artifact 유형(계보) ──
ART_LAYER = "LAYER"
ART_EVENT = "EVENT"
ART_STATE = "STATE"
ART_MATURITY = "MATURITY"
ART_PATTERN = "PATTERN"
ART_COMPARISON = "COMPARISON"
ART_SNAPSHOT = "SNAPSHOT"
ART_REPORT = "REPORT"


class IllegalTransition(Exception):
    """차단된 성숙도 상태 전이(레벨 건너뛰기)."""


class ImmutableEventError(Exception):
    """불변 진화 이벤트 위반."""


class ImmutableMaturityError(Exception):
    """불변 성숙도 평가 위반."""


class ImmutablePatternError(Exception):
    """불변 진화 패턴 위반."""


class UnknownState(Exception):
    """미등록 상태 참조."""


class InvalidEventType(Exception):
    """미등록 이벤트 유형."""


class InvalidMaturityLevel(Exception):
    """미등록 성숙도 레벨."""


def can_transition_state(frm: str, to: str) -> bool:
    """성숙도 전이 유효성: 최초(GENESIS)는 임의 레벨 허용, 이후는 인접 레벨(±1)·동일만 허용.

    레벨 하락은 허용(회귀 지표로 추적)하되, 2단계 이상 건너뛰기는 무효."""
    if to not in _LEVEL_INDEX:
        return False
    if frm == "":
        return True
    if frm not in _LEVEL_INDEX:
        return False
    return abs(_LEVEL_INDEX[to] - _LEVEL_INDEX[frm]) <= 1


def level_index(level: str) -> int:
    return _LEVEL_INDEX.get(level, -1)


def is_regression(frm: str, to: str) -> bool:
    if frm not in _LEVEL_INDEX or to not in _LEVEL_INDEX:
        return False
    return _LEVEL_INDEX[to] < _LEVEL_INDEX[frm]


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


def metadata_hash(metadata: dict) -> str:
    return _digest(dict(metadata or {}))


def snapshot_hash(collected_states: list, summary: dict) -> str:
    return _digest({"states": sorted(collected_states or []), "summary": dict(summary or {})})


# ── 결정적 ID ──
def event_id(source_layer: str, event_type: str, description: str) -> str:
    return "GEE:" + hashlib.sha1(
        input_digest(source_layer, event_type, description).encode()).hexdigest()[:12]


def state_id(layer_reference: str) -> str:
    return "GSX:" + hashlib.sha1(input_digest(layer_reference).encode()).hexdigest()[:12]


def state_event_id(sid: str, sequence: int) -> str:
    return "GSE:" + hashlib.sha1(input_digest(sid, int(sequence)).encode()).hexdigest()[:12]


def maturity_id(layer_reference: str, epoch: str) -> str:
    return "GEM:" + hashlib.sha1(
        input_digest(layer_reference, epoch).encode()).hexdigest()[:12]


def pattern_id(detected_sequence: list) -> str:
    return "GEP:" + hashlib.sha1(
        input_digest(list(detected_sequence or [])).encode()).hexdigest()[:12]


def comparison_id(previous_state: str, current_state: str) -> str:
    return "GEC:" + hashlib.sha1(
        input_digest(previous_state, current_state).encode()).hexdigest()[:12]


def snapshot_id(name: str, epoch: str) -> str:
    return "GEN:" + hashlib.sha1(input_digest(name, epoch).encode()).hexdigest()[:12]


def report_id(scope: str) -> str:
    return "GER:" + hashlib.sha1(input_digest(scope).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "GEA:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── 점수/평가(결정적, 정보용) ──
def overall_maturity(dimension_scores: dict) -> float:
    """차원 점수 가중 평균(0~1). **MATURITY SCORE ≠ PERMISSION — 권한 신호 아님.**"""
    total = 0.0
    for dim in MATURITY_DIMENSIONS:
        total += float((dimension_scores or {}).get(dim, 0.0)) * _DIMENSION_WEIGHT
    return round(total, 8)


def pattern_confidence(frequency: int, sequence_length: int) -> float:
    """반복도·시퀀스 길이 → 패턴 신뢰도(0~1). **PATTERN ≠ ACTION — 분석 전용.**"""
    base = min(1.0, float(max(0, frequency)) / _FREQ_SATURATION)
    depth = min(1.0, float(max(0, sequence_length)) / _SEQ_SATURATION)
    return round(0.6 * base + 0.4 * depth, 8)


def evolution_score(metrics: dict) -> float:
    """가중 진화 건강 점수(0~1). **EVOLUTION ANALYSIS ≠ EVOLUTION ACTION — 집행 신호 아님.**"""
    m = dict(metrics or {})
    if "regression_inverse" not in m and "regression_rate" in m:
        m["regression_inverse"] = max(0.0, 1.0 - float(m.get("regression_rate", 0.0)))
    total = 0.0
    for key, wt in EVOLUTION_WEIGHTS.items():
        total += float(m.get(key, 0.0)) * float(wt)
    return round(total, 8)


def evolution_health(metrics: dict) -> str:
    """진화 지표 → HEALTHY/WARNING/DEGRADED. **정보용 — 자동 조치/업그레이드 없음.**"""
    s = evolution_score(metrics)
    if s >= 0.7:
        return HEALTHY
    if s >= 0.4:
        return WARNING
    return DEGRADED


def trend_label(delta: float) -> str:
    """추세 델타 → GROWING/STABLE/REGRESSING. **TREND ≠ CHANGE EXECUTION.**"""
    if delta > _EPS:
        return GROWING
    if delta < -_EPS:
        return REGRESSING
    return STABLE


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
class EvolutionEvent:
    event_id: str
    source_layer: str
    event_type: str
    description: str
    metadata_hash: str
    timestamp: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GovernanceStateEvent:
    event_id: str
    state_id: str
    layer_reference: str
    sequence: int
    from_maturity: str
    to_maturity: str
    maturity_level: str
    capabilities: list
    regression: bool
    timestamp: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MaturityAssessment:
    assessment_id: str
    layer_reference: str
    dimension_scores: dict
    overall_score: float
    evidence_reference: str
    epoch: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvolutionPattern:
    pattern_id: str
    detected_sequence: list
    frequency: int
    confidence: float
    metadata_hash: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class HistoricalComparison:
    comparison_id: str
    previous_state: str
    current_state: str
    differences: dict
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvolutionSnapshot:
    snapshot_id: str
    name: str
    epoch: str
    collected_states: list
    summary: dict
    state_count: int
    snapshot_hash: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvolutionReport:
    report_id: str
    scope: str
    event_count: int
    event_type_distribution: dict
    state_count: int
    layer_count: int
    maturity_level_distribution: dict
    assessment_count: int
    average_maturity: float
    pattern_count: int
    comparison_count: int
    snapshot_count: int
    regression_indicators: list
    capability_evolution_map: dict
    metrics: dict
    evolution_score: float
    evolution_health: str
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvolutionArtifact:
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
class EvolutionSummary:
    timestamp: str
    event_count: int
    event_type_distribution: dict
    state_count: int
    layer_count: int
    maturity_level_distribution: dict
    assessment_count: int
    pattern_count: int
    comparison_count: int
    snapshot_count: int
    report_count: int

    def to_dict(self) -> dict:
        return asdict(self)
