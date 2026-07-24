"""jarvis.research_dashboard_backend — Research Dashboard Backend Layer (P34). **백엔드 집계, UI 없음.**

백엔드 집계 계층: 통계·타임라인·헬스·지식 요약·연구 진행·모니터링. Panels·Snapshots·Widgets·Reports·Lineage 를 소유한다.

**UI 없음. 백엔드 전용. 결정 권한 없음.** execution/broker/live_trading/portfolio_execution import·호출 없음.
BACKEND ONLY · AGGREGATION ≠ DECISION · DASHBOARD ≠ AUTHORITY. 불변·append-only·해시체인·결정적·재현. 상위 계층
(P10~P33)은 READ ONLY. 원장 rdb_ 접두사.
"""
from jarvis.research_dashboard_backend.engine import ResearchDashboardBackendEngine  # noqa: F401
from jarvis.research_dashboard_backend.models import (  # noqa: F401
    PANEL_TYPES,
    ArtifactRecord,
    DashboardReportRecord,
    DashboardSummary,
    PanelRecord,
    SnapshotRecord,
    UnknownEntityError,
    WidgetRecord,
    ratio,
)
