"""Research Compliance & Integrity Governance 자료형 (P10.19) — 연구 산출물 거버넌스 기준 준수 관찰 전용.

P9.8~P10.18 전 계층을 **READ ONLY** 로 참조(파일 기반, import 없음)해 컴플라이언스 규칙 레지스트리·연구 무결성
점검·증거 레지스트리·컴플라이언스 검토·위반 기록·시정 권고·감사 리포트·컴플라이언스 계보를 제공한다.
**위반 자동 수정·연구 산출물 수정·배포 승인·permission 변경·실행 상태 변경 없음.** COMPLIANCE CHECK ≠ APPROVAL ·
VIOLATION DETECTION ≠ CORRECTION · RECOMMENDATION ≠ ACTION · AUDIT RESULT ≠ DEPLOYMENT PERMISSION. 불변·
append-only 해시체인·결정적. 물리 원장은 rc_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"
_EPS = 1e-9

# ── 규칙 범주 ──
C_REPRODUCIBILITY = "reproducibility"
C_DATA_INTEGRITY = "data_integrity"
C_VALIDATION_REQUIREMENT = "validation_requirement"
C_LINEAGE_REQUIREMENT = "lineage_requirement"
C_DOCUMENTATION = "documentation"
C_RISK_DISCLOSURE = "risk_disclosure"
RULE_CATEGORIES = (C_REPRODUCIBILITY, C_DATA_INTEGRITY, C_VALIDATION_REQUIREMENT,
                   C_LINEAGE_REQUIREMENT, C_DOCUMENTATION, C_RISK_DISCLOSURE)

# ── 점검 결과 ──
PASS = "PASS"
WARNING = "WARNING"
FAIL = "FAIL"
CHECK_RESULTS = (PASS, WARNING, FAIL)

# ── 검토 결정 ──
ACCEPT = "ACCEPT"
REQUEST_CHANGE = "REQUEST_CHANGE"
REJECT = "REJECT"
REVIEW_DECISIONS = (ACCEPT, REQUEST_CHANGE, REJECT)

# ── 위반 생명주기 ──
DETECTED = "DETECTED"
REVIEWED = "REVIEWED"
RESOLVED = "RESOLVED"
ARCHIVED = "ARCHIVED"
VIOLATION_STATES = (DETECTED, REVIEWED, RESOLVED, ARCHIVED)
VIOLATION_TRANSITIONS = {
    "": {DETECTED},
    DETECTED: {REVIEWED, ARCHIVED},
    REVIEWED: {RESOLVED, ARCHIVED},
    RESOLVED: {ARCHIVED},
    ARCHIVED: set(),
}

SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
_SEVERITY_WEIGHT = {"LOW": 0.25, "MEDIUM": 0.5, "HIGH": 0.75, "CRITICAL": 1.0}

# ── 컴플라이언스 프레임워크 요구 항목 ──
COMPLETENESS_REQUIREMENTS = ("hypothesis", "dataset_reference", "experiment_lineage")
VALIDATION_REQUIREMENTS = ("out_of_sample", "robustness", "reproducibility")
INTEGRITY_REQUIREMENTS = ("immutable_artifact", "lineage_continuity", "evidence_present")

# ── 권고 우선순위 ──
PRIORITIES = ("LOW", "MEDIUM", "HIGH", "URGENT")

# ── 계보 노드 유형 ──
NODE_OBJECT = "OBJECT"
NODE_RULE = "RULE"
NODE_CHECK = "CHECK"
NODE_EVIDENCE = "EVIDENCE"
NODE_REVIEW = "REVIEW"
NODE_REPORT = "REPORT"
NODE_TYPES = (NODE_OBJECT, NODE_RULE, NODE_CHECK, NODE_EVIDENCE, NODE_REVIEW, NODE_REPORT)

# ── 컴플라이언스 점수 가중치(합=1.0) — 정보용, 승인/배포 아님 ──
COMPLIANCE_WEIGHTS = {
    "rule_coverage": 0.20,
    "evidence_completeness": 0.25,
    "check_pass_rate": 0.25,
    "violation_resolution_rate": 0.20,
    "lineage_integrity": 0.10,
}

# ── 컴플라이언스 상태 라벨 ──
COMPLIANT = "COMPLIANT"
AT_RISK = "AT_RISK"
NON_COMPLIANT = "NON_COMPLIANT"

# ── Artifact 유형(계보) ──
ART_OBJECT = "OBJECT"
ART_RULE = "RULE"
ART_CHECK = "CHECK"
ART_EVIDENCE = "EVIDENCE"
ART_REVIEW = "REVIEW"
ART_VIOLATION = "VIOLATION"
ART_RECOMMENDATION = "RECOMMENDATION"
ART_REPORT = "REPORT"


class IllegalTransition(Exception):
    """차단된 생명주기 전이."""


class ImmutableRuleError(Exception):
    """불변 컴플라이언스 규칙 위반."""


class ImmutableEvidenceError(Exception):
    """불변 증거 기록 위반."""


class ImmutableCheckError(Exception):
    """불변 점검 기록 위반."""


class UnknownRule(Exception):
    """미등록 규칙 참조."""


class UnknownViolation(Exception):
    """미등록 위반 참조."""


class InvalidRuleCategory(Exception):
    """미등록 규칙 범주."""


class InvalidCheckResult(Exception):
    """유효하지 않은 점검 결과."""


class InvalidReviewDecision(Exception):
    """유효하지 않은 검토 결정."""


class MissingReviewer(Exception):
    """검토자 미지정."""


class InvalidViolationCategory(Exception):
    """미등록 위반 범주."""


def _can(table: dict, frm: str, to: str) -> bool:
    return to in table.get(frm, set())


def can_transition_violation(frm: str, to: str) -> bool:
    return _can(VIOLATION_TRANSITIONS, frm, to)


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


def checksum(payload) -> str:
    """증거 아티팩트 체크섬(결정적)."""
    return _digest(payload)


# ── 결정적 ID ──
def rule_id(category: str, description: str, version: str) -> str:
    return "RCR:" + hashlib.sha1(
        input_digest(category, description, version).encode()).hexdigest()[:12]


def check_id(rule_id: str, source_reference: str) -> str:
    return "RCC:" + hashlib.sha1(
        input_digest(rule_id, source_reference).encode()).hexdigest()[:12]


def evidence_id(source: str, artifact_reference: str) -> str:
    return "RCE:" + hashlib.sha1(
        input_digest(source, artifact_reference).encode()).hexdigest()[:12]


def review_id(reviewer: str, target_reference: str) -> str:
    return "RCW:" + hashlib.sha1(
        input_digest(reviewer, target_reference).encode()).hexdigest()[:12]


def violation_id(category: str, source: str) -> str:
    return "RCX:" + hashlib.sha1(input_digest(category, source).encode()).hexdigest()[:12]


def violation_event_id(vid: str, frm: str, to: str) -> str:
    return "RVE:" + hashlib.sha1(input_digest(vid, frm, to).encode()).hexdigest()[:12]


def recommendation_id(target_violation: str, action_description: str) -> str:
    return "RCM:" + hashlib.sha1(
        input_digest(target_violation, action_description).encode()).hexdigest()[:12]


def report_id(scope: str) -> str:
    return "RCP:" + hashlib.sha1(input_digest(scope).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "RCA:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── 점수/평가(결정적, 정보용) ──
def severity_weight(severity: str) -> float:
    return _SEVERITY_WEIGHT.get(severity, 0.0)


def derive_result(checklist: dict) -> str:
    """요구 항목 충족표(dict[str,bool]) → PASS/WARNING/FAIL. **점검 결과 기록용 — 승인 아님.**

    전부 충족 PASS · 일부 충족 WARNING · 전무 FAIL."""
    items = list((checklist or {}).values())
    if not items:
        return FAIL
    met = sum(1 for v in items if bool(v))
    if met == len(items):
        return PASS
    if met == 0:
        return FAIL
    return WARNING


def compliance_score(metrics: dict) -> float:
    """가중 컴플라이언스 점수(0~1). **COMPLIANCE CHECK ≠ APPROVAL — 승인/배포 신호 아님.**"""
    total = 0.0
    for key, wt in COMPLIANCE_WEIGHTS.items():
        total += float(metrics.get(key, 0.0)) * float(wt)
    return round(total, 8)


def compliance_status(metrics: dict) -> str:
    """컴플라이언스 지표 → COMPLIANT/AT_RISK/NON_COMPLIANT. **정보용 — 자동 승인/시정 없음.**"""
    s = compliance_score(metrics)
    if s >= 0.7:
        return COMPLIANT
    if s >= 0.4:
        return AT_RISK
    return NON_COMPLIANT


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
class ComplianceRule:
    rule_id: str
    category: str
    description: str
    severity: str
    version: str
    metadata_hash: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ComplianceCheck:
    check_id: str
    rule_id: str
    source_reference: str
    result: str
    evidence_reference: str
    checklist: dict
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    source: str
    artifact_reference: str
    checksum: str
    epoch: str
    timestamp: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ReviewRecord:
    review_id: str
    reviewer: str
    target_reference: str
    decision: str
    notes: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ViolationEvent:
    event_id: str
    violation_id: str
    category: str
    severity: str
    source: str
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
class RemediationRecommendation:
    recommendation_id: str
    target_violation: str
    action_description: str
    rationale: str
    priority: str
    supporting_evidence: list
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AuditReport:
    report_id: str
    scope: str
    rule_count: int
    rule_category_distribution: dict
    check_count: int
    check_result_distribution: dict
    evidence_count: int
    review_count: int
    review_decision_distribution: dict
    violation_count: int
    violation_state_distribution: dict
    violation_severity_distribution: dict
    recommendation_count: int
    integrity_findings: list
    metrics: dict
    compliance_score: float
    compliance_status: str
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ComplianceArtifact:
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
class ComplianceSummary:
    timestamp: str
    rule_count: int
    rule_category_distribution: dict
    check_count: int
    check_result_distribution: dict
    evidence_count: int
    review_count: int
    review_decision_distribution: dict
    violation_count: int
    violation_state_distribution: dict
    recommendation_count: int
    report_count: int

    def to_dict(self) -> dict:
        return asdict(self)
