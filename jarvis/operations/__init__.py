"""jarvis.operations — Operations Alerting & Incident Management Layer (P9.2). **관제 전용.**

P9.1 SystemHealthReport 를 데이터로 읽어 Alert(INFO/WARNING/ERROR/CRITICAL) → 지속 시
Incident(OPEN→ACKNOWLEDGED→MITIGATING→RESOLVED→CLOSED 상태머신) → CRITICAL 지속 시
Escalation(레코드만 — 이메일/Slack/Webhook/SMS 발송 없음) → Operator Acknowledgement →
Resolution. 5개 append-only 해시체인 원장. 결정적·재현가능.

**집행 없음: 주문/브로커/게이트웨이/ARM/킬스위치/리스크/레지스트리/권한/포트폴리오/페이퍼 무변경.**
집행 소유 서브시스템(P6~P8)을 import 하지 않고 원장 파일로만 관측한다. 읽기전용.
"""
from jarvis.operations.engine import OperationsEngine  # noqa: F401
from jarvis.operations.models import (  # noqa: F401
    ACKNOWLEDGED,
    CLOSED,
    CRITICAL,
    ERROR,
    INFO,
    MITIGATING,
    OPEN,
    RESOLVED,
    WARNING,
    Acknowledgement,
    Alert,
    Escalation,
    IllegalTransition,
    IncidentEvent,
    Resolution,
)
