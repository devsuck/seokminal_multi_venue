"""Research Governance Knowledge Memory 자료형 (P10.21) — 재사용 가능한 거버넌스 지식 저장 전용.

P9.8~P10.20 전 계층을 **READ ONLY** 로 참조(파일 기반, import 없음)해 지식 항목 레지스트리·거버넌스 메모리
기록·경험 기록·해소 이력·유사도 참조·메모리 스냅샷·지식 리포트·메모리 계보를 제공한다. 과거 연구 교훈·반복
이슈 해소·검증 경험·거버넌스 패턴·역사적 맥락을 축적한다. **의사결정 실행·정책 변경·config 수정·strategy
승인·model 배포 없음.** MEMORY ≠ AUTHORITY · SIMILARITY ≠ DECISION · HISTORICAL PATTERN ≠ FUTURE ACTION ·
KNOWLEDGE ≠ PERMISSION. 불변·append-only 해시체인·결정적. 물리 원장은 gm_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"
_EPS = 1e-9

# ── 지식 항목 범주 ──
K_RESEARCH_LESSON = "research_lesson"
K_VALIDATION_LESSON = "validation_lesson"
K_FAILURE_PATTERN = "failure_pattern"
K_GOVERNANCE_RULE = "governance_rule"
K_OPERATIONAL_PATTERN = "operational_pattern"
K_HISTORICAL_CONTEXT = "historical_context"
ENTRY_CATEGORIES = (K_RESEARCH_LESSON, K_VALIDATION_LESSON, K_FAILURE_PATTERN, K_GOVERNANCE_RULE,
                    K_OPERATIONAL_PATTERN, K_HISTORICAL_CONTEXT)

# ── 결과/영향 라벨 ──
OUTCOMES = ("SUCCESS", "PARTIAL", "FAILURE", "INCONCLUSIVE")
IMPACTS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
_IMPACT_WEIGHT = {"LOW": 0.25, "MEDIUM": 0.5, "HIGH": 0.75, "CRITICAL": 1.0}

# ── 메모리 링크 유형 ──
SIMILAR_TO = "similar_to"
DERIVED_FROM = "derived_from"
RELATED_TO = "related_to"
CONTRADICTS = "contradicts"
LINK_TYPES = (SIMILAR_TO, DERIVED_FROM, RELATED_TO, CONTRADICTS)
# derived_from 은 인과·계보성(비순환) 관계 — 순환 차단 대상. 나머지는 연관(대칭 허용).
ACYCLIC_LINK_TYPES = (DERIVED_FROM,)

# ── 계보 노드 유형 ──
NODE_LAYER = "LAYER"
NODE_EXPERIENCE = "EXPERIENCE"
NODE_LESSON = "LESSON"
NODE_ENTRY = "ENTRY"
NODE_LINK = "LINK"
NODE_SNAPSHOT = "SNAPSHOT"
NODE_REPORT = "REPORT"
NODE_TYPES = (NODE_LAYER, NODE_EXPERIENCE, NODE_LESSON, NODE_ENTRY, NODE_LINK, NODE_SNAPSHOT,
              NODE_REPORT)

# ── 메모리 건강 점수 가중치(합=1.0) — 정보용, 권한/집행 아님 ──
MEMORY_WEIGHTS = {
    "entry_coverage": 0.25,
    "lesson_density": 0.25,
    "link_connectivity": 0.20,
    "resolution_reuse": 0.20,
    "snapshot_freshness": 0.10,
}

# ── 메모리 건강 라벨 ──
HEALTHY = "HEALTHY"
WARNING = "WARNING"
DEGRADED = "DEGRADED"

# ── Artifact 유형(계보) ──
ART_LAYER = "LAYER"
ART_EXPERIENCE = "EXPERIENCE"
ART_LESSON = "LESSON"
ART_ENTRY = "ENTRY"
ART_RESOLUTION = "RESOLUTION"
ART_LINK = "LINK"
ART_SNAPSHOT = "SNAPSHOT"
ART_REPORT = "REPORT"


class ImmutableEntryError(Exception):
    """불변 지식 항목 위반."""


class ImmutableLessonError(Exception):
    """불변 교훈 기록 위반."""


class ImmutableExperienceError(Exception):
    """불변 경험 기록 위반."""


class ImmutableResolutionError(Exception):
    """불변 해소 이력 위반."""


class InvalidEntryCategory(Exception):
    """미등록 지식 항목 범주."""


class InvalidLinkType(Exception):
    """미등록 메모리 링크 유형."""


class InvalidMemoryLink(Exception):
    """유효하지 않은 메모리 링크(미등록 노드/자기참조/순환)."""


class UnknownSnapshot(Exception):
    """미등록 스냅샷 참조."""


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


def knowledge_content_hash(content) -> str:
    """지식 내용의 결정적 콘텐츠 해시."""
    return _digest(content)


def metadata_hash(metadata: dict) -> str:
    return _digest(dict(metadata or {}))


def snapshot_hash(collected_entries: list, summary: dict) -> str:
    return _digest({"entries": sorted(collected_entries or []), "summary": dict(summary or {})})


# ── 결정적 ID ──
def entry_id(category: str, source_reference: str) -> str:
    return "GME:" + hashlib.sha1(
        input_digest(category, source_reference).encode()).hexdigest()[:12]


def experience_id(event_reference: str) -> str:
    return "GMX:" + hashlib.sha1(input_digest(event_reference).encode()).hexdigest()[:12]


def lesson_id(observation: str, conclusion: str) -> str:
    return "GML:" + hashlib.sha1(
        input_digest(observation, conclusion).encode()).hexdigest()[:12]


def resolution_id(original_issue: str, historical_response: str) -> str:
    return "GMH:" + hashlib.sha1(
        input_digest(original_issue, historical_response).encode()).hexdigest()[:12]


def link_id(from_ref: str, link_type: str, to_ref: str) -> str:
    return "GMK:" + hashlib.sha1(
        input_digest(from_ref, link_type, to_ref).encode()).hexdigest()[:12]


def snapshot_id(name: str, epoch: str) -> str:
    return "GMS:" + hashlib.sha1(input_digest(name, epoch).encode()).hexdigest()[:12]


def report_id(scope: str) -> str:
    return "GMR:" + hashlib.sha1(input_digest(scope).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "GMA:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── 점수/평가(결정적, 정보용) ──
def impact_weight(impact: str) -> float:
    return _IMPACT_WEIGHT.get(impact, 0.0)


def memory_score(metrics: dict) -> float:
    """가중 메모리 건강 점수(0~1). **MEMORY ≠ AUTHORITY — 권한/집행 신호 아님.**"""
    total = 0.0
    for key, wt in MEMORY_WEIGHTS.items():
        total += float(metrics.get(key, 0.0)) * float(wt)
    return round(total, 8)


def memory_health(metrics: dict) -> str:
    """메모리 지표 → HEALTHY/WARNING/DEGRADED. **정보용 — 자동 조치/승인 없음.**"""
    s = memory_score(metrics)
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


def connected_components(edges: list) -> list:
    """무방향 연결 요소(지식 클러스터). 각 요소는 정렬된 노드 리스트."""
    adj: dict = {}
    nodes: set = set()
    for a, b in edges:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
        nodes.add(a)
        nodes.add(b)
    seen: set = set()
    out: list = []
    for n in sorted(nodes):
        if n in seen:
            continue
        stack = [n]
        comp: set = set()
        while stack:
            x = stack.pop()
            if x in comp:
                continue
            comp.add(x)
            seen.add(x)
            for y in adj.get(x, ()):
                if y not in comp:
                    stack.append(y)
        out.append(sorted(comp))
    return sorted(out, key=lambda c: (-len(c), c))


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class KnowledgeEntry:
    entry_id: str
    category: str
    source_reference: str
    content_hash: str
    metadata: dict
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExperienceRecord:
    experience_id: str
    event_reference: str
    outcome: str
    impact: str
    detail: str
    timestamp: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LessonRecord:
    lesson_id: str
    observation: str
    conclusion: str
    evidence: list
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ResolutionHistory:
    resolution_id: str
    original_issue: str
    historical_response: str
    outcome: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MemoryLink:
    link_id: str
    from_ref: str
    link_type: str
    to_ref: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MemorySnapshot:
    snapshot_id: str
    name: str
    epoch: str
    collected_entries: list
    summary: dict
    entry_count: int
    snapshot_hash: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class KnowledgeReport:
    report_id: str
    scope: str
    entry_count: int
    entry_category_distribution: dict
    experience_count: int
    lesson_count: int
    resolution_count: int
    link_count: int
    link_type_distribution: dict
    cluster_count: int
    largest_cluster_size: int
    knowledge_gap_count: int
    snapshot_count: int
    metrics: dict
    memory_score: float
    memory_health: str
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MemoryArtifact:
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
class MemorySummary:
    timestamp: str
    entry_count: int
    entry_category_distribution: dict
    experience_count: int
    lesson_count: int
    resolution_count: int
    link_count: int
    link_type_distribution: dict
    snapshot_count: int
    report_count: int

    def to_dict(self) -> dict:
        return asdict(self)
