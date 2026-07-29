"""Model Governance & AI Oversight 자료형 (P9.9) — 모델 생명주기 관리·감사 전용.

**모델 실행·학습 실행·배포 실행·trading decision 생성 없음.** 등록/버전/학습메타/평가/승인/배포기록/
drift 기록만. 불변·append-only 해시체인·결정적. record_hash = 정렬 canonical json sha256(체인 필드
제외). 물리 원장은 mg_ 접두사(기존 approvals/drift_reports 원장과 충돌 회피).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

GENESIS = "GENESIS"

# ── Model Lifecycle 상태머신 ──
DRAFT = "DRAFT"
TRAINED = "TRAINED"
EVALUATED = "EVALUATED"
APPROVED = "APPROVED"
REJECTED = "REJECTED"
DEPLOYED_CANDIDATE = "DEPLOYED_CANDIDATE"
RETIRED = "RETIRED"

LIFECYCLE_STATES = (DRAFT, TRAINED, EVALUATED, APPROVED, REJECTED,
                    DEPLOYED_CANDIDATE, RETIRED)

ALLOWED_TRANSITIONS = {
    "": {DRAFT},
    DRAFT: {TRAINED},
    TRAINED: {EVALUATED},
    EVALUATED: {APPROVED, REJECTED},
    APPROVED: {DEPLOYED_CANDIDATE, RETIRED},
    DEPLOYED_CANDIDATE: {RETIRED},
    REJECTED: set(),
    RETIRED: set(),
}

# ── 승인 결정 ──
APPROVE = "APPROVE"
REJECT = "REJECT"
_DECISIONS = {APPROVE, REJECT}

# ── Evaluation verdict(기록용 라벨 — 자동 배포 아님) ──
PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"

# ── Drift ──
NO_DRIFT = "NO_DRIFT"
WARNING_DRIFT = "WARNING_DRIFT"
CRITICAL_DRIFT = "CRITICAL_DRIFT"

FEATURE_DRIFT = "FEATURE_DRIFT"
PREDICTION_DRIFT = "PREDICTION_DRIFT"
PERFORMANCE_DRIFT = "PERFORMANCE_DRIFT"
_DRIFT_TYPES = {FEATURE_DRIFT, PREDICTION_DRIFT, PERFORMANCE_DRIFT}

_EPS = 1e-12


class IllegalTransition(Exception):
    """차단된 모델 생명주기 전이."""


class ImmutableModelError(Exception):
    """불변 모델 위반."""


class ImmutableVersionError(Exception):
    """불변 모델 버전 위반(동일 model+version 내용 상이)."""


class ApprovalError(Exception):
    """승인 거버넌스 위반."""


def can_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, set())


def is_valid_decision(d: str) -> bool:
    return d in _DECISIONS


def is_valid_drift_type(t: str) -> bool:
    return t in _DRIFT_TYPES


def version_key(model_id: str, version: str) -> str:
    return f"{model_id}@{version}"


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


def model_hash(model_id: str, name: str, model_type: str, task: str, description: str) -> str:
    return _digest({"model_id": model_id, "name": name, "model_type": model_type,
                    "task": task, "description": description})


def version_hash(model_id: str, version: str, framework: str, params: dict) -> str:
    return _digest({"model_id": model_id, "version": version, "framework": framework,
                    "params": params})


def version_event_id(vkey: str, from_state: str, to_state: str) -> str:
    return "MVE:" + hashlib.sha1(
        input_digest(vkey, from_state, to_state).encode()).hexdigest()[:12]


def training_run_id(vkey: str, input_hash: str) -> str:
    return "MTR:" + hashlib.sha1(input_digest(vkey, input_hash).encode()).hexdigest()[:12]


def evaluation_id(vkey: str, metrics_hash: str) -> str:
    return "MEV:" + hashlib.sha1(input_digest(vkey, metrics_hash).encode()).hexdigest()[:12]


def approval_id(vkey: str, approver: str, decision: str) -> str:
    return "MAP:" + hashlib.sha1(
        input_digest(vkey, approver, decision).encode()).hexdigest()[:12]


def deployment_id(vkey: str, environment: str) -> str:
    return "MDP:" + hashlib.sha1(input_digest(vkey, environment).encode()).hexdigest()[:12]


def drift_report_id(model_id: str, drift_type: str, input_hash: str) -> str:
    return "MDR:" + hashlib.sha1(
        input_digest(model_id, drift_type, input_hash).encode()).hexdigest()[:12]


# ── 평가 verdict(기록 라벨 — 자동 조치 없음) ──
def evaluation_verdict(accuracy: float, sharpe: float, max_drawdown: float,
                       stability: float, confidence_score: float) -> str:
    """성능 지표 → 기록용 라벨(PASS/WARN/FAIL). **자동 배포/조치 아님.**"""
    hard_fail = (sharpe < 0.5) or (max_drawdown < -0.35) or (stability < 0.4)
    strong = (sharpe >= 1.0 and max_drawdown >= -0.2 and stability >= 0.7
              and confidence_score >= 0.7)
    if hard_fail:
        return FAIL
    if strong:
        return PASS
    return WARN


def drift_level(drift_score: float, warning_threshold: float, critical_threshold: float) -> str:
    if drift_score >= critical_threshold:
        return CRITICAL_DRIFT
    if drift_score >= warning_threshold:
        return WARNING_DRIFT
    return NO_DRIFT


def relative_change(baseline: float, current: float) -> float:
    return abs(float(current) - float(baseline)) / max(abs(float(baseline)), _EPS)


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class ModelMetadata:
    model_id: str
    name: str
    description: str
    model_type: str
    task: str
    owner: str
    created_at: str
    model_hash: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ModelVersion:
    """버전 생명주기 이벤트(이벤트 소싱). 현재 상태 = 마지막 to_state."""
    version_id: str
    version_key: str
    model_id: str
    version: str
    framework: str
    version_hash: str
    from_state: str
    to_state: str
    status: str
    created_at: str
    actor: str = "system"
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TrainingRun:
    run_id: str
    version_key: str
    dataset_ref: str
    training_params: dict
    duration_seconds: float
    status: str                     # RECORDED — 실제 학습 실행 아님
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvaluationReport:
    report_id: str
    version_key: str
    accuracy: float
    sharpe: float
    max_drawdown: float
    stability: float
    validation_period: str
    benchmark_comparison: dict
    confidence_score: float
    verdict: str                    # PASS | WARN | FAIL (기록 라벨)
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ModelApproval:
    approval_id: str
    version_key: str
    approver: str
    decision: str                   # APPROVE | REJECT
    rationale: str
    evaluation_ref: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DeploymentRecord:
    deployment_id: str
    version_key: str
    environment: str
    deployed_by: str
    status: str                     # CANDIDATE_RECORDED — 실제 배포 아님
    note: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ModelDriftReport:
    report_id: str
    model_id: str
    version: str
    drift_type: str                 # FEATURE | PREDICTION | PERFORMANCE
    drift_score: float
    drift_level: str                # NO | WARNING | CRITICAL
    baseline: float
    current: float
    findings: list
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ModelGovernanceReport:
    timestamp: str
    model_count: int
    version_count: int
    state_distribution: dict
    approved_count: int
    deployed_candidate_count: int
    drift_critical: int
    drift_warning: int
    average_confidence: float

    def to_dict(self) -> dict:
        return asdict(self)
