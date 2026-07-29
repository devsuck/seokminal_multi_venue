"""프로파일링 헬퍼 (P14) — CPU·메모리·replay·graph·simulation. **관찰 전용, 부작용 없음.**

주입 가능한 시계(clock)와 메모리 샘플러(mem)로 결정적 프로파일링을 지원한다. 섹션별 호출 수·누적 시간·메모리
증가를 수집하고, 정렬된 결정적 리포트와 핫스팟을 생성한다. 기존 모듈을 변경하지 않는다(완전 additive).
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass


class StepClock:
    """결정적 시계 — 호출마다 step 증가."""

    def __init__(self, start: float = 0.0, step: float = 1.0) -> None:
        self._t = float(start)
        self._step = float(step)

    def __call__(self) -> float:
        cur = self._t
        self._t += self._step
        return cur


class StepMemSampler:
    """결정적 메모리 샘플러 — 호출마다 step 바이트 증가."""

    def __init__(self, start: int = 0, step: int = 1024) -> None:
        self._m = int(start)
        self._step = int(step)

    def __call__(self) -> int:
        cur = self._m
        self._m += self._step
        return cur


@dataclass(frozen=True)
class SectionStat:
    name: str
    calls: int
    total_time: float
    total_alloc: int
    per_call_time: float

    def to_dict(self) -> dict:
        return asdict(self)


class Profiler:
    """섹션 기반 프로파일러. clock/mem 주입 시 결정적. 순수 관찰 — 대상 동작을 바꾸지 않는다."""

    def __init__(self, *, clock=None, mem=None) -> None:
        self._clock = clock or time.perf_counter
        self._mem = mem
        self._sections: dict = {}   # name -> [calls, total_time, total_alloc]

    def _acc(self, name: str, dt: float, dalloc: int) -> None:
        s = self._sections.setdefault(name, [0, 0.0, 0])
        s[0] += 1
        s[1] += dt
        s[2] += dalloc

    def record(self, name: str, elapsed: float, alloc: int = 0) -> None:
        """수동 기록(외부 측정값 주입)."""
        self._acc(name, float(elapsed), int(alloc))

    class _Section:
        def __init__(self, prof, name):
            self._p = prof
            self._name = name

        def __enter__(self):
            self._t0 = self._p._clock()
            self._m0 = self._p._mem() if self._p._mem else 0
            return self

        def __exit__(self, *a):
            t1 = self._p._clock()
            m1 = self._p._mem() if self._p._mem else 0
            self._p._acc(self._name, t1 - self._t0, max(0, m1 - self._m0))

    def section(self, name: str) -> "Profiler._Section":
        return Profiler._Section(self, name)

    def profile(self, name: str, fn):
        """콜러블을 프로파일 섹션으로 실행하고 반환값 전달."""
        with self.section(name):
            return fn()

    def stat(self, name: str) -> SectionStat:
        c, t, a = self._sections[name]
        return SectionStat(name=name, calls=c, total_time=round(t, 9), total_alloc=a,
                           per_call_time=round(t / c, 9) if c else 0.0)

    def sections(self) -> list:
        return sorted(self._sections)

    def report(self, *, top: int = 5) -> dict:
        """결정적 프로파일 리포트(섹션 정렬 + 핫스팟)."""
        stats = [self.stat(n).to_dict() for n in sorted(self._sections)]
        total_time = round(sum(s["total_time"] for s in stats), 9)
        total_alloc = sum(s["total_alloc"] for s in stats)
        hotspots = sorted(stats, key=lambda s: (-s["total_time"], s["name"]))[:top]
        return {"sections": stats, "total_time": total_time, "total_alloc": total_alloc,
                "hotspots": [h["name"] for h in hotspots], "section_count": len(stats)}


# ── 특화 프로파일 헬퍼(주입 clock/mem 로 결정적) ──
def profile_callable(fn, *, name: str = "callable", clock=None, mem=None) -> dict:
    p = Profiler(clock=clock, mem=mem)
    result = p.profile(name, fn)
    return {"result": result, "report": p.report()}


def profile_cpu(fn, *, iterations: int = 1, clock=None) -> dict:
    p = Profiler(clock=clock)
    last = None
    for _ in range(iterations):
        last = p.profile("cpu", fn)
    return {"result": last, "report": p.report()}


def profile_memory(fn, *, mem=None, clock=None) -> dict:
    p = Profiler(clock=clock, mem=mem)
    result = p.profile("memory", fn)
    return {"result": result, "report": p.report()}


def profile_replay(fn, *, clock=None) -> dict:
    return profile_callable(fn, name="replay", clock=clock)


def profile_graph(fn, *, clock=None) -> dict:
    return profile_callable(fn, name="graph", clock=clock)


def profile_simulation(fn, *, clock=None) -> dict:
    return profile_callable(fn, name="simulation", clock=clock)
