"""Autonomous Research Pipeline Core 자료형 (P12.1) — 중앙 연구 자동화 파이프라인. **파이프라인 오케스트레이션 전용.**

고립된 연구 컴포넌트를 반복 가능한 연구 사이클로 전환한다(연구 목표 인테이크·가설 생성·실험 계획·실험 실행 조정·
결과 수집·리뷰 라우팅·지식 영속화·개선 사이클). **거래 실행·전략 배포·자본 배분·라이브 시스템 수정·프로덕션
모델 승인·권한 변경을 하지 않는다.** PIPELINE ≠ EXECUTION · STAGE ≠ DEPLOYMENT · COLLECT ≠ APPROVAL. 불변·
append-only·이벤트 소싱·SHA256 해시체인·결정적. 물리 원장은 arp_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 연구 사이클 생애주기(9 단계) ──
S_OBJECTIVE_CREATED = "OBJECTIVE_CREATED"
S_PLANNING = "PLANNING"
S_HYPOTHESIS_FORMING = "HYPOTHESIS_FORMING"
S_EXPERIMENT_DESIGN = "EXPERIMENT_DESIGN"
S_EXPERIMENT_RUNNING = "EXPERIMENT_RUNNING"
S_RESULT_ANALYSIS = "RESULT_ANALYSIS"
S_REVIEW_PENDING = "REVIEW_PENDING"
S_KNOWLEDGE_UPDATE = "KNOWLEDGE_UPDATE"
S_COMPLETED = "COMPLETED"
CYCLE_STAGES = (S_OBJECTIVE_CREATED, S_PLANNING, S_HYPOTHESIS_FORMING, S_EXPERIMENT_DESIGN,
                S_EXPERIMENT_RUNNING, S_RESULT_ANALYSIS, S_REVIEW_PENDING, S_KNOWLEDGE_UPDATE,
                S_COMPLETED)
# 선형 순서 인덱스(스킵/역행 탐지)
STAGE_ORDER = {s: i for i, s in enumerate(CYCLE_STAGES)}

# 오직 유효한 선형 전이만 허용(스킵·역행·무단 완료 거부)
ALLOWED_TRANSITIONS = {
    S_OBJECTIVE_CREATED: {S_PLANNING},
    S_PLANNING: {S_HYPOTHESIS_FORMING},
    S_HYPOTHESIS_FORMING: {S_EXPERIMENT_DESIGN},
    S_EXPERIMENT_DESIGN: {S_EXPERIMENT_RUNNING},
    S_EXPERIMENT_RUNNING: {S_RESULT_ANALYSIS},
    S_RESULT_ANALYSIS: {S_REVIEW_PENDING},
    S_REVIEW_PENDING: {S_KNOWLEDGE_UPDATE},
    S_KNOWLEDGE_UPDATE: {S_COMPLETED},
    S_COMPLETED: set(),
}

# ── 파이프라인 상태 모델 참조 유형(8) ──
REF_OBJECTIVE = "objective"
REF_HYPOTHESIS = "hypothesis"
REF_EXPERIMENT = "experiment"
REF_AGENT = "agent"
REF_DATASET = "dataset"
REF_RESULT = "result"
REF_REVIEW = "review"
REF_MEMORY = "memory"
REF_TYPES = (REF_OBJECTIVE, REF_HYPOTHESIS, REF_EXPERIMENT, REF_AGENT, REF_DATASET, REF_RESULT,
             REF_REVIEW, REF_MEMORY)

# ── 실행 이력 종류 ──
HIST_REFERENCE = "REFERENCE"
HIST_RESULT = "RESULT"
HIST_REVIEW = "REVIEW"
HIST_STAGE = "STAGE"
HIST_KINDS = (HIST_REFERENCE, HIST_RESULT, HIST_REVIEW, HIST_STAGE)

# ── 파이프라인 컴포넌트(7, 개념) ──
PIPELINE_COMPONENTS = ("OBJECTIVE_MANAGER", "HYPOTHESIS_COORDINATOR", "EXPERIMENT_ROUTER",
                       "RESULT_COLLECTOR", "REVIEW_COORDINATOR", "KNOWLEDGE_CONNECTOR",
                       "CYCLE_TRACKER")

# ── 아티팩트(계보) 유형 ──
ART_CYCLE = "CYCLE"
ART_OBJECTIVE = "OBJECTIVE"
ART_RUN = "RUN"
ART_REPORT = "REPORT"

# ── 금지(실행·승인·배포) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "PROMOTE_MODEL",
    "APPROVE_LIVE", "MODIFY_PERMISSION", "CHANGE_CONFIG", "EXECUTE", "TRADE", "DEPLOY", "APPROVE",
})


class ImmutablePipelineError(Exception):
    """불변 파이프라인 레지스트리 위반."""


class ImmutableObjectiveError(Exception):
    """불변 연구 목표 위반."""


class ImmutableCycleError(Exception):
    """불변 연구 사이클(중복) 위반."""


class ImmutableRunError(Exception):
    """불변 파이프라인 런 위반."""


class ImmutableStageError(Exception):
    """불변 워크플로 스테이지 위반."""


class ImmutableReportError(Exception):
    """불변 리포트 위반."""


class IllegalStageTransition(Exception):
    """유효하지 않은 스테이지 전이(스킵·역행·무단 완료) — 거부."""


class InvalidReferenceType(Exception):
    """미등록 참조 유형."""


class DanglingReferenceError(Exception):
    """dangling 참조 — 거부."""


class MissingArtifactError(Exception):
    """아티팩트 누락 — 거부."""


class UnknownPipelineError(Exception):
    """미등록 파이프라인 참조."""


class UnknownObjectiveError(Exception):
    """미등록 목표 참조."""


class UnknownCycleError(Exception):
    """미등록 사이클 참조."""


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


# ── 결정적 ID (AP* 스킴) ──
def pipeline_id(name: str) -> str:
    return "APG:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def objective_id(pipeline: str, title: str) -> str:
    return "APO:" + hashlib.sha1(input_digest(pipeline, title).encode()).hexdigest()[:12]


def cycle_id(objective: str, iteration: int) -> str:
    return "APC:" + hashlib.sha1(input_digest(objective, iteration).encode()).hexdigest()[:12]


def run_id(cycle: str, label: str) -> str:
    return "APR:" + hashlib.sha1(input_digest(cycle, label).encode()).hexdigest()[:12]


def stage_id(cycle: str, stage: str) -> str:
    return "APS:" + hashlib.sha1(input_digest(cycle, stage).encode()).hexdigest()[:12]


def transition_event_id(cycle: str, to_stage: str, seq: int) -> str:
    return "APV:" + hashlib.sha1(input_digest(cycle, to_stage, seq).encode()).hexdigest()[:12]


def history_id(cycle: str, kind: str, ref_id: str, seq: int) -> str:
    return "APH:" + hashlib.sha1(input_digest(cycle, kind, ref_id, seq).encode()).hexdigest()[:12]


def report_id(scope: str, scope_id: str, generated_at: str) -> str:
    return "APN:" + hashlib.sha1(
        input_digest(scope, scope_id, generated_at).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "APF:" + hashlib.sha1(input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word: str) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, set())


def is_skip(frm: str, to: str) -> bool:
    """스킵 여부(선형 인덱스 기준, 결정적)."""
    if frm not in STAGE_ORDER or to not in STAGE_ORDER:
        return False
    return STAGE_ORDER[to] - STAGE_ORDER[frm] > 1


def is_reverse(frm: str, to: str) -> bool:
    """역행 여부(결정적)."""
    if frm not in STAGE_ORDER or to not in STAGE_ORDER:
        return False
    return STAGE_ORDER[to] < STAGE_ORDER[frm]


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
class PipelineRecord:
    pipeline_id: str
    name: str
    mandate: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ObjectiveRecord:
    objective_id: str
    pipeline_id: str
    title: str
    description: str
    target_metric: str
    evidence_ref: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CycleRecord:
    cycle_id: str
    objective_id: str
    pipeline_id: str
    iteration: int
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    cycle_id: str
    label: str
    note: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class StageRecord:
    stage_id: str
    cycle_id: str
    stage: str
    sequence: int
    note: str
    entered_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TransitionRecord:
    transition_event_id: str
    cycle_id: str
    from_stage: str
    to_stage: str
    valid: bool
    note: str
    occurred_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class HistoryRecord:
    history_id: str
    cycle_id: str
    kind: str
    ref_type: str
    ref_id: str
    detail: str
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PipelineReportRecord:
    report_id: str
    scope: str
    scope_id: str
    cycle_count: int
    objective_count: int
    run_count: int
    stage_count: int
    completed_count: int
    history_count: int
    stage_distribution: dict
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
class PipelineSummary:
    timestamp: str
    pipeline_count: int
    objective_count: int
    cycle_count: int
    run_count: int
    stage_count: int
    transition_count: int
    history_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
