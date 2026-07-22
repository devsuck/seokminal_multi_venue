"""jarvis.post_trade_analytics — Post-Trade Analytics & TCA Layer (P8.7). **ANALYTICS-ONLY.**

완료된 집행을 분석 → TransactionCostAnalysisReport·ExecutionQualityReport·
ExecutionBenchmarkReport·PortfolioExecutionSummary. **거래를 승인하지 않는다.**
벤치마크(Arrival·Decision·VWAP·TWAP·Close·IS·Spread·Market Impact·Opportunity Cost) +
메트릭(execution score·fill efficiency·participation·adverse selection 등) + 포트폴리오 집계.
append-only 해시체인·결정적·재현가능. 읽기전용.

집행 게이트웨이/live/paper/risk거버너 import 없음·주문/집행/브로커 호출 없음·상태 변경 없음.
"""
from jarvis.post_trade_analytics.engine import PostTradeAnalyticsEngine  # noqa: F401
from jarvis.post_trade_analytics.models import (  # noqa: F401
    FAILED,
    PASS,
    WARNING,
    ExecutionData,
    PortfolioExecutionSummary,
    PostTradeReport,
    TransactionCostAnalysisReport,
)
