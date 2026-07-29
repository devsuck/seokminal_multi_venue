"""jarvis.order_lifecycle — Live Order Lifecycle Control Layer (P8.2).

P8.1 라이브 집행 요청/응답을 관측하여 상태전이를 해시체인 append-only 이벤트로 기록.
OrderLifecycleManager · OrderStateMachine · LifecycleEvent Ledger.
**주문 생성/집행 아님 — 오직 관측·기록.** 브로커 호출 없음·게이트웨이 없음·
포지션/포트폴리오/리스크/ARM 변경 없음. 결정적·재현가능. 신규 권한 없음.
"""
from jarvis.order_lifecycle.manager import OrderLifecycleManager  # noqa: F401
from jarvis.order_lifecycle.models import (  # noqa: F401
    OrderLifecycleEvent,
    OrderLifecycleState,
)
from jarvis.order_lifecycle.state_machine import (  # noqa: F401
    InvalidTransition,
    is_valid_transition,
)
