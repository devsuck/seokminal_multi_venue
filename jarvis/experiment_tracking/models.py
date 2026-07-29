"""Experiment Tracking Platform 자료형 (P42) — 모든 연구 실험 추적. **실행 없음.**

모든 연구 실험을 추적한다: 실험 레지스트리·실행(run)·파라미터·아티팩트·결과·비교. 데이터셋 버전·코드 버전·파라미터·
지표·결과를 추적한다. **실행 없음 — 외부에서 사람이 수행한 실험의 기록만.** TRACK ≠ EXECUTE · RECORD ≠ RUN.
불변·append-only·SHA256 해시체인·결정적. 물리 원장 expt_ 접두사. 상위 계층은 READ ONLY.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 실행 상태(기록만, 불변) ──
RUN_STATUSES = ("RECORDED", "ANALYZED", "ARCHIVED")

# ── 아티팩트 유형 ──
ARTIFACT_TYPES = ("MODEL", "PLOT", "REPORT", "DATASET_REF", "LOG", "METRIC_FILE")

# ── 아티팩트 유형(계보) ──
ART_EXPERIMENT = "EXPERIMENT"
ART_RUN = "RUN"
ART_ATTACHED = "ATTACHED"
ART_REPORT = "REPORT"

# ── 절대 금지(거래·실행·배포·배분) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "ACTIVATE_LIVE",
    "BROKER_EXECUTION", "EXECUTE", "DEPLOY", "TRADE", "ALLOCATE", "APPROVE", "RUN_EXPERIMENT",
    "PROMOTE",
})


class UnknownEntityError(Exception):
    """미등록 엔티티 참조."""


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


def value_hash(*parts) -> str:
    return _digest(list(parts))


def _id(tag, *parts) -> str:
    return f"{tag}:" + hashlib.sha1(input_digest(*parts).encode()).hexdigest()[:12]


# ── 결정적 ID (XT* 스킴) ──
def experiment_id(name) -> str:
    return _id("XTE", name)


def run_id(experiment, seq) -> str:
    return _id("XTR", experiment, seq)


def parameter_id(run, key) -> str:
    return _id("XTP", run, key)


def result_id(run, metric) -> str:
    return _id("XTM", run, metric)


def comparison_id(run_a, run_b) -> str:
    return _id("XTC", *sorted([run_a, run_b]))


def report_id(scope, created_at) -> str:
    return _id("XTO", scope, created_at)


def artifact_id(atype, ref) -> str:
    return _id("XTA", atype, ref)


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def metric_delta(a, b) -> float:
    """지표 차이(b - a, 결정적). 비수치는 0."""
    try:
        return round(float(b) - float(a), 6)
    except (TypeError, ValueError):
        return 0.0


def detect_cycle_check(edges) -> bool:
    graph: dict = {}
    for a, b in edges:
        graph.setdefault(a, set()).add(b)
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict = {}

    def dfs(node) -> bool:
        color[node] = GRAY
        for nxt in sorted(graph.get(node, ())):
            c = color.get(nxt, WHITE)
            if c == GRAY:
                return True
            if c == WHITE and dfs(nxt):
                return True
        color[node] = BLACK
        return False

    for node in sorted(graph):
        if color.get(node, WHITE) == WHITE and dfs(node):
            return True
    return False


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class ExperimentRecord:
    experiment_id: str
    name: str
    objective: str
    tags: list
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    experiment_id: str
    dataset_version: str
    code_version: str
    status: str
    note: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ParameterRecord:
    parameter_id: str
    run_id: str
    key: str
    value: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ResultRecord:
    result_id: str
    run_id: str
    metric: str
    value: float
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ComparisonRecord:
    comparison_id: str
    experiment_id: str
    run_a: str
    run_b: str
    metric_deltas: dict
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExperimentReportRecord:
    report_id: str
    scope: str
    experiment_count: int
    run_count: int
    parameter_count: int
    result_count: int
    comparison_count: int
    attached_artifact_count: int
    status_distribution: dict
    is_binding: bool
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ArtifactRecord:
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
class TrackingSummary:
    timestamp: str
    experiment_count: int
    run_count: int
    parameter_count: int
    result_count: int
    comparison_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
