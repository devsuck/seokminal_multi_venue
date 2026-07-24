"""Research Optimization Engine 자료형 (P12.6) — 연구 생태계 최적화 기회 분석. **분석·제안 전용.**

전체 연구 생태계를 분석해 최적화 기회를 식별한다(병목 탐지·워크플로 최적화 분석·자원 효율 분석·연구 처리량
분석). **자동으로 최적화하지 않는다.** ANALYZE ≠ OPTIMIZE · PROPOSAL ≠ MODIFICATION · IDENTIFIED ≠ EXECUTION.
최적화 제안은 코드·설정·권한·전략을 변경할 수 없다. 불변·append-only·이벤트 소싱·SHA256 해시체인·결정적.
물리 원장은 roe_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 최적화 연구 생애주기(6) ──
O_OBSERVED = "OBSERVED"
O_ANALYZED = "ANALYZED"
O_IDENTIFIED = "IDENTIFIED"
O_PROPOSED = "PROPOSED"
O_REVIEWED = "REVIEWED"
O_ARCHIVED = "ARCHIVED"
STUDY_STATES = (O_OBSERVED, O_ANALYZED, O_IDENTIFIED, O_PROPOSED, O_REVIEWED, O_ARCHIVED)

ALLOWED_TRANSITIONS = {
    O_OBSERVED: {O_ANALYZED},
    O_ANALYZED: {O_IDENTIFIED},
    O_IDENTIFIED: {O_IDENTIFIED, O_PROPOSED},
    O_PROPOSED: {O_REVIEWED},
    O_REVIEWED: {O_ARCHIVED, O_ANALYZED},
    O_ARCHIVED: set(),
}

# ── 병목 심각도 ──
SEV_LOW = "LOW"
SEV_MEDIUM = "MEDIUM"
SEV_HIGH = "HIGH"
SEV_CRITICAL = "CRITICAL"
SEVERITIES = (SEV_LOW, SEV_MEDIUM, SEV_HIGH, SEV_CRITICAL)

# ── 효율 비교 방향 ──
DIR_IMPROVED = "IMPROVED"
DIR_REGRESSED = "REGRESSED"
DIR_UNCHANGED = "UNCHANGED"

# ── 금지(자동 최적화·수정·배포·실행) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "AUTO_OPTIMIZE", "AUTO_MODIFY", "AUTO_DEPLOY", "AUTO_EXECUTE", "CHANGE_CODE", "CHANGE_CONFIG",
    "CHANGE_PERMISSION", "CHANGE_STRATEGY", "DEPLOY", "EXECUTE", "MODIFY_SYSTEM", "OPTIMIZE",
})


class ImmutableStudyError(Exception):
    """불변 최적화 연구(중복) 위반."""


class ImmutableBottleneckError(Exception):
    """불변 병목 리포트 위반."""


class ImmutableEfficiencyError(Exception):
    """불변 효율 분석 위반."""


class ImmutableProposalError(Exception):
    """불변 최적화 제안 위반."""


class ImmutableComparisonError(Exception):
    """불변 역사 비교 위반."""


class IllegalStudyTransition(Exception):
    """유효하지 않은 최적화 연구 상태 전이 — 거부."""


class InvalidSeverity(Exception):
    """미등록 병목 심각도."""


class IncompleteProposalError(Exception):
    """제안 필수 필드(problem/evidence/impact/risk/reviewer) 누락 — 거부."""


class ForbiddenOptimizationError(Exception):
    """코드/설정/권한/전략 변경 또는 자동 최적화 시도 — 거부."""


class UnknownStudyError(Exception):
    """미등록 최적화 연구 참조."""


# ── 해시(SHA256) ──
def _digest(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def input_digest(*parts) -> str:
    return _digest(list(parts))


def content_hash(record: dict) -> str:
    core = {k: v for k, v in record.items()
            if k not in ("previous_hash", "record_hash", "report_hash")}
    return _digest(core)


# ── 결정적 ID (OP* 스킴) ──
def study_id(name: str) -> str:
    return "OPS:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def study_event_id(study: str, to_state: str, seq: int) -> str:
    return "OPV:" + hashlib.sha1(input_digest(study, to_state, seq).encode()).hexdigest()[:12]


def bottleneck_id(study: str, target: str) -> str:
    return "OPB:" + hashlib.sha1(input_digest(study, target).encode()).hexdigest()[:12]


def efficiency_id(study: str, subject: str, metric: str) -> str:
    return "OPE:" + hashlib.sha1(input_digest(study, subject, metric).encode()).hexdigest()[:12]


def proposal_id(study: str, title: str) -> str:
    return "OPP:" + hashlib.sha1(input_digest(study, title).encode()).hexdigest()[:12]


def comparison_id(study: str, subject_a: str, subject_b: str, metric: str) -> str:
    return "OPC:" + hashlib.sha1(
        input_digest(study, subject_a, subject_b, metric).encode()).hexdigest()[:12]


def report_id(study: str, scope: str, generated_at: str) -> str:
    return "OPO:" + hashlib.sha1(
        input_digest(study, scope, generated_at).encode()).hexdigest()[:12]


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word: str) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, set())


def compare_direction(value_a: float, value_b: float, higher_is_better: bool = True) -> tuple:
    """효율 비교 방향·델타(결정적). 반환 (direction, delta)."""
    delta = round(float(value_b) - float(value_a), 8)
    if delta == 0:
        return DIR_UNCHANGED, 0.0
    improved = (delta > 0) if higher_is_better else (delta < 0)
    return (DIR_IMPROVED if improved else DIR_REGRESSED), delta


def rank_bottlenecks(items: list) -> list:
    """병목 심각도·부하 기준 결정적 정렬. items: [(target, severity_rank, load)]."""
    return sorted(items, key=lambda x: (-x[1], -x[2], x[0]))


def severity_rank(severity: str) -> int:
    return {SEV_LOW: 1, SEV_MEDIUM: 2, SEV_HIGH: 3, SEV_CRITICAL: 4}.get(severity, 0)


def detect_cycle(edges: list) -> list:
    """방향 그래프 순환 탐지(DFS, 결정적). 첫 순환 경로 또는 []."""
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
class StudyEventRecord:
    study_event_id: str
    study_id: str
    name: str
    scope: str
    from_state: str
    to_state: str
    note: str
    occurred_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class BottleneckRecord:
    bottleneck_id: str
    study_id: str
    target: str
    severity: str
    load: float
    description: str
    evidence_ref: str
    detected_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EfficiencyRecord:
    efficiency_id: str
    study_id: str
    subject: str
    metric_name: str
    value: float
    throughput: float
    note: str
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ProposalRecord:
    proposal_id: str
    study_id: str
    title: str
    problem: str
    evidence: str
    expected_impact: str
    risk: str
    reviewer: str
    proposed_change: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ComparisonRecord:
    comparison_id: str
    study_id: str
    subject_a: str
    subject_b: str
    metric_name: str
    value_a: float
    value_b: float
    delta: float
    direction: str
    compared_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class OptimizationReportRecord:
    report_id: str
    study_id: str
    scope: str
    bottleneck_count: int
    efficiency_count: int
    proposal_count: int
    comparison_count: int
    severity_distribution: dict
    is_binding: bool
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class OptimizationSummary:
    timestamp: str
    study_event_count: int
    bottleneck_count: int
    efficiency_count: int
    proposal_count: int
    comparison_count: int
    report_count: int

    def to_dict(self) -> dict:
        return asdict(self)
