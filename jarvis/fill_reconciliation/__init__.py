"""jarvis.fill_reconciliation — Broker Fill Reconciliation Layer (P8.3).

브로커가 보고한 체결(BrokerFill)과 내부 주문 생애주기 기대(InternalExecutionRecord)를 대조 →
FillReconciliationReport(MATCHED/WARNING/FAILED) → append-only 해시체인 원장.
**집행 아님·주문 없음·브로커 write 없음·포지션 변경 없음.**
매칭(broker_order_id→request_id fallback)·부분체결 집계·누락/예상밖 체결 탐지.
결정적·재현가능. 집행 게이트웨이/리스크/레지스트리 미import. 신규 권한 없음.
"""
from jarvis.fill_reconciliation.engine import FillReconciliationEngine  # noqa: F401
from jarvis.fill_reconciliation.matcher import aggregate, match  # noqa: F401
from jarvis.fill_reconciliation.models import (  # noqa: F401
    FAILED,
    MATCHED,
    WARNING,
    BrokerFill,
    FillReconciliationReport,
    FillThresholds,
    InternalExecutionRecord,
)
