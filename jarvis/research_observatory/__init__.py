"""jarvis.research_observatory — Research Observatory & Control Plane Layer (P10.10). **관측 전용.**

P10.2~P10.9 연구 계층을 READ ONLY 로 소비해 스냅샷·교차계층 지표·의존 그래프·타임라인·트렌드·대시보드·
리포트를 집계하는 최상위 관측 계층이다.

**관찰·집계·시각화만 수행한다.** Strategy 선택·Model 승인·Trading 승인·Live 실행·Deployment·
permission·config·autonomy 변경 없음. execution/broker/portfolio mutation/risk mutation/capital
allocation/order/deploy/promote import·호출 없음. OBSERVED ≠ APPROVED · OBSERVED ≠ DEPLOYED ·
OBSERVED ≠ EXECUTED. append-only 해시체인·결정적·재현. 물리 원장은 ob_ 접두사.
"""
from jarvis.research_observatory.engine import ResearchObservatoryEngine  # noqa: F401
from jarvis.research_observatory.models import (  # noqa: F401
    ANALYZING,
    ARCHIVED,
    COLLECTING,
    CREATED,
    REPORTING,
    Dashboard,
    DependencyEdge,
    IllegalTransition,
    ImmutableSnapshotError,
    ObservatoryArtifact,
    ObservatoryMetric,
    ObservatoryReport,
    ObservatorySummary,
    SnapshotEvent,
    TimelineEvent,
    TrendReport,
    UnknownSnapshot,
)
