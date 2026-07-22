"""jarvis.paper_execution — Paper Execution Layer (P6.2).

APPROVED+ALLOW 프로덕션 제안 → 시뮬레이션 체결(order/fill/position/PnL).
**라이브 아님·브로커 없음·실주문 없음.** 집행 게이트웨이 무호출. append-only·결정적.
Proposal → Approval → Safety Gate → Paper Execution.
"""
from jarvis.paper_execution.engine import PaperExecutionEngine, portfolio_status  # noqa: F401
from jarvis.paper_execution.market_data import (  # noqa: F401
    FlatMarkProvider,
    PriceSnapshot,
    StaticPriceProvider,
)
from jarvis.paper_execution.models import (  # noqa: F401
    PaperExecutionReport,
    PaperFill,
    PaperOrder,
    PaperPosition,
)
from jarvis.paper_execution.monitoring import PaperRiskReport, monitor  # noqa: F401
from jarvis.paper_execution.performance import attribution, attribution_current  # noqa: F401
from jarvis.paper_execution.valuation import PortfolioSnapshot, valuate, valuate_current  # noqa: F401
from jarvis.paper_execution.verify import verify  # noqa: F401
