"""System Health 자료형 (P9.1) — 전 서브시스템 헬스 관측만. **집행 아님.**

모든 서브시스템을 관측 → SubsystemProbe → SystemHealthReport(HEALTHY..CRITICAL/OFFLINE/
UNKNOWN). **상태 변경 없음·거래 인가 없음·브로커 접촉 없음.** 결정적·읽기전용·해시체인.
지연(latency)·타임스탬프는 비결정적이라 해시에서 제외(헬스 상태만 해싱).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

# ── Health Levels ──
HEALTHY = "HEALTHY"
DEGRADED = "DEGRADED"
WARNING = "WARNING"
CRITICAL = "CRITICAL"
OFFLINE = "OFFLINE"
UNKNOWN = "UNKNOWN"

GENESIS = "GENESIS"

# 심각도(overall 집계용) — 높을수록 심각
_SEVERITY = {HEALTHY: 0, UNKNOWN: 1, DEGRADED: 2, WARNING: 3, OFFLINE: 4, CRITICAL: 5}
# 헬스 스코어(0~100)
_SCORE = {HEALTHY: 100, DEGRADED: 75, UNKNOWN: 50, WARNING: 40, OFFLINE: 15, CRITICAL: 0}
# healthy=True 로 간주하는 상태
_OK = {HEALTHY, DEGRADED}


@dataclass(frozen=True)
class SubsystemProbe:
    name: str
    status: str                     # HEALTHY | DEGRADED | WARNING | CRITICAL | OFFLINE | UNKNOWN
    last_update: str = ""           # 마지막 원장 갱신(있으면)
    latency_ms: float = 0.0         # 관측 지연(비결정적 — 해시 제외)
    healthy: bool = False
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    hash: str = ""
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SystemHealthReport:
    report_id: str
    timestamp: str
    overall_status: str
    health_score: float
    subsystems: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    input_hash: str = ""
    report_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


def is_ok(status: str) -> bool:
    return status in _OK


def severity(status: str) -> int:
    return _SEVERITY.get(status, 1)


def overall_status(statuses: list) -> str:
    """최대 심각도 상태. 비어있으면 UNKNOWN."""
    if not statuses:
        return UNKNOWN
    return max(statuses, key=severity)


def health_score(statuses: list) -> float:
    if not statuses:
        return 0.0
    return round(sum(_SCORE.get(s, 50) for s in statuses) / len(statuses), 2)


# ── 해시(헬스 상태만 — latency/timestamp 제외 → 결정적) ──
def probe_hash(name: str, status: str, warnings: list, errors: list) -> str:
    payload = {"name": name, "status": status,
               "warnings": sorted(warnings), "errors": sorted(errors)}
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def report_id(input_hash_: str) -> str:
    return "SHR:" + hashlib.sha1(input_hash_.encode()).hexdigest()[:12]


def input_hash(probes: list) -> str:
    payload = [(p["name"], p["status"]) for p in probes]
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def report_hash(report_id_: str, overall: str, score: float, probes: list,
                warnings: list, errors: list, input_hash_: str) -> str:
    payload = {"report_id": report_id_, "overall_status": overall, "health_score": score,
               "subsystems": [(p["name"], p["status"]) for p in probes],
               "warnings": sorted(warnings), "errors": sorted(errors),
               "input_hash": input_hash_}
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]
