"""Research Learning Loop 자료형 (P12.8) — 통제된 피드백 분석. **관찰·분석·기록 전용.**

"무엇이 통했는가 / 무엇이 실패했는가 / 무엇을 조사해야 하는가"를 분석한다. **자동 개선을 하지 않는다.** 개선
후보는 기록만 하며 절대 자동 적용하지 않는다. LEARNING ≠ MODIFICATION · LESSON ≠ APPLICATION · CANDIDATE ≠ EXECUTION.
불변·append-only·이벤트 소싱·SHA256 해시체인·결정적. 물리 원장은 rll_ 접두사(기존 rl_ 계층과 구별).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 학습 생애주기(5) ──
L_OBSERVED = "OBSERVED"
L_ANALYZED = "ANALYZED"
L_LESSON_CREATED = "LESSON_CREATED"
L_REVIEWED = "REVIEWED"
L_ARCHIVED = "ARCHIVED"
LEARNING_STATES = (L_OBSERVED, L_ANALYZED, L_LESSON_CREATED, L_REVIEWED, L_ARCHIVED)

ALLOWED_TRANSITIONS = {
    L_OBSERVED: {L_ANALYZED},
    L_ANALYZED: {L_LESSON_CREATED},
    L_LESSON_CREATED: {L_REVIEWED},
    L_REVIEWED: {L_ARCHIVED, L_ANALYZED},
    L_ARCHIVED: set(),
}

# ── 관찰 판정(무엇이 통했나/실패했나/조사할까) ──
OBS_WORKED = "WORKED"
OBS_FAILED = "FAILED"
OBS_INVESTIGATE = "INVESTIGATE"
OBS_VERDICTS = (OBS_WORKED, OBS_FAILED, OBS_INVESTIGATE)

# ── 아티팩트(계보) 유형 ──
ART_LOOP = "LOOP"
ART_LESSON = "LESSON"

# ── 금지(자동 수정·실행) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "AUTO_MODIFY_STRATEGY", "AUTO_UPDATE_MODEL", "AUTO_EXECUTE_LEARNING", "AUTO_MODIFY",
    "AUTO_UPDATE", "AUTO_DEPLOY", "MODIFY_STRATEGY", "MODIFY_MODEL", "DEPLOY", "EXECUTE",
    "APPLY_AUTOMATICALLY",
})


class ImmutableLoopError(Exception):
    """불변 학습 루프(중복) 위반."""


class ImmutableObservationError(Exception):
    """불변 관찰 기록 위반."""


class ImmutableLessonError(Exception):
    """불변 교훈 기록 위반."""


class ImmutableImprovementError(Exception):
    """불변 개선 후보 위반."""


class ImmutableFeedbackError(Exception):
    """불변 피드백 위반."""


class IllegalLearningTransition(Exception):
    """유효하지 않은 학습 상태 전이 — 거부."""


class InvalidVerdict(Exception):
    """미등록 관찰 판정."""


class ForbiddenAutoActionError(Exception):
    """자동 수정/실행/적용 시도 — 거부."""


class UnknownLoopError(Exception):
    """미등록 학습 루프 참조."""


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


# ── 결정적 ID (RL* 스킴 — 기존 rl_ 계층과 다른 접두사·태그) ──
def loop_id(name: str) -> str:
    return "RLL:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def loop_event_id(loop: str, to_state: str, seq: int) -> str:
    return "RLD:" + hashlib.sha1(input_digest(loop, to_state, seq).encode()).hexdigest()[:12]


def observation_id(loop: str, source_ref: str, observation: str) -> str:
    return "RLO:" + hashlib.sha1(
        input_digest(loop, source_ref, observation).encode()).hexdigest()[:12]


def lesson_id(loop: str, title: str) -> str:
    return "RLS:" + hashlib.sha1(input_digest(loop, title).encode()).hexdigest()[:12]


def improvement_id(loop: str, title: str) -> str:
    return "RLI:" + hashlib.sha1(input_digest(loop, title).encode()).hexdigest()[:12]


def feedback_id(loop: str, source: str, seq: int) -> str:
    return "RLF:" + hashlib.sha1(input_digest(loop, source, seq).encode()).hexdigest()[:12]


def pattern_id(loop_a: str, loop_b: str, metric: str) -> str:
    return "RLH:" + hashlib.sha1(input_digest(loop_a, loop_b, metric).encode()).hexdigest()[:12]


def report_id(loop: str, scope: str, generated_at: str) -> str:
    return "RLG:" + hashlib.sha1(
        input_digest(loop, scope, generated_at).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "RLA:" + hashlib.sha1(input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word: str) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, set())


def compare_direction(value_a: float, value_b: float, higher_is_better: bool = True) -> tuple:
    """사이클 비교 방향·델타(결정적). 반환 (direction, delta)."""
    delta = round(float(value_b) - float(value_a), 8)
    if delta == 0:
        return "UNCHANGED", 0.0
    improved = (delta > 0) if higher_is_better else (delta < 0)
    return ("IMPROVED" if improved else "REGRESSED"), delta


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
class LoopEventRecord:
    loop_event_id: str
    loop_id: str
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
class ObservationRecord:
    observation_id: str
    loop_id: str
    source_layer: str
    source_ref: str
    observation: str
    verdict: str
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LessonRecord:
    lesson_id: str
    loop_id: str
    title: str
    lesson: str
    category: str
    evidence_ref: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ImprovementCandidateRecord:
    improvement_id: str
    loop_id: str
    title: str
    description: str
    rationale: str
    applied: bool
    reviewer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FeedbackRecord:
    feedback_id: str
    loop_id: str
    source: str
    feedback: str
    sentiment: str
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PatternRecord:
    pattern_id: str
    loop_a: str
    loop_b: str
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
class LearningReportRecord:
    report_id: str
    loop_id: str
    scope: str
    observation_count: int
    lesson_count: int
    improvement_count: int
    feedback_count: int
    verdict_distribution: dict
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
class LearningSummary:
    timestamp: str
    loop_event_count: int
    observation_count: int
    lesson_count: int
    improvement_count: int
    feedback_count: int
    pattern_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
