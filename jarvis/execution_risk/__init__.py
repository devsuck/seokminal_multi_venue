"""jarvis.execution_risk — Execution Risk Enforcement Layer (P8.5).

브로커 제출 직전 '최종' 보호 레이어. 이미 승인된 집행요청이 여전히 안전한지 평가만 →
ALLOW/BLOCK. **주문 생성 없음·주문 제출 없음·집행 게이트웨이 import 없음.**
13개 결정론적 검사(포지션·노셔널·집중도·손실·드로다운·레버리지·회전율·연속실패·브로커·
시장데이터·거래정지·kill switch·긴급정지). 하나라도 FAILED → BLOCK.
읽기전용·append-only 해시체인·재현가능. 신규 권한 없음. 하위 상태 무변경.
"""
from jarvis.execution_risk.engine import ExecutionRiskEngine  # noqa: F401
from jarvis.execution_risk.models import (  # noqa: F401
    ALLOW,
    BLOCK,
    FAILED,
    PASS,
    WARNING,
    ExecutionRiskReport,
    RiskCheck,
)
from jarvis.execution_risk.policy import ExecutionRiskPolicy, RiskContext  # noqa: F401
