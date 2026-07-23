"""Research Governance Feedback Intelligence 자료형 (P10.20) — 거버넌스 폐루프 학습 기록 전용.

P9.8~P10.19 전 계층을 **READ ONLY** 로 참조(파일 기반, import 없음)해 피드백 레지스트리·거버넌스 이슈
레지스트리·패턴 탐지 기록·개선 테마 레지스트리·피드백 집계·거버넌스 추세 리포트·피드백 계보를 제공한다.
반복 거버넌스 이슈·재발 실패·개선 기회·과거 해소·장기 추세를 추적한다. **정책 수정·permission 변경·config
변경·자동 이슈 수정·변경 승인 없음.** FEEDBACK ≠ CHANGE · PATTERN ≠ DECISION · RECOMMENDATION ≠
IMPLEMENTATION · TREND ≠ AUTOMATIC ACTION. 불변·append-only 해시체인·결정적. 물리 원장은 gf_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"
_EPS = 1e-9

# ── 피드백 범주 ──
F_DATA_ISSUE = "data_issue"
F_VALIDATION_ISSUE = "validation_issue"
F_LINEAGE_ISSUE = "lineage_issue"
F_WORKFLOW_ISSUE = "workflow_issue"
F_DOCUMENTATION_ISSUE = "documentation_issue"
F_GOVERNANCE_ISSUE = "governance_issue"
FEEDBACK_CATEGORIES = (F_DATA_ISSUE, F_VALIDATION_ISSUE, F_LINEAGE_ISSUE, F_WORKFLOW_ISSUE,
                       F_DOCUMENTATION_ISSUE, F_GOVERNANCE_ISSUE)

# ── 이슈 생명주기 ──
DETECTED = "DETECTED"
ANALYZED = "ANALYZED"
TRACKED = "TRACKED"
ARCHIVED = "ARCHIVED"
ISSUE_STATES = (DETECTED, ANALYZED, TRACKED, ARCHIVED)
ISSUE_TRANSITIONS = {
    "": {DETECTED},
    DETECTED: {ANALYZED, ARCHIVED},
    ANALYZED: {TRACKED, ARCHIVED},
    TRACKED: {ARCHIVED},
    ARCHIVED: set(),
}

SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
_SEVERITY_WEIGHT = {"LOW": 0.25, "MEDIUM": 0.5, "HIGH": 0.75, "CRITICAL": 1.0}

IMPACTS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
PRIORITIES = ("LOW", "MEDIUM", "HIGH", "URGENT")

# ── 검토 결정(분석 전용, 비집행) ──
ACKNOWLEDGE = "ACKNOWLEDGE"
ESCALATE = "ESCALATE"
MONITOR = "MONITOR"
REVIEW_DECISIONS = (ACKNOWLEDGE, ESCALATE, MONITOR)

# ── 추세 라벨(정보용) ──
IMPROVING = "IMPROVING"
STABLE = "STABLE"
DECLINING = "DECLINING"

# ── 계보 노드 유형 ──
NODE_LAYER = "LAYER"
NODE_FEEDBACK = "FEEDBACK"
NODE_ISSUE = "ISSUE"
NODE_PATTERN = "PATTERN"
NODE_THEME = "THEME"
NODE_REPORT = "REPORT"
NODE_TYPES = (NODE_LAYER, NODE_FEEDBACK, NODE_ISSUE, NODE_PATTERN, NODE_THEME, NODE_REPORT)

# ── 거버넌스 건강 점수 가중치(합=1.0) — 정보용, 집행/자동조치 아님 ──
GOVERNANCE_WEIGHTS = {
    "issue_resolution_rate": 0.30,
    "recurring_issue_inverse": 0.25,
    "feedback_responsiveness": 0.20,
    "pattern_stability": 0.15,
    "documentation_coverage": 0.10,
}

# ── 거버넌스 건강 라벨 ──
HEALTHY = "HEALTHY"
WARNING = "WARNING"
DEGRADED = "DEGRADED"

# ── 패턴 신뢰도 파라미터 ──
_OCCURRENCE_SATURATION = 5.0
_SOURCE_SATURATION = 3.0

# ── Artifact 유형(계보) ──
ART_LAYER = "LAYER"
ART_FEEDBACK = "FEEDBACK"
ART_ISSUE = "ISSUE"
ART_PATTERN = "PATTERN"
ART_THEME = "THEME"
ART_AGGREGATION = "AGGREGATION"
ART_REVIEW = "REVIEW"
ART_REPORT = "REPORT"


class IllegalTransition(Exception):
    """차단된 생명주기 전이."""


class ImmutableFeedbackError(Exception):
    """불변 피드백 기록 위반."""


class ImmutablePatternError(Exception):
    """불변 패턴 기록 위반."""


class ImmutableThemeError(Exception):
    """불변 개선 테마 위반."""


class UnknownIssue(Exception):
    """미등록 이슈 참조."""


class InvalidFeedbackCategory(Exception):
    """미등록 피드백 범주."""


class InvalidReviewDecision(Exception):
    """유효하지 않은 검토 결정."""


def _can(table: dict, frm: str, to: str) -> bool:
    return to in table.get(frm, set())


def can_transition_issue(frm: str, to: str) -> bool:
    return _can(ISSUE_TRANSITIONS, frm, to)


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
def feedback_id(source_layer: str, category: str, description: str) -> str:
    return "GFB:" + hashlib.sha1(
        input_digest(source_layer, category, description).encode()).hexdigest()[:12]


def issue_id(source: str, impact: str) -> str:
    return "GFI:" + hashlib.sha1(input_digest(source, impact).encode()).hexdigest()[:12]


def issue_event_id(iid: str, frm: str, to: str) -> str:
    return "GIE:" + hashlib.sha1(input_digest(iid, frm, to).encode()).hexdigest()[:12]


def pattern_id(issue_type: str) -> str:
    return "GFP:" + hashlib.sha1(input_digest(issue_type).encode()).hexdigest()[:12]


def theme_id(description: str) -> str:
    return "GFT:" + hashlib.sha1(input_digest(description).encode()).hexdigest()[:12]


def aggregation_id(period: str) -> str:
    return "GFA:" + hashlib.sha1(input_digest(period).encode()).hexdigest()[:12]


def review_id(reviewer: str, target_reference: str) -> str:
    return "GFV:" + hashlib.sha1(
        input_digest(reviewer, target_reference).encode()).hexdigest()[:12]


def report_id(scope: str) -> str:
    return "GFR:" + hashlib.sha1(input_digest(scope).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "GFX:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── 점수/평가(결정적, 정보용) ──
def severity_weight(severity: str) -> float:
    return _SEVERITY_WEIGHT.get(severity, 0.0)


def pattern_confidence(occurrences: int, distinct_sources: int) -> float:
    """반복도·소스 다양성 → 패턴 신뢰도(0~1). **PATTERN ≠ DECISION — 결정 신호 아님.**"""
    base = min(1.0, float(max(0, occurrences)) / _OCCURRENCE_SATURATION)
    breadth = min(1.0, float(max(0, distinct_sources)) / _SOURCE_SATURATION)
    return round(0.6 * base + 0.4 * breadth, 8)


def governance_score(metrics: dict) -> float:
    """가중 거버넌스 건강 점수(0~1). **FEEDBACK ≠ CHANGE — 집행/자동조치 신호 아님.**

    recurring_issue_rate 는 역수(1-rate)로 반영한다."""
    m = dict(metrics or {})
    if "recurring_issue_inverse" not in m and "recurring_issue_rate" in m:
        m["recurring_issue_inverse"] = max(0.0, 1.0 - float(m.get("recurring_issue_rate", 0.0)))
    total = 0.0
    for key, wt in GOVERNANCE_WEIGHTS.items():
        total += float(m.get(key, 0.0)) * float(wt)
    return round(total, 8)


def governance_health(metrics: dict) -> str:
    """거버넌스 지표 → HEALTHY/WARNING/DEGRADED. **정보용 — 자동 조치/승인 없음.**"""
    s = governance_score(metrics)
    if s >= 0.7:
        return HEALTHY
    if s >= 0.4:
        return WARNING
    return DEGRADED


def trend_label(delta: float) -> str:
    """추세 델타 → IMPROVING/STABLE/DECLINING. **TREND ≠ AUTOMATIC ACTION.**"""
    if delta > _EPS:
        return IMPROVING
    if delta < -_EPS:
        return DECLINING
    return STABLE


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
class FeedbackRecord:
    feedback_id: str
    source_layer: str
    category: str
    description: str
    evidence_reference: str
    severity: str
    metadata_hash: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GovernanceIssueEvent:
    event_id: str
    issue_id: str
    source: str
    frequency: int
    impact: str
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
class PatternRecord:
    pattern_id: str
    issue_type: str
    occurrences: int
    related_sources: list
    confidence: float
    metadata_hash: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ImprovementTheme:
    theme_id: str
    description: str
    supporting_feedback: list
    priority: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AggregationRecord:
    aggregation_id: str
    period: str
    metrics: dict
    trend_summary: dict
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FeedbackReview:
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
class GovernanceTrendReport:
    report_id: str
    scope: str
    feedback_count: int
    feedback_category_distribution: dict
    issue_count: int
    issue_state_distribution: dict
    pattern_count: int
    recurring_pattern_count: int
    theme_count: int
    aggregation_count: int
    review_count: int
    unresolved_issue_summary: list
    improvement_opportunity_map: dict
    metrics: dict
    governance_score: float
    governance_health: str
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FeedbackArtifact:
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
class FeedbackSummary:
    timestamp: str
    feedback_count: int
    feedback_category_distribution: dict
    issue_count: int
    issue_state_distribution: dict
    pattern_count: int
    theme_count: int
    aggregation_count: int
    review_count: int
    report_count: int

    def to_dict(self) -> dict:
        return asdict(self)
