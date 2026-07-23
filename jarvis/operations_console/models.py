"""Operations Console 자료형 (P9.5) — 읽기전용 시각화·집계만. **명령/제어/상태변경 없음.**

P9.1 헬스·P9.2 알림/인시던트/에스컬레이션·P9.3 비상·P9.4 복구 준비도/증언을 *JSONL 데이터로만*
읽어 OperationsSnapshot·TimelineEvent·DashboardView 로 집계·표시한다. **집행/주문/브로커/킬스위치/
복구 실행 없음.** 순수 집계 자료형(원장 쓰기 없음·해시 생성 없음·결정적 표시).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

# 소스 라벨
S_HEALTH = "health"
S_ALERT = "alert"
S_INCIDENT = "incident"
S_ESCALATION = "escalation"
S_EMERGENCY = "emergency"
S_RECOVERY = "recovery"

NO_DATA = "NO_DATA"

# 표시용 심각도 순위(정렬 보조 — 높을수록 심각)
_SEVERITY_RANK = {
    "INFO": 1, "DEGRADED": 1, "UNKNOWN": 1, "WATCH": 2, "WARNING": 3, "SAFE_MODE": 3,
    "ERROR": 4, "OFFLINE": 4, "KILL_PENDING": 4, "RECOVERY_PENDING": 4,
    "CRITICAL": 5, "KILL_ACTIVE": 5, "FAILED": 5,
    "HEALTHY": 0, "NORMAL": 0, "READY": 0, "RECOVERED": 0, "PASS": 0,
}


def severity_rank(sev: str) -> int:
    return _SEVERITY_RANK.get(str(sev).upper(), 1)


@dataclass(frozen=True)
class TimelineEvent:
    event_id: str
    source: str                     # health | alert | incident | escalation | emergency | recovery
    severity: str
    timestamp: str
    description: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def sort_key(self) -> tuple:
        # 시간 → 소스 → id 로 결정적 정렬(동일 시각도 안정 순서)
        return (self.timestamp or "", self.source, self.event_id)


@dataclass(frozen=True)
class OperationsSnapshot:
    timestamp: str
    health_summary: dict = field(default_factory=dict)
    alert_summary: dict = field(default_factory=dict)
    incident_summary: dict = field(default_factory=dict)
    emergency_state: str = NO_DATA
    recovery_status: dict = field(default_factory=dict)
    audit_status: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DashboardView:
    timestamp: str
    snapshot: dict = field(default_factory=dict)
    system_overview: dict = field(default_factory=dict)
    emergency_panel: dict = field(default_factory=dict)
    recovery_panel: dict = field(default_factory=dict)
    audit_panel: dict = field(default_factory=dict)
    timeline: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
