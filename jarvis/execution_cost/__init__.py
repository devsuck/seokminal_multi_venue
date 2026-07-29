"""jarvis.execution_cost — Execution Cost & Slippage Accounting Layer (P8.4).

체결(P8.3) 후 실제 집행비용을 측정하는 **회계 전용** 레이어.
ExecutionCostInput + CostRates → CostComponents → ExecutionCostReport(EXPECTED/WARNING/FAILED) →
append-only 해시체인 원장. **집행 아님·주문 없음·브로커 write 없음·포지션 변경 없음.**
결정적·재현가능. 집행 게이트웨이/리스크/포트폴리오 미import. 신규 권한 없음.
"""
from jarvis.execution_cost.calculator import calculate, cost_bps, slippage_bps, spread_bps  # noqa: F401
from jarvis.execution_cost.engine import CostAccountingEngine, cost_input_from_fills  # noqa: F401
from jarvis.execution_cost.models import (  # noqa: F401
    EXPECTED,
    FAILED,
    WARNING,
    CostComponents,
    CostRates,
    CostThresholds,
    ExecutionCostInput,
    ExecutionCostReport,
)
