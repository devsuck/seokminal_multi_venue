"""jarvis.research_control_plane — Research Control Plane Layer (P10.28). **관측 전용.**

Research OS 전체의 중앙 관측·조율 평면. 전 계층(P9.8~P10.27)을 **READ ONLY** 로 참조(파일 기반, import 없음)해
컴포넌트 등록·계층 상태 수집·시스템 맵 구성·헬스 점수 계산·의존성 이슈 탐지·컨트롤 리포트 생성·상태 검증을
수행하고 시스템 개요·계층 상태·의존성 상태·거버넌스 대시보드 데이터·연구 타임라인·헬스 지표·컨트롤 리포트를
남긴다.

**실행 컨트롤러가 아니다 — 관측·집계·시각화·리포트만.** execute/trade/order/allocation/deployment/permission·
config 변경 없음. OBSERVE ≠ EXECUTE · STATUS ≠ CONTROL · HEALTH ≠ ACTION · REPORT ≠ DEPLOYMENT. append-only
해시체인·결정적·재현. 물리 원장은 rcp_ 접두사.
"""
from jarvis.research_control_plane.engine import ResearchControlPlaneEngine  # noqa: F401
from jarvis.research_control_plane.models import (  # noqa: F401
    CATEGORIES,
    HEALTH_LEVELS,
    ISSUE_TYPES,
    STATES,
    TL_KINDS,
    ComponentRecord,
    ControlPlaneSummary,
    ControlReportRecord,
    DependencyRecord,
    GovernanceDashboardRecord,
    HealthMetricRecord,
    ImmutableComponentError,
    ImmutableDashboardError,
    ImmutableDependencyError,
    ImmutableHealthError,
    ImmutableOverviewError,
    ImmutableReportError,
    ImmutableStatusError,
    InvalidComponentCategory,
    LayerStatusRecord,
    SystemOverviewRecord,
    TimelineEventRecord,
    UnknownComponentError,
)
