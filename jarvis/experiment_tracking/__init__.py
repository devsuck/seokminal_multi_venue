"""jarvis.experiment_tracking — Experiment Tracking Platform (P42). **실행 없음.**

모든 연구 실험을 추적한다: 실험 레지스트리·실행(run)·파라미터·아티팩트·결과·비교. 데이터셋 버전·코드 버전·파라미터·지표·
결과를 추적한다.

**실행 없음 — 외부에서 사람이 수행한 실험의 기록만.** execution/broker/live_trading/portfolio_execution import·호출
없음. TRACK ≠ EXECUTE · RECORD ≠ RUN. 불변·append-only·해시체인·결정적·재현. 상위 계층은 READ ONLY. 원장 expt_ 접두사.
기존 P1~P41 불변.
"""
from jarvis.experiment_tracking.engine import ExperimentTrackingEngine  # noqa: F401
from jarvis.experiment_tracking.models import (  # noqa: F401
    ARTIFACT_TYPES,
    RUN_STATUSES,
    ArtifactRecord,
    ComparisonRecord,
    ExperimentRecord,
    ExperimentReportRecord,
    ParameterRecord,
    ResultRecord,
    RunRecord,
    TrackingSummary,
    UnknownEntityError,
    metric_delta,
)
