"""jarvis.system_health — System Health Monitoring & Operations Layer (P9.1). **OPERATIONS-ONLY.**

전 서브시스템(페이퍼·집행 파이프라인 P7/P8·시장데이터·레지스트리·권한·설정)을 관측 →
SubsystemProbe → SystemHealthReport(HEALTHY..CRITICAL/OFFLINE/UNKNOWN). append-only 해시체인·
결정적·재현가능. **거래를 승인하지 않는다.**

집행 소유 서브시스템은 원장(JSONL)을 *데이터 파일*로만 읽는다 — 집행 게이트웨이/arm/live/paper/
risk거버너를 import 하지 않는다. 상태 변경·주문·브로커 호출 없음. 읽기전용.
"""
from jarvis.system_health.collectors import collect_all, subsystem_names  # noqa: F401
from jarvis.system_health.engine import SystemHealthEngine  # noqa: F401
from jarvis.system_health.models import (  # noqa: F401
    CRITICAL,
    DEGRADED,
    HEALTHY,
    OFFLINE,
    UNKNOWN,
    WARNING,
    SubsystemProbe,
    SystemHealthReport,
)
