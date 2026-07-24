"""Research Control Plane 자료형 (P10.28) — Research OS 전체의 중앙 관측·조율 평면. **관측 전용.**

전 계층(P9.8~P10.27)을 **READ ONLY** 로 참조(파일 기반, import 없음)해 시스템 개요·계층 상태·의존성 상태·
거버넌스 대시보드 데이터·연구 타임라인·헬스 지표·컨트롤 리포트를 남긴다. **실행 컨트롤러가 아니다 —
관측·집계·시각화·리포트만.** execute/trade/order/allocation/deployment/permission·config 변경 없음.
OBSERVE ≠ EXECUTE · STATUS ≠ CONTROL · HEALTH ≠ ACTION · REPORT ≠ DEPLOYMENT. 불변·append-only·결정적.
물리 원장은 rcp_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"
_EPS = 1e-9

# ── 컴포넌트 카테고리 ──
CAT_GOVERNANCE = "GOVERNANCE"
CAT_RESEARCH = "RESEARCH"
CAT_INTELLIGENCE = "INTELLIGENCE"
CAT_OBSERVABILITY = "OBSERVABILITY"
CAT_OTHER = "OTHER"
CATEGORIES = (CAT_GOVERNANCE, CAT_RESEARCH, CAT_INTELLIGENCE, CAT_OBSERVABILITY, CAT_OTHER)

# ── 컴포넌트 상태(계층 상태) ──
STATE_ACTIVE = "ACTIVE"
STATE_EMPTY = "EMPTY"
STATE_MISSING = "MISSING"
STATES = (STATE_ACTIVE, STATE_EMPTY, STATE_MISSING)

# ── 헬스 등급 ──
HEALTH_HEALTHY = "HEALTHY"
HEALTH_DEGRADED = "DEGRADED"
HEALTH_CRITICAL = "CRITICAL"
HEALTH_UNKNOWN = "UNKNOWN"
HEALTH_LEVELS = (HEALTH_HEALTHY, HEALTH_DEGRADED, HEALTH_CRITICAL, HEALTH_UNKNOWN)

# ── 의존성 관계 ──
REL_READS = "reads"
RELATIONS = (REL_READS,)

# ── 의존성 이슈 유형 ──
ISSUE_DANGLING = "dangling_target"
ISSUE_MISSING_SOURCE = "missing_source"
ISSUE_CYCLE = "dependency_cycle"
ISSUE_SELF = "self_dependency"
ISSUE_TYPES = (ISSUE_DANGLING, ISSUE_MISSING_SOURCE, ISSUE_CYCLE, ISSUE_SELF)

# ── 타임라인 이벤트 종류 ──
TL_COMPONENT_REGISTERED = "COMPONENT_REGISTERED"
TL_STATUS_COLLECTED = "STATUS_COLLECTED"
TL_DEPENDENCY_MAPPED = "DEPENDENCY_MAPPED"
TL_HEALTH_COMPUTED = "HEALTH_COMPUTED"
TL_OVERVIEW_BUILT = "OVERVIEW_BUILT"
TL_REPORT_GENERATED = "REPORT_GENERATED"
TL_KINDS = (TL_COMPONENT_REGISTERED, TL_STATUS_COLLECTED, TL_DEPENDENCY_MAPPED,
            TL_HEALTH_COMPUTED, TL_OVERVIEW_BUILT, TL_REPORT_GENERATED)

# ── 헬스 가중치·임계 ──
_W_COMPONENT = 0.6
_W_DEPENDENCY = 0.4
_TH_HEALTHY = 0.8
_TH_DEGRADED = 0.5


class ImmutableComponentError(Exception):
    """불변 컴포넌트 등록 위반."""


class ImmutableStatusError(Exception):
    """불변 계층 상태 위반."""


class ImmutableDependencyError(Exception):
    """불변 의존성 위반."""


class ImmutableHealthError(Exception):
    """불변 헬스 지표 위반."""


class ImmutableOverviewError(Exception):
    """불변 시스템 개요 위반."""


class ImmutableDashboardError(Exception):
    """불변 거버넌스 대시보드 위반."""


class ImmutableReportError(Exception):
    """불변 컨트롤 리포트 위반."""


class InvalidComponentCategory(Exception):
    """미등록 컴포넌트 카테고리."""


class UnknownComponentError(Exception):
    """미등록 컴포넌트 참조."""


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


# ── 결정적 ID ──
def component_id(name: str) -> str:
    return "RCC:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def status_id(component: str, observed_at: str) -> str:
    return "RCS:" + hashlib.sha1(
        input_digest(component, observed_at).encode()).hexdigest()[:12]


def dependency_id(source: str, target: str) -> str:
    return "RCD:" + hashlib.sha1(
        input_digest(source, target).encode()).hexdigest()[:12]


def overview_id(scope: str, snapshot_at: str) -> str:
    return "RCO:" + hashlib.sha1(
        input_digest(scope, snapshot_at).encode()).hexdigest()[:12]


def dashboard_id(scope: str, generated_at: str) -> str:
    return "RCB:" + hashlib.sha1(
        input_digest(scope, generated_at).encode()).hexdigest()[:12]


def timeline_id(kind: str, reference: str, occurred_at: str) -> str:
    return "RCT:" + hashlib.sha1(
        input_digest(kind, reference, occurred_at).encode()).hexdigest()[:12]


def health_id(scope: str, computed_at: str) -> str:
    return "RCH:" + hashlib.sha1(
        input_digest(scope, computed_at).encode()).hexdigest()[:12]


def report_id(scope: str, generated_at: str) -> str:
    return "RCR:" + hashlib.sha1(
        input_digest(scope, generated_at).encode()).hexdigest()[:12]


# ── 결정적 분석 함수 ──
def health_score(active: int, total: int, issues: int, dependencies: int) -> float:
    """컴포넌트 활성 비율·의존성 무결성 비율 가중합(0~1, 결정적). **HEALTH ≠ ACTION.**"""
    comp = (float(active) / total) if total > 0 else 0.0
    dep = (1.0 - float(issues) / dependencies) if dependencies > 0 else 1.0
    dep = max(0.0, min(1.0, dep))
    return round(_W_COMPONENT * comp + _W_DEPENDENCY * dep, 8)


def health_level(score: float, total: int) -> str:
    if total <= 0:
        return HEALTH_UNKNOWN
    if score >= _TH_HEALTHY:
        return HEALTH_HEALTHY
    if score >= _TH_DEGRADED:
        return HEALTH_DEGRADED
    return HEALTH_CRITICAL


def detect_cycle(edges: list) -> list:
    """방향 그래프 순환 탐지(DFS, 결정적). 첫 순환 경로 반환 또는 []."""
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


def dependency_issues(edges: list, nodes: list) -> list:
    """의존성 이슈(결정적): self·dangling target·missing source·cycle. 정렬 반환. **탐지만.**"""
    nodeset = set(nodes or [])
    issues: list = []
    for src, tgt in edges:
        if src == tgt:
            issues.append(f"{ISSUE_SELF}:{src}")
            continue
        if src not in nodeset:
            issues.append(f"{ISSUE_MISSING_SOURCE}:{src}")
        if tgt not in nodeset:
            issues.append(f"{ISSUE_DANGLING}:{src}->{tgt}")
    cyc = detect_cycle([(a, b) for a, b in edges if a != b])
    if cyc:
        issues.append(f"{ISSUE_CYCLE}:" + "->".join(cyc))
    return sorted(set(issues))


def reachable_from(edges: list, start: str) -> list:
    """start 에서 방향 간선으로 도달 가능한 노드(결정적 정렬)."""
    adj: dict = {}
    for a, b in edges:
        adj.setdefault(a, set()).add(b)
    seen: set = set()
    stack = [start]
    while stack:
        x = stack.pop()
        for y in sorted(adj.get(x, ())):
            if y not in seen:
                seen.add(y)
                stack.append(y)
    return sorted(seen)


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class ComponentRecord:
    component_id: str
    name: str
    layer: str
    phase: str
    category: str
    ledger_file: str
    id_field: str
    registered_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LayerStatusRecord:
    status_id: str
    component: str
    state: str
    record_count: int
    present: bool
    last_activity: str
    observed_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DependencyRecord:
    dependency_id: str
    source: str
    target: str
    relation: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SystemOverviewRecord:
    overview_id: str
    scope: str
    component_count: int
    active_component_count: int
    dependency_count: int
    dependency_issue_count: int
    overall_score: float
    health_level: str
    phase_distribution: dict
    category_distribution: dict
    disclaimer: str
    snapshot_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GovernanceDashboardRecord:
    dashboard_id: str
    scope: str
    component_count: int
    active_component_count: int
    health_level: str
    overall_score: float
    panels: dict
    disclaimer: str
    generated_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TimelineEventRecord:
    event_id: str
    kind: str
    reference: str
    detail: str
    occurred_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class HealthMetricRecord:
    health_id: str
    scope: str
    component_count: int
    active_component_count: int
    dependency_count: int
    dependency_issue_count: int
    component_health: float
    dependency_health: float
    overall_score: float
    level: str
    computed_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ControlReportRecord:
    report_id: str
    scope: str
    component_count: int
    active_component_count: int
    dependency_count: int
    dependency_issue_count: int
    overall_score: float
    health_level: str
    phase_distribution: dict
    category_distribution: dict
    issues: list
    metrics: dict
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ControlPlaneSummary:
    timestamp: str
    component_count: int
    status_count: int
    dependency_count: int
    overview_count: int
    dashboard_count: int
    timeline_count: int
    health_count: int
    report_count: int

    def to_dict(self) -> dict:
        return asdict(self)
