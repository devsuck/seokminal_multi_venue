"""P14 profiling 테스트 — 섹션·결정성·핫스팟·메모리·특화 헬퍼·보안."""
from __future__ import annotations

import ast
import os

import pytest

from jarvis.profiling.profiler import (
    Profiler,
    SectionStat,
    StepClock,
    StepMemSampler,
    profile_callable,
    profile_cpu,
    profile_graph,
    profile_memory,
    profile_replay,
    profile_simulation,
)


# ═══════════════ StepClock / StepMemSampler ═══════════════
def test_stepclock():
    c = StepClock(0, 1)
    assert (c(), c()) == (0.0, 1.0)


def test_stepmem():
    m = StepMemSampler(0, 100)
    assert (m(), m()) == (0, 100)


# ═══════════════ Profiler.section ═══════════════
def test_section_records_time():
    p = Profiler(clock=StepClock(0, 1))
    with p.section("a"):
        pass
    assert p.stat("a").total_time == 1.0


def test_section_multiple_calls():
    p = Profiler(clock=StepClock(0, 1))
    for _ in range(3):
        with p.section("a"):
            pass
    assert p.stat("a").calls == 3
    assert p.stat("a").total_time == 3.0


def test_section_per_call():
    p = Profiler(clock=StepClock(0, 2))
    for _ in range(2):
        with p.section("a"):
            pass
    assert p.stat("a").per_call_time == 2.0


def test_section_memory():
    p = Profiler(clock=StepClock(0, 1), mem=StepMemSampler(0, 500))
    with p.section("a"):
        pass
    assert p.stat("a").total_alloc == 500


def test_section_no_mem_sampler():
    p = Profiler(clock=StepClock(0, 1))
    with p.section("a"):
        pass
    assert p.stat("a").total_alloc == 0


def test_profile_returns_value():
    p = Profiler(clock=StepClock(0, 1))
    assert p.profile("a", lambda: 42) == 42


def test_record_manual():
    p = Profiler()
    p.record("x", 1.5, 200)
    assert p.stat("x").total_time == 1.5
    assert p.stat("x").total_alloc == 200


# ═══════════════ report ═══════════════
def test_report_deterministic():
    p = Profiler(clock=StepClock(0, 1))
    p.profile("a", lambda: 1)
    p.profile("b", lambda: 1)
    assert p.report() == p.report()


def test_report_sections_sorted():
    p = Profiler(clock=StepClock(0, 1))
    p.profile("zeta", lambda: 1)
    p.profile("alpha", lambda: 1)
    names = [s["name"] for s in p.report()["sections"]]
    assert names == ["alpha", "zeta"]


def test_report_hotspots():
    p = Profiler()
    p.record("slow", 10.0)
    p.record("fast", 1.0)
    rep = p.report()
    assert rep["hotspots"][0] == "slow"


def test_report_total_time():
    p = Profiler()
    p.record("a", 2.0)
    p.record("b", 3.0)
    assert p.report()["total_time"] == 5.0


def test_report_total_alloc():
    p = Profiler()
    p.record("a", 1.0, 100)
    p.record("b", 1.0, 200)
    assert p.report()["total_alloc"] == 300


def test_report_section_count():
    p = Profiler()
    p.record("a", 1.0)
    p.record("b", 1.0)
    assert p.report()["section_count"] == 2


def test_report_top_limit():
    p = Profiler()
    for i in range(10):
        p.record(f"s{i}", float(i))
    assert len(p.report(top=3)["hotspots"]) == 3


def test_stat_type():
    p = Profiler()
    p.record("a", 1.0)
    assert isinstance(p.stat("a"), SectionStat)


def test_stat_frozen():
    p = Profiler()
    p.record("a", 1.0)
    s = p.stat("a")
    with pytest.raises(Exception):
        s.calls = 9


def test_sections_list():
    p = Profiler()
    p.record("b", 1.0)
    p.record("a", 1.0)
    assert p.sections() == ["a", "b"]


# ═══════════════ 특화 헬퍼 ═══════════════
def test_profile_callable():
    out = profile_callable(lambda: 7, clock=StepClock(0, 1))
    assert out["result"] == 7
    assert out["report"]["section_count"] == 1


def test_profile_cpu_iterations():
    out = profile_cpu(lambda: 1, iterations=4, clock=StepClock(0, 1))
    assert out["report"]["sections"][0]["calls"] == 4


def test_profile_memory():
    out = profile_memory(lambda: 1, mem=StepMemSampler(0, 256), clock=StepClock(0, 1))
    assert out["report"]["total_alloc"] == 256


def test_profile_replay_name():
    out = profile_replay(lambda: 1, clock=StepClock(0, 1))
    assert out["report"]["sections"][0]["name"] == "replay"


def test_profile_graph_name():
    out = profile_graph(lambda: 1, clock=StepClock(0, 1))
    assert out["report"]["sections"][0]["name"] == "graph"


def test_profile_simulation_name():
    out = profile_simulation(lambda: 1, clock=StepClock(0, 1))
    assert out["report"]["sections"][0]["name"] == "simulation"


def test_profile_replay_deterministic():
    a = profile_replay(lambda: [1, 2, 3], clock=StepClock(0, 1))
    b = profile_replay(lambda: [1, 2, 3], clock=StepClock(0, 1))
    assert a["report"] == b["report"]


# ═══════════════ 파라미터화 ═══════════════
@pytest.mark.parametrize("step", [1, 2, 5, 10])
def test_section_time_scales(step):
    p = Profiler(clock=StepClock(0, step))
    with p.section("a"):
        pass
    assert p.stat("a").total_time == float(step)


@pytest.mark.parametrize("n", [1, 3, 5, 20])
def test_calls_counted(n):
    p = Profiler(clock=StepClock(0, 1))
    for _ in range(n):
        p.profile("a", lambda: 1)
    assert p.stat("a").calls == n


@pytest.mark.parametrize("helper,name", [
    (profile_replay, "replay"), (profile_graph, "graph"), (profile_simulation, "simulation"),
])
def test_helper_section_names(helper, name):
    out = helper(lambda: 1, clock=StepClock(0, 1))
    assert name in out["report"]["sections"][0]["name"]


# ═══════════════ 보안 ═══════════════
_PKG = os.path.dirname(os.path.dirname(__file__))
_SRC = [os.path.join(_PKG, f) for f in os.listdir(_PKG) if f.endswith(".py")]

_FORBIDDEN_IMPORTS = ("jarvis.execution", "jarvis.broker", "jarvis.portfolio", "jarvis.risk",
                      "jarvis.permission", "jarvis.deployment", "jarvis.live", "jarvis.order")


@pytest.mark.parametrize("path", _SRC)
def test_no_forbidden_imports(path):
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(f) for f in _FORBIDDEN_IMPORTS), node.module


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert "claude-opus" not in open(path).read().lower()


@pytest.mark.parametrize("path", _SRC)
def test_no_execution_defs(path):
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in ("execute_trade", "place_order", "deploy_model")
