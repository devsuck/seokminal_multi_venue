"""jarvis.research_control — Autonomous Research Control Plane Layer (P12.10). **관찰·분석·기록 전용.**

연구 시스템 상태·헬스·이벤트·지표·이상(anomaly)·리포트를 관찰·분석·기록만 한다. Research State Registry·Health
Monitoring·Research Events·System Reports 를 소유한다(+metrics/alerts/artifacts).

**제어 평면이 아니다. 자동 복구·배포·결정을 하지 않는다.** execution/broker/portfolio/risk/permission/deployment/
live import·호출 없음. OBSERVE ≠ EXECUTION · MONITOR ≠ CONTROL · ANOMALY ≠ RECOVERY. 불변·append-only·해시
체인·이벤트 소싱·결정적·재현. 상위 계층(P10.x/P12.x)은 READ ONLY. 물리 원장은 rctl_ 접두사.
"""
from jarvis.research_control.engine import AutonomousResearchControlPlaneEngine  # noqa: F401
from jarvis.research_control.models import (  # noqa: F401
    CONTROL_STATES,
    HEALTH_LEVELS,
    SEVERITIES,
    AlertRecord,
    ArtifactRecord,
    ControlSummary,
    ForbiddenControlActionError,
    HealthRecord,
    IllegalControlTransition,
    ImmutableStateError,
    MetricRecord,
    ResearchEventRecord,
    SnapshotRecord,
    StateEventRecord,
    SystemReportRecord,
    UnknownStateError,
)
