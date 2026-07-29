"""Autonomous Research OS 자료형 (P13) — 최상위 연구 통합. **관찰·분석·기록 전용.**

모든 하위 연구 계층(P10.x/P12.x)을 **READ ONLY** 로 연결·관찰·집계한다. **거래·주문·자본 배분·전략 배포·모델 승격·
권한 변경을 절대 하지 않는다.** Research OS = OBSERVATION + ANALYSIS + RECORDING ONLY. OS ≠ EXECUTION ·
CONNECT ≠ CONTROL · SNAPSHOT ≠ DEPLOYMENT. 불변·append-only·SHA256 해시체인·이벤트 소싱·결정적. 물리 원장 aros_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── OS 생애주기(6) ──
OS_INITIALIZED = "INITIALIZED"
OS_CONNECTED = "CONNECTED"
OS_OBSERVING = "OBSERVING"
OS_ANALYZING = "ANALYZING"
OS_REPORTING = "REPORTING"
OS_ARCHIVED = "ARCHIVED"
OS_STATES = (OS_INITIALIZED, OS_CONNECTED, OS_OBSERVING, OS_ANALYZING, OS_REPORTING, OS_ARCHIVED)

ALLOWED_TRANSITIONS = {
    OS_INITIALIZED: {OS_CONNECTED},
    OS_CONNECTED: {OS_OBSERVING},
    OS_OBSERVING: {OS_OBSERVING, OS_ANALYZING},
    OS_ANALYZING: {OS_ANALYZING, OS_REPORTING, OS_OBSERVING},
    OS_REPORTING: {OS_ARCHIVED, OS_OBSERVING},
    OS_ARCHIVED: set(),
}

# ── 아티팩트(계보) 유형 ──
ART_OS = "OS"
ART_EPISODE = "EPISODE"
ART_SNAPSHOT = "SNAPSHOT"
ART_VIEW = "VIEW"

# ── 절대 금지(실행·거래·배포·승격·권한) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "RUN_ORDER", "START_TRADING", "ALLOCATE_CAPITAL",
    "DEPLOY_STRATEGY", "DEPLOY_MODEL", "DEPLOY", "PROMOTE_MODEL", "CHANGE_PERMISSION",
    "GRANT_PERMISSION", "TRADE", "LIQUIDATE", "REBALANCE", "AUTO_RECOVER", "AUTO_DEPLOY",
})


class ImmutableOSError(Exception):
    """불변 OS 레지스트리(중복) 위반."""


class IllegalOSTransition(Exception):
    """유효하지 않은 OS 상태 전이 — 거부."""


class UnknownOSError(Exception):
    """미등록 OS 인스턴스 참조."""


class ForbiddenOSActionError(Exception):
    """금지된 실행/거래/배포/승격/권한 동작 시도 — 차단."""


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


# ── 결정적 ID (AO* 스킴) ──
def os_id(name: str) -> str:
    return "AOG:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def os_event_id(os: str, to_state: str, seq: int) -> str:
    return "AOR:" + hashlib.sha1(input_digest(os, to_state, seq).encode()).hexdigest()[:12]


def episode_id(os: str, layer: str, seq: int) -> str:
    return "AOE:" + hashlib.sha1(input_digest(os, layer, seq).encode()).hexdigest()[:12]


def snapshot_id(os: str, generated_at: str) -> str:
    return "AOS:" + hashlib.sha1(input_digest(os, generated_at).encode()).hexdigest()[:12]


def view_id(os: str, kind: str, generated_at: str) -> str:
    return "AOV:" + hashlib.sha1(input_digest(os, kind, generated_at).encode()).hexdigest()[:12]


def report_id(os: str, scope: str, generated_at: str) -> str:
    return "AON:" + hashlib.sha1(input_digest(os, scope, generated_at).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "AOF:" + hashlib.sha1(input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word: str) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, set())


def detect_cycle_check(edges: list) -> bool:
    """방향 그래프 순환 존재 여부(DFS, 결정적). 계보 검증용."""
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
class OSEventRecord:
    os_event_id: str
    os_id: str
    name: str
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
class EpisodeRecord:
    episode_id: str
    os_id: str
    layer: str
    source_file: str
    observed_count: int
    note: str
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ViewRecord:
    view_id: str
    os_id: str
    kind: str
    layer_counts: dict
    total_records: int
    is_binding: bool
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SnapshotRecord:
    snapshot_id: str
    os_id: str
    timestamp: str
    os_state: str
    episode_count: int
    layer_counts: dict
    total_records: int
    is_binding: bool
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class OSReportRecord:
    report_id: str
    os_id: str
    scope: str
    os_state: str
    episode_count: int
    view_count: int
    snapshot_count: int
    connected_layers: int
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
class OSSummary:
    timestamp: str
    os_event_count: int
    episode_count: int
    view_count: int
    snapshot_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
