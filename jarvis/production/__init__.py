"""jarvis.production — Production Readiness Layer (P6.1).

연구/제안 ↔ 집행 경계. **라이브 트레이딩 아님.** 제어된 프로덕션 인터페이스만.
브로커 없음·주문 없음·자율 트레이딩 없음. risk governor가 최종 권위(무수정).
제안 전용(사람 승인 전까지). 집행 게이트웨이 무수정.
"""
from jarvis.production.approval import ApprovalGate, submit  # noqa: F401
from jarvis.production.gate import ProductionGate  # noqa: F401
from jarvis.production.models import (  # noqa: F401
    GateDecision,
    ProductionProposal,
    make_proposal_id,
)
from jarvis.production.monitor import ProductionMonitor  # noqa: F401
from jarvis.production.verify import verify  # noqa: F401
