"""Local Research Runtime 자료형 (P42) — 로컬 단일 실행 환경. **클라우드 없음, 거래·집행 없음.**

로컬 워크스테이션에서 Jarvis 연구 모듈을 관리하는 단일 진입점을 위한 자료형: 환경 검증·모듈 발견·헬스 체크·런타임
이벤트·로그. **기존 boot()/status() 를 통합(재사용)하며 새 지능 계층을 만들지 않는다.** 기존 원장 READ ONLY,
추가만. execution/broker/live_trading import·호출 없음. 불변·append-only·SHA256 해시체인.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

GENESIS = "GENESIS"

# ── 런타임 상태 ──
RT_RUNNING = "RUNNING"
RT_STOPPED = "STOPPED"
RT_UNKNOWN = "UNKNOWN"
RUNTIME_STATES = (RT_RUNNING, RT_STOPPED, RT_UNKNOWN)

# ── 이벤트 종류 ──
EV_STARTUP = "STARTUP"
EV_RESTART = "RESTART"
EV_STOP = "STOP"
EV_HEALTH = "HEALTH"
EVENT_KINDS = (EV_STARTUP, EV_RESTART, EV_STOP, EV_HEALTH)

# ── 헬스/검증 상태 ──
OK = "OK"
WARN = "WARN"
FAIL = "FAIL"
CHECK_STATES = (OK, WARN, FAIL)

# ── 로그 레벨 ──
LOG_LEVELS = ("DEBUG", "INFO", "WARN", "ERROR")

# ── 절대 금지 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "ACTIVATE_LIVE",
    "BROKER_EXECUTION", "APPROVE_FOR_TRADING", "EXECUTE", "DEPLOY", "TRADE", "ALLOCATE", "APPROVE",
})


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


def _id(tag, *parts) -> str:
    return f"{tag}:" + hashlib.sha1(input_digest(*parts).encode()).hexdigest()[:12]


def event_id(kind, seq) -> str:
    return _id("LRTE", kind, seq)


def log_id(seq) -> str:
    return _id("LRTL", seq)


def is_forbidden_verb(word) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def worst_status(statuses) -> str:
    """가장 심각한 상태 반환(FAIL > WARN > OK). 빈 목록이면 OK."""
    sev = {OK: 0, WARN: 1, FAIL: 2}
    worst = OK
    for s in statuses:
        if sev.get(s, 0) > sev.get(worst, 0):
            worst = s
    return worst


@dataclass(frozen=True)
class EnvCheck:
    name: str
    status: str
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class HealthCheck:
    name: str
    status: str
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ModuleDiscovery:
    module_count: int
    category_counts: dict
    categories: dict        # {category: [module names]}

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeEventRecord:
    event_id: str
    kind: str
    status: str
    summary: str
    detail: dict
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LogRecord:
    log_id: str
    level: str
    source: str
    message: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeStatus:
    system: str
    runtime_state: str
    autonomy_level: int
    autonomy_name: str
    live_execution: str
    module_count: int
    category_counts: dict
    health_status: str
    health_summary: str
    env_status: str
    boot_ran: bool
    timestamp: str
    checks: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeSummary:
    timestamp: str
    event_count: int
    log_count: int
    last_event_kind: str
    runtime_state: str

    def to_dict(self) -> dict:
        return asdict(self)
