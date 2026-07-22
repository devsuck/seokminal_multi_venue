"""jarvis.live_execution — Live Execution Adapter Layer (P8.1). **첫 라이브 집행 경계.**

ExecutionIntent → Decision READY → Readiness Certificate READY → 사람 ARM →
LiveExecutionRequest → BrokerExecutionAdapter → LiveExecutionResponse.
브로커 write 능력은 오직 [READY 인증서 + 사람 ARM + 명시적 호출] 뒤에서만.

**사람 게이트 전용 — 자율 트레이딩 없음·무인 집행 없음·스케줄러 트리거 없음·
자동 자본 배치 없음.** 실브로커 어댑터(IB/KIS)는 자리표시자·기본 비활성(자격증명 없음,
자율레벨<MIN_LIVE). MockExecutionAdapter만 활성이며 시뮬 응답(실자본 없음).
결정적·append-only. 하위 레이어(리스크/레지스트리/페이퍼/시뮬) 무변경.
"""
from jarvis.live_execution.adapters import (  # noqa: F401
    BrokerExecutionAdapter,
    IBExecutionAdapter,
    KISExecutionAdapter,
    MockExecutionAdapter,
    get_adapter,
)
from jarvis.live_execution.engine import LiveExecutionEngine, build_request, human_arm  # noqa: F401
from jarvis.live_execution.models import (  # noqa: F401
    ACCEPTED,
    REJECTED,
    LiveExecutionRequest,
    LiveExecutionResponse,
)
