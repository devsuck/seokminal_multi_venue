"""jarvis.operations_console — Operations Control Center (P9.5). **읽기전용 시각화·관제 뷰.**

P9.1 헬스·P9.2 알림/인시던트/에스컬레이션·P9.3 비상·P9.4 복구 준비도/증언을 *JSONL 데이터로만*
읽어 System Overview·Incident Timeline·Emergency Panel·Recovery Panel·Audit Panel 로 표시한다.

**시각화·운영자 인터페이스 전용: 명령 실행·서비스 재시작·상태변경·킬스위치·자동 복구승인·주문·
브로커·리스크/권한 변경 없음.** 소유 원장 없음(원장 쓰기 없음). 결정적·재현가능. 컨트롤 없음.
집행/게이트웨이/arm/리스크거버너/페이퍼/브로커/포트폴리오 import 없음 — 전부 데이터로만 소비.
"""
from jarvis.operations_console.engine import OperationsConsole, render_dashboard  # noqa: F401
from jarvis.operations_console.models import (  # noqa: F401
    DashboardView,
    OperationsSnapshot,
    TimelineEvent,
)
