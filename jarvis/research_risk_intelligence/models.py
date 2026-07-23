"""Research Risk Intelligence 자료형 (P10.25) — 연구 과정 자체의 리스크 분석 전용. **투자 실행 리스크 아님.**

P10.2 Strategy Governance·P10.3 Alpha Intelligence·P10.4 Portfolio Research·P10.7 Decision Intelligence·
P10.8 Simulation 을 **READ ONLY** 로 참조(파일 기반, import 없음)해 과적합·데이터 누수·거짓 발견·복잡도·검증
취약·재현성 리스크를 분석한다. 리스크 레지스트리·리스크 평가·리스크 요인·리스크 리포트·리스크 계보를 제공한다.
**리스크 한도 변경·자본 결정·전략 거부·배포 결정 없음.** RISK ANALYSIS ≠ RISK LIMIT CHANGE · ASSESSMENT ≠
CAPITAL DECISION · FINDING ≠ STRATEGY REJECTION · SCORE ≠ DEPLOYMENT DECISION. 불변·append-only·결정적. 원장 rr_.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"
_EPS = 1e-9

# ── 리스크 생명주기 ──
UNKNOWN = "UNKNOWN"
ANALYZING = "ANALYZING"
ASSESSED = "ASSESSED"
REVIEWED = "REVIEWED"
RISK_STATES = (UNKNOWN, ANALYZING, ASSESSED, REVIEWED)
RISK_TRANSITIONS = {
    "": {UNKNOWN},
    UNKNOWN: {ANALYZING},
    ANALYZING: {ASSESSED},
    ASSESSED: {REVIEWED},
    REVIEWED: set(),
}

# ── 리스크 결과 라벨 ──
PASS = "PASS"
WARNING = "WARNING"
CRITICAL = "CRITICAL"
RESULTS = (PASS, WARNING, CRITICAL)

# ── 연구 리스크 범주(6대) ──
R_OVERFITTING = "overfitting_risk"
R_DATA_LEAKAGE = "data_leakage_risk"
R_FALSE_DISCOVERY = "false_discovery_risk"
R_COMPLEXITY = "complexity_risk"
R_VALIDATION_WEAKNESS = "validation_weakness"
R_REPRODUCIBILITY = "reproducibility_risk"
RISK_CATEGORIES = (R_OVERFITTING, R_DATA_LEAKAGE, R_FALSE_DISCOVERY, R_COMPLEXITY,
                   R_VALIDATION_WEAKNESS, R_REPRODUCIBILITY)

SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")

# ── 리스크 점수 가중치(합=1.0) — 높을수록 리스크 큼. 정보용, 결정/집행 아님 ──
RISK_WEIGHTS = {
    R_OVERFITTING: 0.25,
    R_DATA_LEAKAGE: 0.20,
    R_FALSE_DISCOVERY: 0.20,
    R_COMPLEXITY: 0.10,
    R_VALIDATION_WEAKNESS: 0.15,
    R_REPRODUCIBILITY: 0.10,
}

# ── 계보 노드 유형 ──
NODE_LAYER = "LAYER"
NODE_RISK = "RISK"
NODE_FACTOR = "FACTOR"
NODE_ASSESSMENT = "ASSESSMENT"
NODE_REPORT = "REPORT"
NODE_TYPES = (NODE_LAYER, NODE_RISK, NODE_FACTOR, NODE_ASSESSMENT, NODE_REPORT)

# ── Artifact 유형(계보) ──
ART_LAYER = "LAYER"
ART_RISK = "RISK"
ART_FACTOR = "FACTOR"
ART_ASSESSMENT = "ASSESSMENT"
ART_REPORT = "REPORT"


class IllegalTransition(Exception):
    """차단된 리스크 생명주기 전이."""


class ImmutableFactorError(Exception):
    """불변 리스크 요인 위반."""


class ImmutableAssessmentError(Exception):
    """불변 리스크 평가 위반."""


class UnknownRisk(Exception):
    """미등록 리스크 참조."""


class InvalidRiskCategory(Exception):
    """미등록 리스크 범주."""


def can_transition_risk(frm: str, to: str) -> bool:
    return to in RISK_TRANSITIONS.get(frm, set())


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


# ── 결정적 ID ──
def risk_id(source_reference: str, risk_category: str) -> str:
    return "RRK:" + hashlib.sha1(
        input_digest(source_reference, risk_category).encode()).hexdigest()[:12]


def risk_event_id(rid: str, frm: str, to: str) -> str:
    return "RRE:" + hashlib.sha1(input_digest(rid, frm, to).encode()).hexdigest()[:12]


def factor_id(risk_ref: str, name: str) -> str:
    return "RRF:" + hashlib.sha1(input_digest(risk_ref, name).encode()).hexdigest()[:12]


def assessment_id(risk_ref: str, epoch: str) -> str:
    return "RRA:" + hashlib.sha1(input_digest(risk_ref, epoch).encode()).hexdigest()[:12]


def report_id(scope: str) -> str:
    return "RRP:" + hashlib.sha1(input_digest(scope).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "RRX:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── 점수/평가(결정적, 정보용) ──
def risk_score(dimension_scores: dict) -> float:
    """가중 리스크 점수(0~1, 높을수록 리스크 큼). **SCORE ≠ DEPLOYMENT DECISION — 결정 신호 아님.**"""
    total = 0.0
    for dim, wt in RISK_WEIGHTS.items():
        total += float((dimension_scores or {}).get(dim, 0.0)) * float(wt)
    return round(total, 8)


def risk_label(dimension_scores: dict) -> str:
    """리스크 점수 → PASS/WARNING/CRITICAL(리스크 수준). **정보용 — 자동 거부/한도변경 없음.**

    점수가 낮으면 리스크 낮음(PASS), 높으면 리스크 큼(CRITICAL)."""
    s = risk_score(dimension_scores)
    if s >= 0.7:
        return CRITICAL
    if s >= 0.4:
        return WARNING
    return PASS


def label_from_score(score: float) -> str:
    if score >= 0.7:
        return CRITICAL
    if score >= 0.4:
        return WARNING
    return PASS


def worst_label(labels: list) -> str:
    rank = {PASS: 0, WARNING: 1, CRITICAL: 2}
    worst = PASS
    for l in labels or []:
        if rank.get(l, 0) > rank.get(worst, 0):
            worst = l
    return worst


def aggregate_factors(factors: list) -> dict:
    """리스크 요인 목록 → 범주별 가중 평균 dimension_scores. **집계만 — 결정 아님.**"""
    acc: dict = {}
    wsum: dict = {}
    for f in factors or []:
        cat = f.get("category")
        if cat not in RISK_CATEGORIES:
            continue
        w = float(f.get("weight", 1.0))
        acc[cat] = acc.get(cat, 0.0) + float(f.get("value", 0.0)) * w
        wsum[cat] = wsum.get(cat, 0.0) + w
    return {cat: round(acc[cat] / wsum[cat], 8) for cat in acc if wsum.get(cat, 0.0) > _EPS}


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
class RiskEvent:
    event_id: str
    risk_id: str
    source_layer: str
    source_reference: str
    risk_category: str
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
class RiskFactor:
    factor_id: str
    risk_ref: str
    name: str
    category: str
    value: float
    weight: float
    interpretation: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RiskAssessment:
    assessment_id: str
    risk_ref: str
    source_reference: str
    dimension_scores: dict
    risk_score: float
    risk_label: str
    evidence_reference: str
    epoch: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RiskReport:
    report_id: str
    scope: str
    risk_count: int
    risk_state_distribution: dict
    risk_category_distribution: dict
    assessment_count: int
    assessment_label_distribution: dict
    factor_count: int
    average_risk_score: float
    overall_label: str
    high_risk_items: list
    metrics: dict
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RiskArtifact:
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
class RiskSummary:
    timestamp: str
    risk_count: int
    risk_state_distribution: dict
    risk_category_distribution: dict
    factor_count: int
    assessment_count: int
    assessment_label_distribution: dict
    report_count: int

    def to_dict(self) -> dict:
        return asdict(self)
