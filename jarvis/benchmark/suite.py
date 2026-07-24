"""벤치마크 스위트 (P14) — 10개 대표 연산 결정적 실행. **측정 전용.**

주입 clock 으로 재현 가능한 스위트를 실행한다. 각 타겟은 결정적 합성 데이터로 동작하며, 리포트의 작업 checksum 은
입력 규모(scale)에만 의존한다(타이밍 제외). tmp_dir 미지정 시 원장 append 타겟은 메모리 카운트로 대체.
"""
from __future__ import annotations

import os

from jarvis.benchmark import targets as _t
from jarvis.benchmark.harness import run_benchmark
from jarvis.benchmark.report import build_report

# (name, work_units) — 결정적 스케일
DEFAULT_SCALE = {
    "ledger_append": 200,
    "replay": 200,
    "hash_verification": 200,
    "lineage_traversal": 128,
    "knowledge_graph_traversal": 128,
    "simulation_replay": 500,
    "decision_evaluation": 200,
    "memory_retrieval": 200,
    "agent_workflow": 300,
    "os_snapshot_generation": 32,
}

BENCHMARK_NAMES = tuple(sorted(DEFAULT_SCALE))


def _target_fn(name: str, scale: dict, tmp_dir: str | None):
    n = scale[name]
    if name == "ledger_append":
        path = os.path.join(tmp_dir, "bench_append.jsonl") if tmp_dir else None
        if path is None:
            return lambda: len(_t.make_records(n))
        return lambda: _t.ledger_append(path, n)
    if name == "replay":
        recs = _t.make_records(n)
        return lambda: _t.replay(recs)
    if name == "hash_verification":
        recs = _t.make_records(n)
        return lambda: _t.hash_verification(recs)
    if name == "lineage_traversal":
        tree = _t.make_tree(n)
        return lambda: _t.lineage_traversal(tree)
    if name == "knowledge_graph_traversal":
        graph = _t.make_graph(n)
        return lambda: _t.graph_traversal(graph)
    if name == "simulation_replay":
        return lambda: _t.simulation_replay(n)
    if name == "decision_evaluation":
        return lambda: _t.decision_evaluation(n)
    if name == "memory_retrieval":
        return lambda: _t.memory_retrieval(n, n)
    if name == "agent_workflow":
        return lambda: _t.agent_workflow(n)
    if name == "os_snapshot_generation":
        return lambda: _t.os_snapshot_generation(n, 4)
    raise KeyError(name)


def run_suite(label: str = "suite", *, scale: dict | None = None, iterations: int = 1,
              clock=None, tmp_dir: str | None = None, generated_at: str = ""):
    """전체 벤치마크 스위트 실행 → BenchmarkReport(결정적)."""
    sc = dict(DEFAULT_SCALE)
    if scale:
        sc.update(scale)
    results = []
    for name in BENCHMARK_NAMES:
        fn = _target_fn(name, sc, tmp_dir)
        results.append(run_benchmark(name, fn, iterations, clock=clock, work_units=sc[name]))
    return build_report(label, results, generated_at)
