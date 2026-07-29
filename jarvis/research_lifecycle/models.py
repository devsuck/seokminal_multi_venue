"""Research Lifecycle Intelligence 자료형 (P10.26) — 전 모듈 연구 생명주기 추적 전용. 관찰·기록만.

P10.2~P10.25 를 **READ ONLY** 로 참조(파일 기반, import 없음)해 연구 프로젝트·생명주기 이벤트·스테이지 전이·
병목 기록·생명주기 리포트를 제공한다. 생명주기: IDEA→HYPOTHESIS→EXPERIMENT→BACKTEST→VALIDATION→DECISION→
ARCHIVE. 이벤트 소싱·불변 생명주기 이력·전이 검증·누락 스테이지 탐지. **실행·배포·승인·거래 없음.** LIFECYCLE
TRACKING ≠ EXECUTION · TRANSITION ≠ APPROVAL · STAGE ≠ DEPLOYMENT · RECORD ≠ DECISION. 불변·append-only·결정적.
물리 원장은 rl_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"
_EPS = 1e-9

# ── 연구 생명주기 스테이지 ──
IDEA = "IDEA"
HYPOTHESIS = "HYPOTHESIS"
EXPERIMENT = "EXPERIMENT"
BACKTEST = "BACKTEST"
VALIDATION = "VALIDATION"
DECISION = "DECISION"
ARCHIVE = "ARCHIVE"
STAGES = (IDEA, HYPOTHESIS, EXPERIMENT, BACKTEST, VALIDATION, DECISION, ARCHIVE)
_STAGE_INDEX = {s: i for i, s in enumerate(STAGES)}

# 선형 진행 + 임의 스테이지에서 조기 ARCHIVE 허용. 스테이지 건너뛰기(2단계 이상)는 무효.
STAGE_TRANSITIONS = {
    "": {IDEA},
    IDEA: {HYPOTHESIS, ARCHIVE},
    HYPOTHESIS: {EXPERIMENT, ARCHIVE},
    EXPERIMENT: {BACKTEST, ARCHIVE},
    BACKTEST: {VALIDATION, ARCHIVE},
    VALIDATION: {DECISION, ARCHIVE},
    DECISION: {ARCHIVE},
    ARCHIVE: set(),
}

# ── 생명주기 이벤트 유형(예시) ──
EV_NOTE = "NOTE"
EV_ARTIFACT_LINKED = "ARTIFACT_LINKED"
EV_STAGE_ENTERED = "STAGE_ENTERED"
EV_REWORK = "REWORK"
EV_BLOCKED = "BLOCKED"
EVENT_TYPES = (EV_NOTE, EV_ARTIFACT_LINKED, EV_STAGE_ENTERED, EV_REWORK, EV_BLOCKED)

# ── 병목 범주 ──
B_STALLED_STAGE = "stalled_stage"
B_REPEATED_REWORK = "repeated_rework"
B_MISSING_VALIDATION = "missing_validation"
B_SLOW_TRANSITION = "slow_transition"
B_RESOURCE_WAIT = "resource_wait"
BOTTLENECK_CATEGORIES = (B_STALLED_STAGE, B_REPEATED_REWORK, B_MISSING_VALIDATION,
                         B_SLOW_TRANSITION, B_RESOURCE_WAIT)

SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")

# ── 계보 노드 유형 ──
NODE_LAYER = "LAYER"
NODE_PROJECT = "PROJECT"
NODE_TRANSITION = "TRANSITION"
NODE_EVENT = "EVENT"
NODE_BOTTLENECK = "BOTTLENECK"
NODE_REPORT = "REPORT"
NODE_TYPES = (NODE_LAYER, NODE_PROJECT, NODE_TRANSITION, NODE_EVENT, NODE_BOTTLENECK, NODE_REPORT)

# ── Artifact 유형(계보) ──
ART_LAYER = "LAYER"
ART_PROJECT = "PROJECT"
ART_TRANSITION = "TRANSITION"
ART_EVENT = "EVENT"
ART_BOTTLENECK = "BOTTLENECK"
ART_REPORT = "REPORT"


class IllegalTransition(Exception):
    """차단된 생명주기 스테이지 전이."""


class ImmutableEventError(Exception):
    """불변 생명주기 이벤트 위반."""


class ImmutableBottleneckError(Exception):
    """불변 병목 기록 위반."""


class UnknownProject(Exception):
    """미등록 연구 프로젝트 참조."""


class InvalidStage(Exception):
    """미등록 생명주기 스테이지."""


class InvalidEventType(Exception):
    """미등록 생명주기 이벤트 유형."""


class InvalidBottleneckCategory(Exception):
    """미등록 병목 범주."""


def can_transition_stage(frm: str, to: str) -> bool:
    return to in STAGE_TRANSITIONS.get(frm, set())


def stage_index(stage: str) -> int:
    return _STAGE_INDEX.get(stage, -1)


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
def project_id(name: str) -> str:
    return "RLP:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def project_event_id(pid: str, frm: str, to: str) -> str:
    return "RLE:" + hashlib.sha1(input_digest(pid, frm, to).encode()).hexdigest()[:12]


def transition_id(pid: str, frm: str, to: str) -> str:
    return "RLT:" + hashlib.sha1(input_digest(pid, frm, to).encode()).hexdigest()[:12]


def event_id(pid: str, event_type: str, reference: str) -> str:
    return "RLV:" + hashlib.sha1(
        input_digest(pid, event_type, reference).encode()).hexdigest()[:12]


def bottleneck_id(pid: str, stage: str, category: str) -> str:
    return "RLB:" + hashlib.sha1(input_digest(pid, stage, category).encode()).hexdigest()[:12]


def report_id(scope: str) -> str:
    return "RLR:" + hashlib.sha1(input_digest(scope).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "RLX:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── 누락 스테이지 탐지(결정적) ──
def missing_stages(entered_stages: list) -> list:
    """진입한 스테이지 목록 대비 정규 스테이지 중 누락된 것(ARCHIVE 제외). **정보용 — 조치 아님.**"""
    entered = set(entered_stages or [])
    return [s for s in STAGES if s != ARCHIVE and s not in entered]


def completion_ratio(entered_stages: list) -> float:
    """진행률: 진입한 정규 스테이지 수 / 전체(ARCHIVE 제외). 0~1."""
    core = [s for s in STAGES if s != ARCHIVE]
    entered = {s for s in (entered_stages or []) if s in core}
    return round(len(entered) / len(core), 8) if core else 0.0


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
class ProjectEvent:
    event_id: str
    project_id: str
    name: str
    source_layer: str
    source_reference: str
    from_stage: str
    to_stage: str
    stage: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class StageTransition:
    transition_id: str
    project_id: str
    from_stage: str
    to_stage: str
    note: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LifecycleEvent:
    event_id: str
    project_id: str
    event_type: str
    reference: str
    detail: str
    stage: str
    timestamp: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class BottleneckRecord:
    bottleneck_id: str
    project_id: str
    stage: str
    category: str
    severity: str
    detail: str
    evidence: list
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LifecycleReport:
    report_id: str
    scope: str
    project_count: int
    stage_distribution: dict
    transition_count: int
    event_count: int
    event_type_distribution: dict
    bottleneck_count: int
    bottleneck_category_distribution: dict
    archived_count: int
    completed_decision_count: int
    average_completion: float
    missing_stage_summary: dict
    metrics: dict
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LifecycleArtifact:
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
class LifecycleSummary:
    timestamp: str
    project_count: int
    stage_distribution: dict
    transition_count: int
    event_count: int
    bottleneck_count: int
    report_count: int

    def to_dict(self) -> dict:
        return asdict(self)
