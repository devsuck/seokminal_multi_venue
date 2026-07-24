"""Research Operating System Core 자료형 (P10.30) — Phase 10 최종 상위 연구 운영 환경. **관측 전용.**

10대 아키텍처 도메인(Data·Model·Alpha·Portfolio·Simulation·Decision·Agent·Knowledge·Audit·Control Plane)에
걸쳐 전 계층(P9.8~P10.29)을 **READ ONLY** 로 참조(파일 기반, import 없음)해 OS 레지스트리·글로벌 연구 상태·모듈
카탈로그·시스템 스냅샷·연구 리포트를 남긴다. **이 계층은 관측만 한다 — execute·trade·deploy·allocate·modify
없음.** OBSERVE ≠ EXECUTE · SNAPSHOT ≠ DEPLOY · HEALTH ≠ ACTION · REPORT ≠ TRADE. 불변·append-only·결정적.
물리 원장은 rosc_ 접두사.

주: 상위 스펙의 이름 jarvis/research_os/ 는 이미 존재(ros_ 접두사, 선행 Phase)하므로 충돌을 피해 미사용
네임스페이스 jarvis/research_os_core/ (rosc_) 에 배치한다. 기존 research_os 는 READ ONLY 로만 참조.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 10대 아키텍처 도메인 ──
D_DATA = "DATA"
D_MODEL = "MODEL"
D_ALPHA = "ALPHA"
D_PORTFOLIO = "PORTFOLIO"
D_SIMULATION = "SIMULATION"
D_DECISION = "DECISION"
D_AGENT = "AGENT"
D_KNOWLEDGE = "KNOWLEDGE"
D_AUDIT = "AUDIT"
D_CONTROL_PLANE = "CONTROL_PLANE"
DOMAINS = (D_DATA, D_MODEL, D_ALPHA, D_PORTFOLIO, D_SIMULATION, D_DECISION, D_AGENT,
           D_KNOWLEDGE, D_AUDIT, D_CONTROL_PLANE)

# ── 도메인 데이터 흐름 의존성(DAG) — dependency integrity 검증용 ──
DOMAIN_DEPS = (
    (D_DATA, D_MODEL),
    (D_DATA, D_ALPHA),
    (D_MODEL, D_ALPHA),
    (D_ALPHA, D_PORTFOLIO),
    (D_PORTFOLIO, D_SIMULATION),
    (D_SIMULATION, D_DECISION),
    (D_KNOWLEDGE, D_ALPHA),
    (D_KNOWLEDGE, D_DECISION),
    (D_DECISION, D_CONTROL_PLANE),
    (D_AGENT, D_CONTROL_PLANE),
    (D_AUDIT, D_CONTROL_PLANE),
)

# ── 모듈 상태 ──
STATE_ACTIVE = "ACTIVE"
STATE_EMPTY = "EMPTY"
STATE_MISSING = "MISSING"
STATES = (STATE_ACTIVE, STATE_EMPTY, STATE_MISSING)

# ── OS 헬스 등급 ──
HEALTH_HEALTHY = "HEALTHY"
HEALTH_DEGRADED = "DEGRADED"
HEALTH_CRITICAL = "CRITICAL"
HEALTH_UNKNOWN = "UNKNOWN"
HEALTH_LEVELS = (HEALTH_HEALTHY, HEALTH_DEGRADED, HEALTH_CRITICAL, HEALTH_UNKNOWN)

# ── 헬스 가중치·임계 ──
_W_COVERAGE = 0.5
_W_ACTIVITY = 0.3
_W_INTEGRITY = 0.2
_TH_HEALTHY = 0.8
_TH_DEGRADED = 0.5


class ImmutableModuleError(Exception):
    """불변 모듈 등록 위반."""


class ImmutableCatalogError(Exception):
    """불변 모듈 카탈로그 위반."""


class ImmutableStateError(Exception):
    """불변 글로벌 상태 위반."""


class ImmutableSnapshotError(Exception):
    """불변 시스템 스냅샷 위반."""


class ImmutableReportError(Exception):
    """불변 연구 리포트 위반."""


class InvalidDomain(Exception):
    """미등록 아키텍처 도메인."""


class UnknownModuleError(Exception):
    """미등록 모듈 참조."""


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
def module_id(name: str) -> str:
    return "OSM:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def catalog_id(domain: str, module: str) -> str:
    return "OSC:" + hashlib.sha1(input_digest(domain, module).encode()).hexdigest()[:12]


def state_id(scope: str, computed_at: str) -> str:
    return "OSS:" + hashlib.sha1(input_digest(scope, computed_at).encode()).hexdigest()[:12]


def snapshot_id(scope: str, snapshot_at: str) -> str:
    return "OSN:" + hashlib.sha1(input_digest(scope, snapshot_at).encode()).hexdigest()[:12]


def report_id(scope: str, generated_at: str) -> str:
    return "OSR:" + hashlib.sha1(input_digest(scope, generated_at).encode()).hexdigest()[:12]


# ── 결정적 분석 함수 ──
def os_health_score(coverage: float, activity: float, integrity_ok: bool) -> float:
    """도메인 커버리지·모듈 활성·무결성 가중합(0~1, 결정적). **HEALTH ≠ ACTION.**"""
    integ = 1.0 if integrity_ok else 0.0
    return round(_W_COVERAGE * coverage + _W_ACTIVITY * activity + _W_INTEGRITY * integ, 8)


def health_level(score: float, module_count: int) -> str:
    if module_count <= 0:
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
    """도메인 의존성 이슈(결정적): 미지 노드·순환. 정렬 반환. **탐지만.**"""
    nodeset = set(nodes or [])
    issues: list = []
    for src, tgt in edges:
        if src not in nodeset:
            issues.append(f"unknown_source:{src}")
        if tgt not in nodeset:
            issues.append(f"unknown_target:{tgt}")
    cyc = detect_cycle(edges)
    if cyc:
        issues.append("dependency_cycle:" + "->".join(cyc))
    return sorted(set(issues))


def domain_coverage(covered: int, total: int) -> float:
    return round((float(covered) / total) if total > 0 else 0.0, 8)


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class ModuleRecord:
    module_id: str
    name: str
    domain: str
    phase: str
    ledger_file: str
    id_field: str
    registered_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CatalogRecord:
    catalog_id: str
    domain: str
    module: str
    ledger_file: str
    phase: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GlobalStateRecord:
    state_id: str
    scope: str
    module_count: int
    active_module_count: int
    covered_domains: int
    domain_coverage: float
    module_activity: float
    integrity_ok: bool
    overall_score: float
    level: str
    computed_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SnapshotRecord:
    snapshot_id: str
    scope: str
    module_count: int
    active_module_count: int
    domain_count: int
    covered_domains: int
    domain_coverage: float
    per_domain: dict
    overall_score: float
    health_level: str
    phase_distribution: dict
    disclaimer: str
    snapshot_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GlobalReportRecord:
    report_id: str
    scope: str
    module_count: int
    active_module_count: int
    domain_count: int
    covered_domains: int
    domain_coverage: float
    overall_score: float
    health_level: str
    per_domain: dict
    phase_distribution: dict
    dependency_ok: bool
    compliance_ok: bool
    metrics: dict
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class OSSummary:
    timestamp: str
    module_count: int
    catalog_count: int
    state_count: int
    snapshot_count: int
    report_count: int

    def to_dict(self) -> dict:
        return asdict(self)
