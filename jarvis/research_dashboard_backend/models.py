"""Research Dashboard Backend 자료형 (P34) — 백엔드 집계 계층. **UI 없음, 결정 권한 없음.**

백엔드 집계 계층: 통계·타임라인·헬스·지식 요약·연구 진행·모니터링을 제공한다. **UI 없음. 백엔드 전용. 결정 권한 없음.**
BACKEND ONLY · AGGREGATION ≠ DECISION · DASHBOARD ≠ AUTHORITY. 불변·append-only·SHA256 해시체인·결정적.
물리 원장 rdb_ 접두사. 상위 계층(P10~P33)은 READ ONLY.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 패널 유형 ──
PANEL_TYPES = ("STATISTICS", "TIMELINE", "HEALTH", "KNOWLEDGE_SUMMARY", "RESEARCH_PROGRESS",
               "MONITORING")

# ── 아티팩트 유형 ──
ART_PANEL = "PANEL"
ART_SNAPSHOT = "SNAPSHOT"
ART_REPORT = "REPORT"

# ── 절대 금지(실행·배포·거래·승인·결정) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "ACTIVATE_LIVE",
    "APPROVE_FOR_TRADING", "EXECUTE", "DEPLOY", "TRADE", "ALLOCATE", "APPROVE", "DECIDE",
    "SELECT_STRATEGY", "MAKE_DECISION", "PROMOTE",
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


# ── 결정적 ID (DB* 스킴) ──
def panel_id(panel_type, name) -> str:
    return _id("DBP", panel_type, name)


def snapshot_id(panel_type, created_at) -> str:
    return _id("DBS", panel_type, created_at)


def widget_id(panel_type, metric_name, seq) -> str:
    return _id("DBW", panel_type, metric_name, seq)


def report_id(scope, created_at) -> str:
    return _id("DBR", scope, created_at)


def artifact_id(atype, ref) -> str:
    return _id("DBA", atype, ref)


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def ratio(numerator, denominator) -> float:
    d = float(denominator)
    if d == 0.0:
        return 0.0
    return round(float(numerator) / d, 6)


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
class PanelRecord:
    panel_id: str
    panel_type: str
    name: str
    description: str
    is_readonly: bool  # 항상 True — 백엔드 집계 전용
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SnapshotRecord:
    snapshot_id: str
    panel_type: str
    data: dict
    data_hash: str
    is_decision: bool  # 항상 False — 집계만, 결정 권한 없음
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class WidgetRecord:
    widget_id: str
    panel_type: str
    metric_name: str
    value: float
    unit: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DashboardReportRecord:
    report_id: str
    scope: str
    panel_count: int
    snapshot_count: int
    widget_count: int
    panel_type_distribution: dict
    aggregate_statistics: dict
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
class DashboardSummary:
    timestamp: str
    panel_count: int
    snapshot_count: int
    widget_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
