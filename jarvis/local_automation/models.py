"""Local Research Automation 자료형 (P45) — 반복 연구 작업 자동화. **워크플로 보조, 거래·배포·배분 없음.**

개인 연구자의 반복 작업(데이터 새로고침·데이터 품질 검사·연구 점검·리포트 생성·메모리 업데이트·헬스 체크)을
잡·스케줄·실행 이력·자동화 로그로 관리한다. **자동화 = 워크플로 보조이며 자동 거래·자동 배포·자동 자본 배분이 아니다.**
AUTOMATION = WORKFLOW ASSISTANCE. execution/broker/live_trading import·호출 없음. 불변·append-only·SHA256 해시체인·
이벤트 소싱·결정적. 물리 원장 la_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 잡 생애주기 — 이벤트 소싱 ──
J_REGISTERED = "REGISTERED"
J_ENABLED = "ENABLED"
J_DISABLED = "DISABLED"
J_ARCHIVED = "ARCHIVED"
JOB_STATES = (J_REGISTERED, J_ENABLED, J_DISABLED, J_ARCHIVED)
JOB_TRANSITIONS = {
    J_REGISTERED: {J_ENABLED, J_ARCHIVED},
    J_ENABLED: {J_DISABLED, J_ARCHIVED},
    J_DISABLED: {J_ENABLED, J_ARCHIVED},
    J_ARCHIVED: set(),
}

# ── 잡 종류(연구 안전 — 거래/배포/배분 없음) ──
JOB_KINDS = ("DATA_REFRESH", "DATA_QUALITY_CHECK", "RESEARCH_CHECK", "REPORT_GENERATION",
             "MEMORY_UPDATE", "HEALTH_CHECK", "NOTIFY")

# ── 실행 상태 ──
RUN_SUCCESS = "SUCCESS"
RUN_FAILED = "FAILED"
RUN_SKIPPED = "SKIPPED"
RUN_STATUSES = (RUN_SUCCESS, RUN_FAILED, RUN_SKIPPED)

# ── 스케줄 케이던스 → 주기(틱 단위, 결정적. 벽시계 없음) ──
CADENCES = {"MANUAL": 0, "HOURLY": 1, "DAILY": 24, "WEEKLY": 168}

# ── 로그 레벨 ──
LOG_LEVELS = ("DEBUG", "INFO", "WARN", "ERROR")

# ── 절대 금지 잡 종류/동사 — 자동화가 절대 하지 않는 것 ──
FORBIDDEN_JOB_KINDS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "ACTIVATE_LIVE",
    "TRADE", "DEPLOY", "ALLOCATE", "LIVE_EXECUTION", "BROKER_ORDER", "AUTO_TRADE", "AUTO_DEPLOY",
    "AUTO_ALLOCATE",
})
FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "ACTIVATE_LIVE",
    "BROKER_EXECUTION", "APPROVE_FOR_TRADING", "EXECUTE", "DEPLOY", "TRADE", "ALLOCATE", "APPROVE",
    "AUTO_TRADE", "AUTO_DEPLOY", "AUTO_ALLOCATE",
})

DISCLAIMER = ("Local Research Automation — AUTOMATION = WORKFLOW ASSISTANCE. 반복 연구 작업(데이터·검사·리포트·"
              "메모리·헬스)의 워크플로 보조·이력 기록일 뿐, 자동 거래·자동 배포·자동 자본 배분이 아니다. "
              "거래/배포/배분 잡은 등록 자체가 거부된다.")


class ImmutableJobError(Exception):
    """불변 잡(중복 genesis) 위반."""


class IllegalJobTransition(Exception):
    """유효하지 않은 잡 전이 — 차단."""


class ForbiddenJobKindError(Exception):
    """금지된 잡 종류(거래·배포·배분) — 차단."""


class UnknownEntityError(Exception):
    """미등록 엔티티 참조."""


def _digest(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def input_digest(*parts) -> str:
    return _digest(list(parts))


def content_hash(record: dict) -> str:
    core = {k: v for k, v in record.items()
            if k not in ("previous_hash", "record_hash")}
    return _digest(core)


def result_digest(payload) -> str:
    return _digest({"payload": payload})


def _id(tag, *parts) -> str:
    return f"{tag}:" + hashlib.sha1(input_digest(*parts).encode()).hexdigest()[:12]


def job_id(name) -> str:
    return _id("LAJ", name)


def job_event_id(job, to, seq) -> str:
    return _id("LAE", job, to, seq)


def schedule_id(job) -> str:
    return _id("LAS", job)


def run_id(job, seq) -> str:
    return _id("LAR", job, seq)


def log_id(seq) -> str:
    return _id("LAL", seq)


def report_id(scope, created_at) -> str:
    return _id("LAP", scope, created_at)


def is_forbidden_verb(word) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def is_forbidden_job_kind(kind) -> bool:
    return (kind or "").strip().upper() in FORBIDDEN_JOB_KINDS


def validate_job_kind(kind) -> str:
    """잡 종류 검증. 금지(거래·배포·배분)면 ForbiddenJobKindError, 미허용이면 ValueError."""
    k = (kind or "").strip().upper()
    if is_forbidden_job_kind(k):
        raise ForbiddenJobKindError(f"금지된 잡 종류 {k} — 자동화는 거래/배포/배분을 하지 않는다")
    if k not in JOB_KINDS:
        raise ValueError(f"미지원 잡 종류 {k}")
    return k


def can_job_transition(frm, to) -> bool:
    return to in JOB_TRANSITIONS.get(frm, set())


def is_due(cadence, tick) -> bool:
    """케이던스·틱(정수) 으로 실행 예정 여부(결정적, 벽시계 없음). MANUAL 은 절대 자동 예정 아님."""
    period = CADENCES.get((cadence or "").strip().upper(), 0)
    if period <= 0:
        return False
    try:
        t = int(tick)
    except (TypeError, ValueError):
        return False
    return t >= 0 and t % period == 0


@dataclass(frozen=True)
class JobEventRecord:
    job_event_id: str
    job_id: str
    name: str
    kind: str
    from_state: str
    to_state: str
    note: str
    occurred_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ScheduleRecord:
    schedule_id: str
    job_id: str
    cadence: str
    enabled: bool
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class JobRunRecord:
    run_id: str
    job_id: str
    kind: str
    status: str
    summary: str
    result_digest: str
    is_binding: bool
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LogRecord:
    log_id: str
    job_id: str
    level: str
    message: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AutomationReportRecord:
    report_id: str
    scope: str
    job_count: int
    enabled_job_count: int
    run_count: int
    success_count: int
    failed_count: int
    schedule_count: int
    kind_distribution: dict
    status_distribution: dict
    is_binding: bool
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AutomationSummary:
    timestamp: str
    job_event_count: int
    job_count: int
    schedule_count: int
    run_count: int
    log_count: int
    report_count: int

    def to_dict(self) -> dict:
        return asdict(self)
