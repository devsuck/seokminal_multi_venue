"""jarvis.local_runtime — Local Research Runtime (P42). **클라우드 없음, 거래·집행 없음.**

로컬 워크스테이션에서 Jarvis 연구 환경을 관리하는 단일 진입점. 기존 boot()/status() 를 통합(재사용)하고, P41
integration_audit 스캐너로 모듈을 발견하며, 환경 검증·헬스 체크·start/restart/stop·상태·로그를 제공한다.

**새 지능 계층 없음. 기존 원장 READ ONLY(자체 lrt_ 원장만 append). 기본 start 는 boot() 를 실행하지 않음.**
클라우드·외부 서비스 의존 없음. execution/broker/live_trading import·호출 없음. 엔진은 execute()/trade()/deploy()/
allocate()/approve() 를 노출하지 않는다. 기존 P1~P41 불변.

  python -m jarvis.local_runtime start      # 로컬 연구 런타임 시작(read-only)
  python -m jarvis.local_runtime status      # 통합 상태
  python -m jarvis.local_runtime health       # 헬스 체크
"""
from jarvis.local_runtime.engine import LocalRuntimeEngine  # noqa: F401
from jarvis.local_runtime.models import (  # noqa: F401
    CHECK_STATES,
    EVENT_KINDS,
    RUNTIME_STATES,
    EnvCheck,
    HealthCheck,
    LogRecord,
    ModuleDiscovery,
    RuntimeEventRecord,
    RuntimeStatus,
    RuntimeSummary,
    worst_status,
)
