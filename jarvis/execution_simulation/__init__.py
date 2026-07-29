"""jarvis.execution_simulation — Execution Simulation & Dry-Run Control Layer (P7.5).

READY ExecutionDecision → SimulatedOrder → SimulatedFill → ExecutionSimulationReport.
**SimulatedOrder는 주문이 아니다 — 가상(hypothetical) 체결 레코드일 뿐.**
집행 게이트웨이 import 금지·브로커 호출 없음·실주문 없음·실자본 없음.
페이퍼/포트폴리오/리스크/레지스트리 변경 없음. 소스 원장 읽기전용·append-only·재현가능.
"""
from jarvis.execution_simulation.engine import SimulationEngine  # noqa: F401
from jarvis.execution_simulation.models import (  # noqa: F401
    BLOCKED,
    REJECTED,
    SIMULATED,
    ExecutionSimulationReport,
    SimulatedFill,
    SimulatedOrder,
)
