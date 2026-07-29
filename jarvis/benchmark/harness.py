"""벤치마크 하니스 (P14) — 결정적 성능 측정. **측정 전용, 부작용 없음.**

주입 가능한 시계(clock)로 결정적 타이밍을 지원한다. 각 벤치마크는 순수 작업(callable)을 iterations 회 실행하고
work_units·checksum(작업 결정성 지문)·타이밍 통계를 수집한다. 기존 모듈을 변경하지 않는다(완전 additive).
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass


class StepClock:
    """결정적 시계 — 호출마다 step 만큼 증가. 벤치마크 재현성 테스트용."""

    def __init__(self, start: float = 0.0, step: float = 1.0) -> None:
        self._t = float(start)
        self._step = float(step)

    def __call__(self) -> float:
        cur = self._t
        self._t += self._step
        return cur


def _checksum(value) -> str:
    blob = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class BenchmarkResult:
    name: str
    iterations: int
    work_units: int
    checksum: str
    elapsed: float
    per_iter: float
    min_iter: float
    max_iter: float

    def to_dict(self) -> dict:
        return asdict(self)


def run_benchmark(name: str, fn, iterations: int = 1, *, clock=None,
                  work_units: int = 0) -> BenchmarkResult:
    """fn 을 iterations 회 실행하며 타이밍 수집. fn 은 결정적 값(체크섬 대상)을 반환해야 한다.

    clock: 인자 없는 callable(단조 증가 시간 반환). 기본 time.perf_counter. StepClock 주입 시 결정적.
    """
    if iterations < 1:
        raise ValueError("iterations must be >= 1")
    clk = clock or time.perf_counter
    last = None
    per_iter: list[float] = []
    total = 0.0
    for _ in range(iterations):
        t0 = clk()
        last = fn()
        t1 = clk()
        dt = t1 - t0
        per_iter.append(dt)
        total += dt
    return BenchmarkResult(
        name=name, iterations=iterations, work_units=work_units,
        checksum=_checksum(last), elapsed=round(total, 9),
        per_iter=round(total / iterations, 9),
        min_iter=round(min(per_iter), 9), max_iter=round(max(per_iter), 9))
