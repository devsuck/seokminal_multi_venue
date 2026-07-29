"""jarvis.diagnostics — 진단 (P14 Production Hardening). **관찰·경고 전용, 완전 additive.**

죽은/대형 원장·느린 replay·깨진 계보·스냅샷 드리프트·성능 회귀를 결정적으로 탐지해 심각도별로 보고한다. 자동 조치·
복구·실행을 하지 않으며(is_actionable=False), 기존 P9~P13 원장/모듈을 변경하지 않는다. 실행 능력 없음.
"""
from jarvis.diagnostics.checks import (  # noqa: F401
    CRITICAL,
    INFO,
    SEVERITIES,
    WARNING,
    Diagnostic,
    broken_lineage,
    dead_ledger,
    large_ledger,
    performance_regression,
    run_diagnostics,
    slow_replay,
    snapshot_drift,
)
