"""jarvis.recovery_control — Recovery Operations Control Plane (P9.4). **복구 관제 전용.**

P9.1 헬스·P9.2 인시던트/에스컬레이션·P9.3 비상/복구·집행경계를 *데이터로만* 관측 →
RecoveryEvidence → RecoveryChecklist(결정적 체크) → RecoveryReadinessReport(READY/WARNING/
FAILED) → RecoveryAttestation(Operator 인간 증언). append-only 해시체인·결정적·재현가능.

**자동 복구 아님: 서비스 재시작·킬스위치 해제·거래 재개·브로커/게이트웨이/집행/리스크/권한/
레지스트리/포트폴리오/페이퍼/라이브 변경·호출 없음.** 킬스위치 소유권은 P9.3/execution 유지.
증언은 기록만 — 권한상승 아님. 외부 정보는 전부 JSONL 데이터 리더로만 소비(계층 import 없음).
"""
from jarvis.recovery_control.engine import RecoveryControlEngine  # noqa: F401
from jarvis.recovery_control.models import (  # noqa: F401
    APPROVE_RESTART_REVIEW,
    FAILED,
    PASS,
    READY,
    REJECT,
    WARNING,
    RecoveryAttestation,
    RecoveryAttestationError,
    RecoveryCheck,
    RecoveryChecklist,
    RecoveryEvidence,
    RecoveryReadinessReport,
)
