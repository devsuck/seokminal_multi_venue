"""jarvis.research_os_core — Research Operating System Core (P10.30, Phase 10 최종). **관측 전용.**

Phase 10 을 마무리하는 상위 연구 운영 환경. 10대 아키텍처 도메인(Data·Model·Alpha·Portfolio·Simulation·
Decision·Agent·Knowledge·Audit·Control Plane)에 걸쳐 전 계층(P9.8~P10.29)을 **READ ONLY** 로 참조(파일 기반,
import 없음)해 모듈 등록·OS 스냅샷·OS 헬스·글로벌 리포트·전체 무결성 검증을 수행하고 OS 레지스트리·글로벌 연구
상태·모듈 카탈로그·시스템 스냅샷·연구 리포트를 남긴다.

**이 계층은 관측만 한다 — execute·trade·deploy·allocate·modify 없음.** execution/broker/order/portfolio
execution/capital allocation/live trading/permission/risk controller import·호출 없음. OBSERVE ≠ EXECUTE ·
SNAPSHOT ≠ DEPLOY · HEALTH ≠ ACTION · REPORT ≠ TRADE. append-only 해시체인·결정적·재현. 물리 원장은 rosc_ 접두사.

주: 상위 스펙 이름 jarvis/research_os/ 는 선행 Phase(ros_)가 이미 소유 → 충돌 회피를 위해 미사용 네임스페이스
jarvis/research_os_core/ (rosc_) 에 배치. 기존 research_os 는 READ ONLY 로만 참조한다.
"""
from jarvis.research_os_core.engine import ResearchOSCoreEngine  # noqa: F401
from jarvis.research_os_core.models import (  # noqa: F401
    DOMAIN_DEPS,
    DOMAINS,
    HEALTH_LEVELS,
    STATES,
    CatalogRecord,
    GlobalReportRecord,
    GlobalStateRecord,
    ImmutableCatalogError,
    ImmutableModuleError,
    ImmutableReportError,
    ImmutableSnapshotError,
    ImmutableStateError,
    InvalidDomain,
    ModuleRecord,
    OSSummary,
    SnapshotRecord,
    UnknownModuleError,
)
