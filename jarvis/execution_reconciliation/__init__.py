"""jarvis.execution_reconciliation — Execution Reconciliation & Fill Validation Layer (P7.6).

ExecutionExpectation + ExecutionSimulationReport →
  [수량·가격·수수료·슬리피지·타이밍] → ExecutionValidationReport(PASS/WARNING/FAILED).
**집행 결과 검증만 — 주문 생성/거래 집행/포지션 변경 없음.**
집행 게이트웨이 import 금지·브로커 호출 없음·실체결 없음·자본 배치 없음.
시뮬 원장 읽기전용·append-only 감사·결정적·재현가능. 신규 권한 없음.
"""
from jarvis.execution_reconciliation.engine import (  # noqa: F401
    ExecutionReconciliationEngine,
    perfect_expectation,
)
from jarvis.execution_reconciliation.models import (  # noqa: F401
    FAILED,
    PASS,
    WARNING,
    ExecutionExpectation,
    ExecutionValidationReport,
    ValidationThresholds,
)
