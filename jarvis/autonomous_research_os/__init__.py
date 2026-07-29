"""jarvis.autonomous_research_os — Autonomous Research OS Layer (P13). **관찰·분석·기록 전용.**

최상위 연구 통합 계층 — 모든 하위 연구 계층(P10.x/P12.x)을 READ ONLY 로 연결·관찰·집계한다. Research OS Registry·
System Snapshots·Research Episodes·Knowledge Views·Operational Reports 를 소유한다(+artifacts).

**운영 체제가 아니다(실행 아님). 거래·주문·자본 배분·전략 배포·모델 승격·권한 변경을 절대 하지 않는다.** execution/broker/
portfolio/risk/permission/deployment/live import·호출 없음. Research OS = OBSERVATION + ANALYSIS + RECORDING
ONLY. OS ≠ EXECUTION · CONNECT ≠ CONTROL · SNAPSHOT ≠ DEPLOYMENT. 불변·append-only·해시체인·이벤트 소싱·결정적·
재현. 하위 계층 원장에 절대 쓰지 않는다. 물리 원장은 aros_ 접두사.
"""
from jarvis.autonomous_research_os.engine import AutonomousResearchOSEngine  # noqa: F401
from jarvis.autonomous_research_os.models import (  # noqa: F401
    OS_STATES,
    ArtifactRecord,
    EpisodeRecord,
    ForbiddenOSActionError,
    IllegalOSTransition,
    ImmutableOSError,
    OSEventRecord,
    OSReportRecord,
    OSSummary,
    SnapshotRecord,
    UnknownOSError,
    ViewRecord,
)
