"""P14 cache 테스트 — 불변성·버전 무효화·통계·리포트·결정성·원본 불변·보안."""
from __future__ import annotations

import ast
import os

import pytest

from jarvis.cache.store import CacheStats, ImmutableCache, ImmutableCacheError


def _c():
    return ImmutableCache()


# ═══════════════ put / get ═══════════════
def test_put_get():
    c = _c()
    c.put("ns", "k", 1, {"v": 10})
    assert c.get("ns", "k", 1) == {"v": 10}


def test_get_miss_default():
    c = _c()
    assert c.get("ns", "k", 1, default="X") == "X"


def test_contains():
    c = _c()
    c.put("ns", "k", 1, 5)
    assert c.contains("ns", "k", 1)
    assert not c.contains("ns", "k", 2)


def test_put_same_value_idempotent():
    c = _c()
    c.put("ns", "k", 1, [1, 2, 3])
    c.put("ns", "k", 1, [1, 2, 3])
    assert c.stats().puts == 1


def test_put_different_value_rejected():
    c = _c()
    c.put("ns", "k", 1, {"v": 1})
    with pytest.raises(ImmutableCacheError):
        c.put("ns", "k", 1, {"v": 2})


def test_rejected_counted():
    c = _c()
    c.put("ns", "k", 1, 1)
    try:
        c.put("ns", "k", 1, 2)
    except ImmutableCacheError:
        pass
    assert c.stats().rejected == 1


def test_different_version_allowed():
    c = _c()
    c.put("ns", "k", 1, "a")
    c.put("ns", "k", 2, "b")
    assert c.get("ns", "k", 1) == "a"
    assert c.get("ns", "k", 2) == "b"


def test_version_coerced_to_str():
    c = _c()
    c.put("ns", "k", 1, "a")
    assert c.get("ns", "k", "1") == "a"


# ═══════════════ 원본 불변 ═══════════════
def test_get_returns_copy_not_reference():
    c = _c()
    original = {"v": [1, 2]}
    c.put("ns", "k", 1, original)
    got = c.get("ns", "k", 1)
    got["v"].append(3)
    # 캐시 내부는 변형되지 않음
    assert c.get("ns", "k", 1) == {"v": [1, 2]}


def test_put_snapshot_isolates_source():
    c = _c()
    src = {"v": 1}
    c.put("ns", "k", 1, src)
    src["v"] = 999  # 이후 원본 변형이 캐시에 영향 없음
    assert c.get("ns", "k", 1) == {"v": 1}


def test_fingerprint_stable():
    c = _c()
    c.put("ns", "k", 1, {"a": 1, "b": 2})
    fp1 = c.fingerprint("ns", "k", 1)
    assert fp1 == c.fingerprint("ns", "k", 1)
    assert fp1.startswith("sha256:")


def test_fingerprint_missing():
    assert _c().fingerprint("ns", "k", 1) is None


# ═══════════════ 무효화 ═══════════════
def test_invalidate_version():
    c = _c()
    c.put("ns", "a", 1, 1)
    c.put("ns", "b", 1, 2)
    c.put("ns", "a", 2, 3)
    removed = c.invalidate_version("ns", 1)
    assert removed == 2
    assert not c.contains("ns", "a", 1)
    assert c.contains("ns", "a", 2)


def test_invalidate_version_none():
    c = _c()
    assert c.invalidate_version("ns", 9) == 0


def test_invalidate_namespace():
    c = _c()
    c.put("ns1", "a", 1, 1)
    c.put("ns2", "b", 1, 2)
    assert c.invalidate_namespace("ns1") == 1
    assert not c.contains("ns1", "a", 1)
    assert c.contains("ns2", "b", 1)


def test_invalidation_counted():
    c = _c()
    c.put("ns", "a", 1, 1)
    c.invalidate_version("ns", 1)
    assert c.stats().invalidations == 1


def test_reput_after_invalidation():
    c = _c()
    c.put("ns", "k", 1, "a")
    c.invalidate_version("ns", 1)
    c.put("ns", "k", 1, "b")  # 무효화 후 재저장 허용
    assert c.get("ns", "k", 1) == "b"


# ═══════════════ 조회/통계 ═══════════════
def test_versions():
    c = _c()
    c.put("ns", "a", 1, 1)
    c.put("ns", "b", 3, 1)
    assert c.versions("ns") == ["1", "3"]


def test_keys():
    c = _c()
    c.put("ns", "a", 1, 1)
    c.put("ns", "b", 1, 1)
    assert len(c.keys("ns")) == 2


def test_stats_hits_misses():
    c = _c()
    c.put("ns", "k", 1, 1)
    c.get("ns", "k", 1)
    c.get("ns", "k", 2)
    s = c.stats()
    assert s.hits == 1
    assert s.misses == 1


def test_stats_type():
    assert isinstance(_c().stats(), CacheStats)


def test_stats_frozen():
    s = _c().stats()
    with pytest.raises(Exception):
        s.entries = 5


def test_stats_entries():
    c = _c()
    c.put("ns", "a", 1, 1)
    c.put("ns", "b", 1, 1)
    assert c.stats().entries == 2


def test_stats_versions_count():
    c = _c()
    c.put("ns", "a", 1, 1)
    c.put("ns", "a", 2, 1)
    assert c.stats().versions == 2


# ═══════════════ 리포트 ═══════════════
def test_report_hit_rate():
    c = _c()
    c.put("ns", "k", 1, 1)
    c.get("ns", "k", 1)
    c.get("ns", "k", 1)
    c.get("ns", "x", 1)  # miss
    rep = c.report()
    assert rep["hit_rate"] == round(2 / 3, 6)


def test_report_namespaces():
    c = _c()
    c.put("ns1", "a", 1, 1)
    c.put("ns2", "b", 1, 1)
    rep = c.report()
    assert set(rep["namespaces"]) == {"ns1", "ns2"}


def test_report_deterministic():
    c = _c()
    c.put("ns", "a", 1, 1)
    assert c.report() == c.report()


def test_report_empty_hit_rate():
    assert _c().report()["hit_rate"] == 0.0


def test_report_namespace_versions_sorted():
    c = _c()
    c.put("ns", "a", 3, 1)
    c.put("ns", "b", 1, 1)
    rep = c.report()
    assert rep["namespaces"]["ns"]["versions"] == ["1", "3"]


# ═══════════════ 파라미터화 ═══════════════
@pytest.mark.parametrize("val", [1, "s", [1, 2], {"a": 1}, None, 3.14, True])
def test_roundtrip_types(val):
    c = _c()
    c.put("ns", "k", 1, val)
    assert c.get("ns", "k", 1) == val


@pytest.mark.parametrize("n", [1, 5, 20, 100])
def test_many_entries(n):
    c = _c()
    for i in range(n):
        c.put("ns", f"k{i}", 1, i)
    assert c.stats().entries == n


@pytest.mark.parametrize("v", [1, 2, 3, 10])
def test_version_isolation(v):
    c = _c()
    for i in range(1, v + 1):
        c.put("ns", "k", i, i * 10)
    assert c.get("ns", "k", v) == v * 10


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
