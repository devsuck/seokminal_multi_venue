"""Research Orchestration & Workflow Intelligence 자료형 (P10.17) — 연구 과정 가시성·조정 전용.

P9.8~P10.16 전 계층을 **READ ONLY** 로 참조(파일 기반, import 없음)해 연구 워크플로 레지스트리·파이프라인
정의·태스크·의존 그래프·실행 이력·이벤트 이력·병목 레지스트리·오케스트레이션 리포트·연구 계보를 관리한다.
**연구를 실행하지 않는다.** strategy/signal 실행·portfolio 수정·order 생성·capital 배분·live trading·model
배포·자동 연구 트리거·자동 최적화 없음. WORKFLOW STATE ≠ EXECUTION STATE · TASK READY ≠ RUNNING PROCESS ·
WORKFLOW COMPLETED ≠ DEPLOYMENT · ORCHESTRATION ≠ AUTOMATION. 불변·append-only 해시체인·결정적. 원장 or_.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"
_EPS = 1e-9

# ── Workflow 생명주기 ──
CREATED = "CREATED"
PLANNED = "PLANNED"
RUNNING = "RUNNING"
PAUSED = "PAUSED"
COMPLETED = "COMPLETED"
ARCHIVED = "ARCHIVED"

WORKFLOW_STATES = (CREATED, PLANNED, RUNNING, PAUSED, COMPLETED, ARCHIVED)
WORKFLOW_TRANSITIONS = {
    "": {CREATED},
    CREATED: {PLANNED, ARCHIVED},
    PLANNED: {RUNNING, ARCHIVED},
    RUNNING: {PAUSED, COMPLETED, ARCHIVED},
    PAUSED: {RUNNING, COMPLETED, ARCHIVED},
    COMPLETED: {ARCHIVED},
    ARCHIVED: set(),
}

# ── Task 생명주기 ──
READY = "READY"
BLOCKED = "BLOCKED"
IN_PROGRESS = "IN_PROGRESS"
# CREATED / COMPLETED / ARCHIVED 공유

TASK_STATES = (CREATED, READY, BLOCKED, IN_PROGRESS, COMPLETED, ARCHIVED)
TASK_TRANSITIONS = {
    "": {CREATED},
    CREATED: {READY, BLOCKED, ARCHIVED},
    READY: {IN_PROGRESS, BLOCKED, ARCHIVED},
    BLOCKED: {READY, ARCHIVED},
    IN_PROGRESS: {COMPLETED, BLOCKED, ARCHIVED},
    COMPLETED: {ARCHIVED},
    ARCHIVED: set(),
}

# ── Bottleneck 생명주기(해소 추적) ──
OPEN = "OPEN"
ACKNOWLEDGED = "ACKNOWLEDGED"
RESOLVED = "RESOLVED"
# ARCHIVED 공유

BOTTLENECK_STATES = (OPEN, ACKNOWLEDGED, RESOLVED, ARCHIVED)
BOTTLENECK_TRANSITIONS = {
    "": {OPEN},
    OPEN: {ACKNOWLEDGED, RESOLVED, ARCHIVED},
    ACKNOWLEDGED: {RESOLVED, ARCHIVED},
    RESOLVED: {ARCHIVED},
    ARCHIVED: set(),
}

# ── 병목 범주 ──
B_DEPENDENCY_BLOCK = "dependency_block"
B_DATA_MISSING = "data_missing"
B_VALIDATION_FAILED = "validation_failed"
B_RESOURCE_LIMIT = "resource_limit"
B_REPEATED_FAILURE = "repeated_failure"
B_RESEARCH_DEAD_END = "research_dead_end"
BOTTLENECK_CATEGORIES = (B_DEPENDENCY_BLOCK, B_DATA_MISSING, B_VALIDATION_FAILED, B_RESOURCE_LIMIT,
                         B_REPEATED_FAILURE, B_RESEARCH_DEAD_END)

SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
_SEVERITY_WEIGHT = {"LOW": 0.25, "MEDIUM": 0.5, "HIGH": 0.75, "CRITICAL": 1.0}

# ── 태스크 유형 ──
T_DATA_PREP = "DATA_PREP"
T_FEATURE = "FEATURE"
T_HYPOTHESIS = "HYPOTHESIS"
T_BACKTEST = "BACKTEST"
T_VALIDATION = "VALIDATION"
T_SIMULATION = "SIMULATION"
T_REVIEW = "REVIEW"
T_ANALYSIS = "ANALYSIS"
TASK_TYPES = (T_DATA_PREP, T_FEATURE, T_HYPOTHESIS, T_BACKTEST, T_VALIDATION, T_SIMULATION,
              T_REVIEW, T_ANALYSIS)

# ── 이벤트 유형(예시) ──
EV_WORKFLOW_CREATED = "WORKFLOW_CREATED"
EV_TASK_REGISTERED = "TASK_REGISTERED"
EV_STATE_CHANGED = "STATE_CHANGED"
EV_BOTTLENECK_FLAGGED = "BOTTLENECK_FLAGGED"
EV_RUN_RECORDED = "RUN_RECORDED"
EVENT_TYPES = (EV_WORKFLOW_CREATED, EV_TASK_REGISTERED, EV_STATE_CHANGED, EV_BOTTLENECK_FLAGGED,
               EV_RUN_RECORDED)

# ── 계보 노드 유형 ──
NODE_WORKFLOW = "WORKFLOW"
NODE_PIPELINE = "PIPELINE"
NODE_TASK = "TASK"
NODE_RUN = "RUN"
NODE_BOTTLENECK = "BOTTLENECK"
NODE_TYPES = (NODE_WORKFLOW, NODE_PIPELINE, NODE_TASK, NODE_RUN, NODE_BOTTLENECK)

# ── 오케스트레이션 건강 가중치(합=1.0) — 정보용, 실행/자동화 아님 ──
ORCH_WEIGHTS = {
    "task_completion_rate": 0.30,
    "dependency_health": 0.25,
    "bottleneck_resolution_rate": 0.20,
    "workflow_progress": 0.15,
    "lineage_completeness": 0.10,
}

# ── Health 라벨 ──
HEALTHY = "HEALTHY"
WARNING = "WARNING"
DEGRADED = "DEGRADED"

# ── Artifact 유형(계보) ──
ART_WORKFLOW = "WORKFLOW"
ART_PIPELINE = "PIPELINE"
ART_TASK = "TASK"
ART_DEPENDENCY = "DEPENDENCY"
ART_RUN = "RUN"
ART_EVENT = "EVENT"
ART_BOTTLENECK = "BOTTLENECK"
ART_REPORT = "REPORT"


class IllegalTransition(Exception):
    """차단된 생명주기 전이."""


class ImmutableWorkflowError(Exception):
    """불변 워크플로 위반."""


class ImmutablePipelineError(Exception):
    """불변 파이프라인 버전 위반."""


class ImmutableTaskError(Exception):
    """불변 태스크 위반."""


class UnknownWorkflow(Exception):
    """미등록 워크플로 참조."""


class UnknownTask(Exception):
    """미등록 태스크 참조."""


class UnknownBottleneck(Exception):
    """미등록 병목 참조."""


class InvalidBottleneckCategory(Exception):
    """미등록 병목 범주."""


class InvalidDependencyGraph(Exception):
    """유효하지 않은 의존 그래프(미등록 노드/순환/자기참조)."""


def _can(table: dict, frm: str, to: str) -> bool:
    return to in table.get(frm, set())


def can_transition_workflow(frm: str, to: str) -> bool:
    return _can(WORKFLOW_TRANSITIONS, frm, to)


def can_transition_task(frm: str, to: str) -> bool:
    return _can(TASK_TRANSITIONS, frm, to)


def can_transition_bottleneck(frm: str, to: str) -> bool:
    return _can(BOTTLENECK_TRANSITIONS, frm, to)


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
def workflow_id(name: str) -> str:
    return "ORW:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def workflow_event_id(wid: str, frm: str, to: str) -> str:
    return "OWE:" + hashlib.sha1(input_digest(wid, frm, to).encode()).hexdigest()[:12]


def pipeline_id(workflow_id: str, version: str) -> str:
    return "ORP:" + hashlib.sha1(input_digest(workflow_id, version).encode()).hexdigest()[:12]


def task_id(workflow_id: str, name: str) -> str:
    return "ORT:" + hashlib.sha1(input_digest(workflow_id, name).encode()).hexdigest()[:12]


def task_event_id(tid: str, frm: str, to: str) -> str:
    return "OTE:" + hashlib.sha1(input_digest(tid, frm, to).encode()).hexdigest()[:12]


def dependency_id(from_task: str, to_task: str) -> str:
    return "ORD:" + hashlib.sha1(input_digest(from_task, to_task).encode()).hexdigest()[:12]


def run_id(workflow_id: str, sequence: int) -> str:
    return "ORR:" + hashlib.sha1(
        input_digest(workflow_id, int(sequence)).encode()).hexdigest()[:12]


def event_id(scope: str, event_type: str, reference: str) -> str:
    return "OEV:" + hashlib.sha1(
        input_digest(scope, event_type, reference).encode()).hexdigest()[:12]


def bottleneck_id(source_task: str, category: str) -> str:
    return "ORB:" + hashlib.sha1(input_digest(source_task, category).encode()).hexdigest()[:12]


def bottleneck_event_id(bid: str, frm: str, to: str) -> str:
    return "OBE:" + hashlib.sha1(input_digest(bid, frm, to).encode()).hexdigest()[:12]


def report_id(scope: str) -> str:
    return "ORX:" + hashlib.sha1(input_digest(scope).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "ORA:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── 점수(결정적, 정보용) ──
def severity_weight(severity: str) -> float:
    return _SEVERITY_WEIGHT.get(severity, 0.0)


def orchestration_score(metrics: dict) -> float:
    """가중 오케스트레이션 건강 점수(0~1). **ORCHESTRATION ≠ AUTOMATION — 실행 신호 아님.**"""
    total = 0.0
    for key, wt in ORCH_WEIGHTS.items():
        total += float(metrics.get(key, 0.0)) * float(wt)
    return round(total, 8)


def orchestration_health(metrics: dict) -> str:
    """건강 지표 → HEALTHY/WARNING/DEGRADED. **정보용 — 자동 조치/트리거 없음.**"""
    s = orchestration_score(metrics)
    if s >= 0.7:
        return HEALTHY
    if s >= 0.4:
        return WARNING
    return DEGRADED


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
class WorkflowEvent:
    event_id: str
    workflow_id: str
    name: str
    version: str
    objective: str
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
class PipelineVersion:
    pipeline_id: str
    workflow_id: str
    stages: list
    version: str
    metadata_hash: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TaskEvent:
    event_id: str
    task_id: str
    workflow_id: str
    name: str
    task_type: str
    dependencies: list
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
class DependencyEdge:
    dependency_id: str
    from_task: str
    to_task: str
    relation: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class WorkflowRun:
    run_id: str
    workflow_id: str
    sequence: int
    trigger: str
    status: str
    note: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class OrchestrationEvent:
    event_id: str
    scope: str
    event_type: str
    reference: str
    timestamp: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class BottleneckEvent:
    event_id: str
    bottleneck_id: str
    source_task: str
    category: str
    severity: str
    evidence: list
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
class OrchestrationReport:
    report_id: str
    scope: str
    workflow_count: int
    workflow_state_distribution: dict
    pipeline_count: int
    task_count: int
    task_state_distribution: dict
    dependency_count: int
    run_count: int
    bottleneck_count: int
    bottleneck_state_distribution: dict
    metrics: dict
    orchestration_score: float
    orchestration_health: str
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class OrchestrationArtifact:
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
class OrchestrationSummary:
    timestamp: str
    workflow_count: int
    workflow_state_distribution: dict
    pipeline_count: int
    task_count: int
    task_state_distribution: dict
    dependency_count: int
    run_count: int
    event_count: int
    bottleneck_count: int
    bottleneck_state_distribution: dict
    report_count: int

    def to_dict(self) -> dict:
        return asdict(self)
