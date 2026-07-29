"""jarvis.emergency — Kill Switch & Emergency Response Layer (P9.3). **비상 결정 전용.**

P9.1 헬스·P8.5 리스크·P9.2 인시던트/에스컬레이션을 *데이터로만* 관측 → EmergencyDecision
(NORMAL/WATCH/SAFE_MODE/KILL_PENDING/KILL_ACTIVE/RECOVERY_PENDING/RECOVERED). Recovery 는
자동 금지 — Operator 승인 흐름(RecoveryRequest/Approval/Decision)만. append-only 해시체인·결정적.

**킬스위치 결정만 생성 — 실제 작동 없음: Gateway/Broker/Order Cancel/ARM/Risk/Registry/
Portfolio/Paper/Permission 무변경·무호출.** 집행/리스크/운영 계층을 import 하지 않고 원장으로만 관측.
"""
from jarvis.emergency.engine import EmergencyEngine  # noqa: F401
from jarvis.emergency.models import (  # noqa: F401
    KILL_ACTIVE,
    KILL_PENDING,
    NORMAL,
    RECOVERED,
    RECOVERY_PENDING,
    SAFE_MODE,
    WATCH,
    EmergencyDecision,
    RecoveryApproval,
    RecoveryEvent,
    RecoveryNotPermitted,
    RecoveryRequest,
)
