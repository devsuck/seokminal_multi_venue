"""jarvis.execution_control — Execution Control Plane Layer (P7.4).

ProductionProposal → ExecutionIntent → [6 checks] → ExecutionDecision(BLOCKED/READY).
**ExecutionDecision은 주문이 아니다 — 감사가능한 지시 후보일 뿐.**
집행 게이트웨이 import 금지·브로커 호출 없음·주문 없음·포지션/리스크/레지스트리 변경 없음.
소스 원장 읽기전용·append-only 감사·결정적. 신규 권한 없음.
"""
from jarvis.execution_control.engine import ExecutionControlPlane  # noqa: F401
from jarvis.execution_control.models import (  # noqa: F401
    BLOCKED,
    READY,
    ControlCheck,
    ExecutionDecision,
    ExecutionIntent,
)
