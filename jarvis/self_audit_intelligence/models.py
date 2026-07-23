"""Research Self Audit Intelligence 자료형 (P10.24) — 전 연구 생태계 무결성 메타 감사. **READ ONLY 검사 전용.**

P9.8~P10.23 전 계층 원장을 **READ ONLY** 로 검사(파일 기반, import 없음)해 감사 레지스트리·감사 실행·무결성
점검·위반 기록·감사 리포트·감사 계보를 제공한다. **원장·정책·config·permission·strategy·model 을 수정하지
않는다.** 깨진 해시체인·누락 부모·유효하지 않은 생명주기·미문서화 변경·누락 검증을 탐지한다. AUDIT ≠ REPAIR ·
FINDING ≠ FIX · INSPECTION ≠ MODIFICATION · REPORT ≠ ACTION. 불변·append-only 해시체인·결정적. 원장 sa_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"
_EPS = 1e-9

# ── 감사 실행 생명주기 ──
CREATED = "CREATED"
RUNNING = "RUNNING"
COMPLETED = "COMPLETED"
ARCHIVED = "ARCHIVED"
RUN_STATES = (CREATED, RUNNING, COMPLETED, ARCHIVED)
RUN_TRANSITIONS = {
    "": {CREATED},
    CREATED: {RUNNING, ARCHIVED},
    RUNNING: {COMPLETED, ARCHIVED},
    COMPLETED: {ARCHIVED},
    ARCHIVED: set(),
}

# ── 감사 결과 라벨 ──
PASS = "PASS"
WARNING = "WARNING"
CRITICAL = "CRITICAL"
RESULTS = (PASS, WARNING, CRITICAL)
_RESULT_RANK = {PASS: 0, WARNING: 1, CRITICAL: 2}

# ── 무결성 점검 종류 ──
CK_HASH_CHAIN = "hash_chain"            # 깨진 해시체인
CK_LINEAGE = "lineage"                  # 누락 부모(missing parent)
CK_LIFECYCLE = "lifecycle"              # 유효하지 않은 생명주기
CK_DOCUMENTATION = "documentation"      # 미문서화 변경
CK_VALIDATION = "validation_presence"   # 누락 검증(원장 부재)
CHECK_KINDS = (CK_HASH_CHAIN, CK_LINEAGE, CK_LIFECYCLE, CK_DOCUMENTATION, CK_VALIDATION)

SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")

# ── 계보 노드 유형 ──
NODE_AUDIT = "AUDIT"
NODE_RUN = "RUN"
NODE_CHECK = "CHECK"
NODE_VIOLATION = "VIOLATION"
NODE_REPORT = "REPORT"
NODE_TYPES = (NODE_AUDIT, NODE_RUN, NODE_CHECK, NODE_VIOLATION, NODE_REPORT)

# ── Artifact 유형(계보) ──
ART_AUDIT = "AUDIT"
ART_RUN = "RUN"
ART_CHECK = "CHECK"
ART_VIOLATION = "VIOLATION"
ART_REPORT = "REPORT"


class IllegalTransition(Exception):
    """차단된 감사 실행 생명주기 전이."""


class ImmutableAuditError(Exception):
    """불변 감사 정의 위반."""


class UnknownRun(Exception):
    """미등록 감사 실행 참조."""


class InvalidCheckKind(Exception):
    """미등록 점검 종류."""


def can_transition_run(frm: str, to: str) -> bool:
    return to in RUN_TRANSITIONS.get(frm, set())


# ── 해시(상위 계층과 동일 규약 — 상위 체인 재계산 검증에 사용) ──
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
def audit_id(name: str) -> str:
    return "SAA:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def run_id(audit_ref: str, epoch: str) -> str:
    return "SAU:" + hashlib.sha1(input_digest(audit_ref, epoch).encode()).hexdigest()[:12]


def run_event_id(rid: str, frm: str, to: str) -> str:
    return "SAR:" + hashlib.sha1(input_digest(rid, frm, to).encode()).hexdigest()[:12]


def check_id(run_ref: str, layer: str, check_kind: str, locus: str) -> str:
    return "SAC:" + hashlib.sha1(
        input_digest(run_ref, layer, check_kind, locus).encode()).hexdigest()[:12]


def violation_id(run_ref: str, layer: str, check_kind: str, locus: str) -> str:
    return "SAV:" + hashlib.sha1(
        input_digest(run_ref, layer, check_kind, locus).encode()).hexdigest()[:12]


def report_id(run_ref: str) -> str:
    return "SAP:" + hashlib.sha1(input_digest(run_ref).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "SAX:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── 결과 롤업(결정적) ──
def worst_result(results: list) -> str:
    """결과 목록 중 가장 심각한 라벨. **롤업만 — 조치 아님.**"""
    worst = PASS
    for r in results or []:
        if _RESULT_RANK.get(r, 0) > _RESULT_RANK.get(worst, 0):
            worst = r
    return worst


def result_rank(result: str) -> int:
    return _RESULT_RANK.get(result, 0)


# ── 상위 체인 무결성 검증(READ ONLY, 순수 함수) ──
def audit_hash_chain(records: list, id_field: str = "") -> dict:
    """상위 원장의 해시체인 무결성 점검(변조/링크/누락/중복). **읽기 전용 — 원본 무변경.**

    반환: {result, issues}. result ∈ PASS/WARNING/CRITICAL."""
    issues: list = []
    if not records:
        return {"result": PASS, "issues": [], "n": 0}
    prev = GENESIS
    seen: set = set()
    for i, r in enumerate(records):
        if r.get("previous_hash") != prev:
            issues.append(("CRITICAL", f"previous_hash_broken@{i}"))
        if not r.get("record_hash"):
            issues.append(("CRITICAL", f"missing_record_hash@{i}"))
        elif content_hash(r) != r.get("record_hash"):
            issues.append(("CRITICAL", f"record_hash_mismatch@{i}"))
        if id_field:
            rid = r.get(id_field)
            if rid in seen:
                issues.append(("CRITICAL", f"duplicate_id@{i}"))
            seen.add(rid)
        prev = r.get("record_hash") or prev
    result = worst_result([sev for sev, _ in issues]) if issues else PASS
    return {"result": result, "issues": [m for _, m in issues], "n": len(records)}


def audit_lineage(records: list) -> dict:
    """아티팩트 원장 계보 점검: 누락 부모(missing parent)·순환. **읽기 전용.**"""
    issues: list = []
    ids = {a.get("artifact_id") for a in records}
    edges: list = []
    for a in records:
        parent = a.get("parent_artifact")
        if parent:
            if parent not in ids:
                issues.append(f"missing_parent:{a.get('artifact_id')}->{parent}")
            edges.append((a.get("artifact_id"), parent))
    cyc = detect_cycle(edges)
    if cyc:
        issues.append("lineage_cycle:" + "->".join(cyc))
    return {"result": CRITICAL if issues else PASS, "issues": sorted(set(issues)),
            "n": len(records)}


def audit_lifecycle(records: list) -> dict:
    """이벤트 소싱 원장 생명주기 구조 점검: to_state 누락(유효하지 않은 생명주기). **읽기 전용.**"""
    issues: list = []
    for i, r in enumerate(records):
        if "to_state" in r and not r.get("to_state"):
            issues.append(f"empty_to_state@{i}")
    return {"result": WARNING if issues else PASS, "issues": sorted(set(issues)),
            "n": len(records)}


def audit_documentation(records: list) -> dict:
    """미문서화 변경 점검: created_at/record_hash 필수 필드 누락. **읽기 전용.**"""
    issues: list = []
    for i, r in enumerate(records):
        if not r.get("created_at"):
            issues.append(f"undocumented_change:missing_created_at@{i}")
        if not r.get("record_hash"):
            issues.append(f"undocumented_change:missing_record_hash@{i}")
    return {"result": WARNING if issues else PASS, "issues": sorted(set(issues)),
            "n": len(records)}


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
class AuditDefinition:
    audit_id: str
    name: str
    scope: str
    target_layers: list
    metadata_hash: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AuditRunEvent:
    event_id: str
    run_id: str
    audit_ref: str
    scope: str
    epoch: str
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
class IntegrityCheck:
    check_id: str
    run_ref: str
    layer: str
    check_kind: str
    result: str
    locus: str
    detail: str
    evidence: list
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ViolationRecord:
    violation_id: str
    run_ref: str
    layer: str
    check_kind: str
    result: str
    locus: str
    detail: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AuditReport:
    report_id: str
    run_ref: str
    scope: str
    layers_scanned: list
    check_count: int
    check_result_distribution: dict
    check_kind_distribution: dict
    violation_count: int
    violation_kind_distribution: dict
    overall_result: str
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AuditArtifact:
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
class AuditSummary:
    timestamp: str
    audit_count: int
    run_count: int
    run_state_distribution: dict
    check_count: int
    check_result_distribution: dict
    violation_count: int
    report_count: int

    def to_dict(self) -> dict:
        return asdict(self)
