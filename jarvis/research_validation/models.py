"""Research Validation & Reproducibility Governance 자료형 (P10.9) — 연구 품질 평가 기록 전용.

P10.2~P10.8 연구 계층을 **READ ONLY** 로 소비해 검증 세션·재현성 체크리스트·증거·리플레이 검증·계보
무결성·검증 점수·감사 요약을 기록한다. **연구 품질 평가 기록만 수행한다.** execution/broker/portfolio
mutation/capital allocation/strategy deployment/model promotion/permission/config/autonomy 변경 없음.
VALIDATED ≠ APPROVED · VALIDATED ≠ DEPLOYABLE. 불변·append-only 해시체인·결정적. 물리 원장은 rv_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

GENESIS = "GENESIS"
_EPS = 1e-9

# ── Validation 생명주기 ──
CREATED = "CREATED"
RUNNING = "RUNNING"
COMPLETED = "COMPLETED"
REVIEWED = "REVIEWED"
ARCHIVED = "ARCHIVED"

VALIDATION_STATES = (CREATED, RUNNING, COMPLETED, REVIEWED, ARCHIVED)
VALIDATION_TRANSITIONS = {
    "": {CREATED},
    CREATED: {RUNNING},
    RUNNING: {COMPLETED},
    COMPLETED: {REVIEWED},
    REVIEWED: {ARCHIVED},
    ARCHIVED: set(),
}

# ── Validation 유형(서술 라벨) ──
LINEAGE_VALIDATION = "LINEAGE"
REPRODUCIBILITY_VALIDATION = "REPRODUCIBILITY"
METADATA_VALIDATION = "METADATA"
FULL_VALIDATION = "FULL"
VALIDATION_TYPES = (LINEAGE_VALIDATION, REPRODUCIBILITY_VALIDATION, METADATA_VALIDATION,
                    FULL_VALIDATION)

# ── 검증 대상 상위 레이어(READ ONLY) ──
TARGET_LAYERS = ("research_governance", "alpha_intelligence", "portfolio_research",
                 "research_kg", "agent_governance", "decision_intelligence",
                 "simulation_environment")

# ── Checklist 항목 ──
LINEAGE_COMPLETENESS = "lineage_completeness"
EXPERIMENT_METADATA_COMPLETENESS = "experiment_metadata_completeness"
DATASET_REFERENCE_INTEGRITY = "dataset_reference_integrity"
PARAMETER_RECORDING_COMPLETENESS = "parameter_recording_completeness"
REPRODUCIBILITY = "reproducibility"
DETERMINISTIC_REPLAY = "deterministic_replay"
ARTIFACT_AVAILABILITY = "artifact_availability"
VALIDATION_INDEPENDENCE = "validation_independence"
CHECKLIST_ITEMS = (LINEAGE_COMPLETENESS, EXPERIMENT_METADATA_COMPLETENESS,
                   DATASET_REFERENCE_INTEGRITY, PARAMETER_RECORDING_COMPLETENESS,
                   REPRODUCIBILITY, DETERMINISTIC_REPLAY, ARTIFACT_AVAILABILITY,
                   VALIDATION_INDEPENDENCE)

# ── Checklist / 검증 결과 라벨 ──
PASS = "PASS"
WARNING = "WARNING"
FAILED = "FAILED"
CHECK_RESULTS = (PASS, WARNING, FAILED)

# ── Replay 검증 결과 ──
REPRODUCIBLE = "REPRODUCIBLE"
NON_REPRODUCIBLE = "NON_REPRODUCIBLE"

# ── Validation Score 가중치(합=1.0) ──
SCORE_WEIGHTS = {
    "lineage": 0.20,
    "reproducibility": 0.20,
    "metadata": 0.15,
    "data_integrity": 0.15,
    "artifact_completeness": 0.15,
    "experiment_quality": 0.15,
}

# ── Artifact 유형(계보) ──
ART_TARGET = "TARGET"
ART_VALIDATION = "VALIDATION"
ART_CHECKLIST = "CHECKLIST"
ART_EVIDENCE = "EVIDENCE"
ART_REPLAY = "REPLAY"
ART_LINEAGE = "LINEAGE_REPORT"
ART_SCORE = "SCORE"


class IllegalTransition(Exception):
    """차단된 검증 생명주기 전이."""


class ImmutableValidationError(Exception):
    """불변 검증 위반(동일 validation_id 내용 상이)."""


class UnknownValidation(Exception):
    """미등록 검증 참조."""


class UnknownSession(Exception):
    """미등록 검증 세션 참조."""


def can_transition_validation(frm: str, to: str) -> bool:
    return to in VALIDATION_TRANSITIONS.get(frm, set())


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


def evidence_hash(evidence: dict) -> str:
    return _digest(dict(evidence or {}))


def output_hash(inputs: dict, metadata: dict, seed: str) -> str:
    """리플레이 검증용 결정적 output 지문 — 같은 입력+metadata+seed → 같은 해시."""
    return _digest({"inputs": dict(inputs or {}), "metadata": dict(metadata or {}),
                    "seed": str(seed)})


# ── 결정적 ID ──
def validation_id(target_layer: str, target_id: str, validation_type: str) -> str:
    return "RVV:" + hashlib.sha1(
        input_digest(target_layer, target_id, validation_type).encode()).hexdigest()[:12]


def validation_event_id(vid: str, frm: str, to: str) -> str:
    return "RVE:" + hashlib.sha1(input_digest(vid, frm, to).encode()).hexdigest()[:12]


def session_id(name: str, validator: str, targets: list) -> str:
    return "RVS:" + hashlib.sha1(
        input_digest(name, validator, sorted(targets or [])).encode()).hexdigest()[:12]


def checklist_id(validation_id_: str) -> str:
    return "RVC:" + hashlib.sha1(input_digest(validation_id_).encode()).hexdigest()[:12]


def evidence_id(validation_id_: str, name: str) -> str:
    return "RVD:" + hashlib.sha1(input_digest(validation_id_, name).encode()).hexdigest()[:12]


def replay_id(validation_id_: str) -> str:
    return "RVP:" + hashlib.sha1(input_digest(validation_id_).encode()).hexdigest()[:12]


def lineage_report_id(validation_id_: str) -> str:
    return "RVL:" + hashlib.sha1(input_digest(validation_id_).encode()).hexdigest()[:12]


def score_id(validation_id_: str) -> str:
    return "RVSC:" + hashlib.sha1(input_digest(validation_id_).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "RVA:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── Checklist 평가(결정적) ──
def checklist_result(passed: bool, warn: bool = False) -> str:
    if not passed:
        return FAILED
    return WARNING if warn else PASS


def checklist_summary(items: dict) -> dict:
    """{item: result} → {pass, warning, failed, overall}. overall: 하나라도 FAILED→FAILED,
    WARNING 있으면 WARNING, 아니면 PASS. 자동 수정 없음 — 라벨만."""
    n_pass = sum(1 for v in items.values() if v == PASS)
    n_warn = sum(1 for v in items.values() if v == WARNING)
    n_fail = sum(1 for v in items.values() if v == FAILED)
    if n_fail:
        overall = FAILED
    elif n_warn:
        overall = WARNING
    else:
        overall = PASS
    return {"pass": n_pass, "warning": n_warn, "failed": n_fail, "overall": overall}


# ── Validation Score 계산(결정적) ──
def compute_score(components: dict) -> float:
    """가중 검증 점수(0~1). **score ≠ approval · score ≠ deployment.**"""
    total = 0.0
    for key, wt in SCORE_WEIGHTS.items():
        total += float(components.get(key, 0.0)) * float(wt)
    return round(total, 8)


def checklist_to_components(items: dict) -> dict:
    """체크리스트 결과 → 점수 컴포넌트(PASS=1.0, WARNING=0.5, FAILED=0.0)."""
    def _v(item):
        r = items.get(item, FAILED)
        return 1.0 if r == PASS else (0.5 if r == WARNING else 0.0)
    return {
        "lineage": _v(LINEAGE_COMPLETENESS),
        "reproducibility": (_v(REPRODUCIBILITY) + _v(DETERMINISTIC_REPLAY)) / 2.0,
        "metadata": _v(EXPERIMENT_METADATA_COMPLETENESS),
        "data_integrity": _v(DATASET_REFERENCE_INTEGRITY),
        "artifact_completeness": _v(ARTIFACT_AVAILABILITY),
        "experiment_quality": (_v(PARAMETER_RECORDING_COMPLETENESS)
                               + _v(VALIDATION_INDEPENDENCE)) / 2.0,
    }


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
class ValidationEvent:
    """검증 등록·상태 전이 이벤트(이벤트 소싱). 정체성 불변."""
    event_id: str
    validation_id: str
    target_layer: str
    target_id: str
    validation_type: str
    session_reference: str
    from_state: str
    to_state: str
    status: str
    score: float
    evidence_hash: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ValidationSession:
    session_id: str
    name: str
    validator: str
    targets: list
    objective: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ReproducibilityChecklist:
    checklist_id: str
    validation_id: str
    items: dict                     # {checklist_item: PASS|WARNING|FAILED}
    summary: dict                   # {pass, warning, failed, overall}
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    validation_id: str
    name: str
    evidence_type: str
    reference: str                  # 외부 레이어/원장 참조 문자열(READ ONLY)
    evidence_hash: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ReplayReport:
    replay_id: str
    validation_id: str
    original_output_hash: str
    replay_output_hash: str
    result: str                     # REPRODUCIBLE | NON_REPRODUCIBLE
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LineageReport:
    lineage_report_id: str
    validation_id: str
    target_layer: str
    issues: list
    n_checked: int
    ok: bool
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ValidationScore:
    score_id: str
    validation_id: str
    components: dict
    overall_score: float            # 0~1 — score ≠ approval · score ≠ deployment
    grade: str                      # 서술 등급(A/B/C/D) — 승인 아님
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ValidationArtifact:
    artifact_id: str
    artifact_type: str
    ref_id: str
    parent_artifact: str
    validation_id: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ValidationAuditSummary:
    timestamp: str
    validation_count: int
    validation_state_distribution: dict
    validation_type_distribution: dict
    target_layer_distribution: dict
    session_count: int
    checklist_count: int
    checklist_overall_distribution: dict
    evidence_count: int
    replay_count: int
    non_reproducible_count: int
    lineage_report_count: int
    lineage_issue_count: int
    score_count: int
    mean_score: float

    def to_dict(self) -> dict:
        return asdict(self)


def score_grade(score: float) -> str:
    """0~1 점수를 서술 등급으로. **승인/배포 아님 — 연구 품질 라벨.**"""
    s = float(score)
    if s >= 0.85:
        return "A"
    if s >= 0.7:
        return "B"
    if s >= 0.5:
        return "C"
    return "D"
