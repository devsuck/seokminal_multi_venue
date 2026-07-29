"""P37 performance 테스트 — 안전 최적화(캐싱·인덱싱·지연 로딩) 동등성·스케일 회귀. **결과 불변 보장.**"""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.performance import benchmark, optimize
from jarvis.performance import models as M
from jarvis.performance.models import ALLOWED_OPTIMIZATIONS, BENCHMARK_OPERATIONS, FORBIDDEN_CHANGES
from jarvis.system_integration.models import verify_hash_records


def _content_hash(rec):
    from jarvis.system_integration.models import content_hash
    return content_hash(rec)


def _chain(cores):
    out = []
    prev = "GENESIS"
    for core in cores:
        rec = dict(core, previous_hash=prev)
        rec["record_hash"] = _content_hash(rec)
        out.append(rec)
        prev = rec["record_hash"]
    return out


def _records(n):
    return [{"id": f"r{i}", "grp": f"g{i % 5}", "v": i} for i in range(n)]


# ═══════════════ 상수 ═══════════════
def test_benchmark_operations_count():
    assert len(BENCHMARK_OPERATIONS) == 6


@pytest.mark.parametrize("op", BENCHMARK_OPERATIONS)
def test_benchmark_operations(op):
    assert op in BENCHMARK_OPERATIONS


@pytest.mark.parametrize("kind", ALLOWED_OPTIMIZATIONS)
def test_allowed_optimizations(kind):
    assert M.is_allowed_optimization(kind) is True


@pytest.mark.parametrize("kind", FORBIDDEN_CHANGES)
def test_forbidden_changes(kind):
    assert M.is_forbidden_change(kind) is True


def test_allowed_not_forbidden():
    for k in ALLOWED_OPTIMIZATIONS:
        assert not M.is_forbidden_change(k)


# ═══════════════ 인덱싱 동등성 ═══════════════
def test_build_index():
    recs = _records(10)
    idx = optimize.build_index(recs, "grp")
    assert len(idx) == 5
    assert len(idx["g0"]) == 2


@pytest.mark.parametrize("value", ["g0", "g1", "g2", "g3", "g4", "missing"])
def test_index_equiv_scan(value):
    recs = _records(20)
    assert benchmark.equiv_index_vs_scan(recs, "grp", value) is True


def test_index_lookup_missing():
    idx = optimize.build_index(_records(5), "grp")
    assert optimize.index_lookup(idx, "zzz") == []


def test_unique_index():
    recs = _records(5)
    idx = optimize.build_unique_index(recs, "id")
    assert idx["r3"]["v"] == 3


@pytest.mark.parametrize("n", [0, 1, 10, 100, 1000])
def test_index_scales(n):
    recs = _records(n)
    idx = optimize.build_index(recs, "grp")
    total = sum(len(v) for v in idx.values())
    assert total == n


# ═══════════════ 지연 로딩 동등성 ═══════════════
def test_stream_equiv_full(tmp_path):
    recs = _records(50)
    p = os.path.join(tmp_path, "d.jsonl")
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert benchmark.equiv_stream_vs_full(p, recs) is True


def test_stream_missing_file(tmp_path):
    assert list(optimize.stream_read_jsonl(os.path.join(tmp_path, "nope.jsonl"))) == []


def test_count_lines_equiv(tmp_path):
    recs = _records(37)
    p = os.path.join(tmp_path, "d.jsonl")
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert benchmark.equiv_count(p, recs) is True


def test_stream_skips_blank(tmp_path):
    p = os.path.join(tmp_path, "d.jsonl")
    with open(p, "w") as f:
        f.write(json.dumps({"id": "a"}) + "\n\n" + json.dumps({"id": "b"}) + "\n")
    assert len(list(optimize.stream_read_jsonl(p))) == 2


def test_stream_skips_malformed(tmp_path):
    p = os.path.join(tmp_path, "d.jsonl")
    with open(p, "w") as f:
        f.write('{"id": "a"}\nNOT JSON\n{"id": "b"}\n')
    assert len(list(optimize.stream_read_jsonl(p))) == 2


def test_first_n():
    assert optimize.first_n(iter(range(100)), 5) == [0, 1, 2, 3, 4]


def test_first_n_zero():
    assert optimize.first_n(iter(range(10)), 0) == []


@pytest.mark.parametrize("n", [1, 10, 500, 2000])
def test_count_scales(tmp_path, n):
    recs = _records(n)
    p = os.path.join(tmp_path, "d.jsonl")
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert optimize.count_lines(p) == n


# ═══════════════ 배치/중복제거 동등성 ═══════════════
@pytest.mark.parametrize("size", [1, 3, 10, 128])
def test_chunk_reassembles(size):
    recs = _records(100)
    assert benchmark.equiv_chunk(recs, size) is True


def test_chunk_bad_size():
    with pytest.raises(ValueError):
        list(optimize.chunk(_records(3), 0))


def test_chunk_batch_sizes():
    batches = list(optimize.chunk(_records(10), 3))
    assert [len(b) for b in batches] == [3, 3, 3, 1]


def test_dedupe_preserve_order():
    recs = [{"id": "a"}, {"id": "b"}, {"id": "a"}, {"id": "c"}]
    out = optimize.dedupe_preserve_order(recs, "id")
    assert [r["id"] for r in out] == ["a", "b", "c"]


def test_dedupe_no_dupes():
    recs = _records(10)
    assert len(optimize.dedupe_preserve_order(recs, "id")) == 10


# ═══════════════ 캐시 해시체인 검증 동등성 ═══════════════
def test_cached_verify_equiv_valid():
    chain = _chain([{"id": "a", "v": 1}, {"id": "b", "v": 2}])
    assert benchmark.equiv_hash_verify(chain) is True


def test_cached_verify_equiv_tamper():
    chain = _chain([{"id": "a", "v": 1}])
    chain[0]["v"] = 999
    assert benchmark.equiv_hash_verify(chain) is True  # 둘 다 실패 → 동일


def test_cached_verify_equiv_broken():
    chain = _chain([{"id": "a"}, {"id": "b"}])
    chain[1]["previous_hash"] = "sha256:bad"
    assert benchmark.equiv_hash_verify(chain) is True


def test_cached_verify_equiv_empty():
    assert benchmark.equiv_hash_verify([]) is True


def test_cache_result_matches_naive():
    chain = _chain([{"id": f"r{i}", "v": i} for i in range(20)])
    cache = optimize.HashVerifyCache()
    assert cache.verify_chain(chain) == verify_hash_records(chain)


def test_cache_hits_on_repeat():
    cache = optimize.HashVerifyCache()
    rec = {"a": 1, "previous_hash": "p"}
    cache.content_hash(rec)
    cache.content_hash(rec)
    assert cache.hits >= 1


def test_cache_hash_matches_content_hash():
    cache = optimize.HashVerifyCache()
    rec = {"x": 5, "y": "z"}
    assert cache.content_hash(rec) == _content_hash(rec)


@pytest.mark.parametrize("n", [1, 50, 500])
def test_cached_verify_scales(n):
    chain = _chain([{"id": f"r{i}", "v": i} for i in range(n)])
    cache = optimize.HashVerifyCache()
    assert cache.verify_chain(chain)["ok"] is True


# ═══════════════ memoize ═══════════════
def test_memoize():
    calls = []

    @optimize.memoize
    def f(x):
        calls.append(x)
        return x * 2

    assert f(3) == 6
    assert f(3) == 6
    assert calls == [3]  # 한 번만 실제 호출


def test_memoize_distinct_args():
    @optimize.memoize
    def f(x):
        return x + 1

    assert f(1) == 2
    assert f(2) == 3
    assert len(f.cache) == 2


# ═══════════════ 벤치마크(결정적) ═══════════════
def test_benchmark_hash_verification():
    chain = _chain([{"id": f"r{i}", "v": i} for i in range(30)])
    b = benchmark.benchmark_hash_verification(chain)
    assert b["records"] == 30
    assert b["ok"] is True


def test_benchmark_indexing():
    b = benchmark.benchmark_indexing(_records(50), "grp")
    assert b["records"] == 50
    assert b["distinct_keys"] == 5


def test_benchmark_deterministic():
    recs = _records(20)
    assert benchmark.benchmark_indexing(recs, "grp") == benchmark.benchmark_indexing(recs, "grp")


@pytest.mark.parametrize("n", [0, 1, 100, 1000, 5000])
def test_large_record_processing(n):
    b = benchmark.large_record_processing(n)
    assert b["records"] == n
    assert b["deduped"] == n
    if n > 0:
        assert b["distinct_groups"] == min(10, n)


def test_large_record_processing_deterministic():
    assert benchmark.large_record_processing(1000) == benchmark.large_record_processing(1000)


def test_large_scale_10k():
    b = benchmark.large_record_processing(10000)
    assert b["records"] == 10000
    assert b["batches"] == (10000 + 127) // 128


# ═══════════════ CLI ═══════════════
def test_cli_benchmark(capsys):
    from jarvis.performance.__main__ import main
    assert main(["benchmark", "--n", "500"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["records"] == 500


def test_cli_operations(capsys):
    from jarvis.performance.__main__ import main
    assert main(["operations"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["operations"]) == 6


# ═══════════════ 안전성(결과/소유권/실행 불변) ═══════════════
_PKG = os.path.dirname(os.path.dirname(__file__))
_SRC = [os.path.join(_PKG, f) for f in os.listdir(_PKG) if f.endswith(".py")]


@pytest.mark.parametrize("path", _SRC)
def test_no_forbidden_imports(path):
    forbidden = ("jarvis.execution", "jarvis.broker", "jarvis.live_trading",
                 "jarvis.portfolio_execution", "jarvis.live_portfolio")
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(f) for f in forbidden), node.module


@pytest.mark.parametrize("path", _SRC)
def test_no_forbidden_method_defs(path):
    tree = ast.parse(open(path).read())
    bad = ("execute", "deploy", "trade", "allocate", "approve", "execute_trade", "place_order")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert ("claude" + "-opus") not in open(path).read().lower()


def test_no_ledger_no_write():
    # P37 은 순수 유틸 — 원장/파일 쓰기 없음
    assert not os.path.exists(os.path.join(_PKG, "ledger.py"))
    for path in _SRC:
        src = open(path).read()
        assert 'open(' not in src or '"w"' not in src  # 쓰기 모드 open 없음


# ═══════════════ end-to-end: 성능 회귀 = 결과 불변 ═══════════════
def test_end_to_end_no_result_change(tmp_path):
    recs = _records(500)
    p = os.path.join(tmp_path, "d.jsonl")
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    # 지연 로딩 == 전체 적재
    assert list(optimize.stream_read_jsonl(p)) == recs
    # 인덱스 == 선형 스캔
    assert benchmark.equiv_index_vs_scan(recs, "grp", "g2")
    # 청크 재조립 == 원본
    assert benchmark.equiv_chunk(recs, 64)
    # 캐시 해시 검증 == 나이브
    chain = _chain([{"id": f"c{i}", "v": i} for i in range(100)])
    assert benchmark.equiv_hash_verify(chain)
    # 대량 처리 스케일 + 결정적
    b1 = benchmark.large_record_processing(5000)
    b2 = benchmark.large_record_processing(5000)
    assert b1 == b2 and b1["records"] == 5000
