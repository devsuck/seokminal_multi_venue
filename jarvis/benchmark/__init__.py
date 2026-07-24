"""jarvis.benchmark — 결정적 벤치마킹 유틸리티 (P14 Production Hardening). **측정 전용, 완전 additive.**

기존 P9~P13 모듈을 변경하지 않고, 대표 연산(원장 append·replay·해시 검증·계보/그래프 순회·시뮬레이션 replay·의사결정
평가·메모리 검색·에이전트 워크플로·OS 스냅샷)을 결정적 합성 데이터로 측정한다. 리포트/이력/비교 제공. 실행·배포·거래
능력 없음. 재현성은 주입 clock(StepClock)으로 보장한다.
"""
from jarvis.benchmark.harness import BenchmarkResult, StepClock, run_benchmark  # noqa: F401
from jarvis.benchmark.report import (  # noqa: F401
    BenchmarkReport,
    append_history,
    build_report,
    compare_reports,
    read_history,
)
from jarvis.benchmark.suite import BENCHMARK_NAMES, DEFAULT_SCALE, run_suite  # noqa: F401
