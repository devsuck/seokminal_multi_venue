"""P15 license 테스트 — 분류·인벤토리·호환성·고지문·결정성·보안."""
from __future__ import annotations

import ast
import os

import pytest

from jarvis.license import audit as L
from jarvis.license.audit import (
    PERMISSIVE,
    PROPRIETARY,
    STRONG_COPYLEFT,
    UNKNOWN,
    WEAK_COPYLEFT,
    build_inventory,
    categorize,
    compatibility_report,
    normalize_license,
    third_party_notice,
)

PKGS = [
    {"name": "requests", "version": "2.31", "license": "Apache-2.0"},
    {"name": "numpy", "version": "1.26", "license": "BSD-3-Clause"},
    {"name": "clicky", "version": "1.0", "license": "MIT"},
    {"name": "mystery", "version": "0.1", "license": "Weird-1.0"},
]


# ═══════════════ categorize ═══════════════
@pytest.mark.parametrize("lic,cat", [
    ("MIT", PERMISSIVE), ("Apache-2.0", PERMISSIVE), ("BSD-3-Clause", PERMISSIVE),
    ("LGPL-3.0", WEAK_COPYLEFT), ("MPL-2.0", WEAK_COPYLEFT),
    ("GPL-3.0", STRONG_COPYLEFT), ("AGPL-3.0", STRONG_COPYLEFT),
    ("Proprietary", PROPRIETARY), ("Weird-9.9", UNKNOWN),
])
def test_categorize(lic, cat):
    assert categorize(lic) == cat


def test_categorize_case_insensitive():
    assert categorize("mit") == PERMISSIVE


def test_normalize():
    assert normalize_license("Apache 2.0") == "APACHE-2.0"


def test_categorize_empty():
    assert categorize("") == UNKNOWN


# ═══════════════ build_inventory ═══════════════
def test_inventory_count():
    inv = build_inventory(PKGS)
    assert inv["count"] == 4


def test_inventory_sorted():
    inv = build_inventory(PKGS)
    names = [e["package"] for e in inv["entries"]]
    assert names == sorted(names)


def test_inventory_by_category():
    inv = build_inventory(PKGS)
    assert inv["by_category"][PERMISSIVE] == 3


def test_inventory_unknown():
    inv = build_inventory(PKGS)
    assert inv["unknown"] == ["mystery"]


def test_inventory_deterministic():
    assert build_inventory(PKGS) == build_inventory(PKGS)


def test_inventory_empty():
    inv = build_inventory([])
    assert inv["count"] == 0


def test_inventory_entry_fields():
    inv = build_inventory([{"name": "x", "version": "1", "license": "MIT"}])
    e = inv["entries"][0]
    assert e["category"] == PERMISSIVE
    assert e["version"] == "1"


# ═══════════════ compatibility ═══════════════
def test_compat_permissive_project_ok():
    rep = compatibility_report("MIT", PKGS)
    assert rep["ok"] is True


def test_compat_strong_copyleft_conflict():
    pkgs = [{"name": "gpl-lib", "license": "GPL-3.0"}]
    rep = compatibility_report("MIT", pkgs)
    assert rep["conflicts"] == ["gpl-lib"]
    assert rep["ok"] is False


def test_compat_strong_copyleft_ok_when_project_gpl():
    pkgs = [{"name": "gpl-lib", "license": "GPL-3.0"}]
    rep = compatibility_report("GPL-3.0", pkgs)
    assert rep["ok"] is True


def test_compat_unknown_review():
    pkgs = [{"name": "x", "license": "Weird"}]
    rep = compatibility_report("MIT", pkgs)
    assert rep["reviews"] == ["x"]


def test_compat_weak_copyleft_ok_permissive_project():
    pkgs = [{"name": "lgpl", "license": "LGPL-3.0"}]
    rep = compatibility_report("MIT", pkgs)
    assert rep["ok"] is True


def test_compat_weak_copyleft_review_proprietary_project():
    pkgs = [{"name": "lgpl", "license": "LGPL-3.0"}]
    rep = compatibility_report("Proprietary", pkgs)
    assert "lgpl" in rep["reviews"]


def test_compat_proprietary_dep_review():
    pkgs = [{"name": "prop", "license": "Commercial"}]
    rep = compatibility_report("MIT", pkgs)
    assert "prop" in rep["reviews"]


def test_compat_deterministic():
    assert compatibility_report("MIT", PKGS) == compatibility_report("MIT", PKGS)


def test_compat_rows_verdicts():
    rep = compatibility_report("MIT", PKGS)
    verdicts = {r["package"]: r["verdict"] for r in rep["rows"]}
    assert verdicts["requests"] == "COMPATIBLE"
    assert verdicts["mystery"] == "REVIEW"


@pytest.mark.parametrize("proj,dep,verdict", [
    ("MIT", "MIT", "COMPATIBLE"),
    ("MIT", "GPL-3.0", "CONFLICT"),
    ("GPL-3.0", "GPL-3.0", "COMPATIBLE"),
    ("MIT", "LGPL-3.0", "COMPATIBLE"),
    ("MIT", "Weird", "REVIEW"),
    ("Proprietary", "GPL-3.0", "CONFLICT"),
])
def test_verdict_matrix(proj, dep, verdict):
    rep = compatibility_report(proj, [{"name": "p", "license": dep}])
    assert rep["rows"][0]["verdict"] == verdict


# ═══════════════ third_party_notice ═══════════════
def test_notice_contains_all():
    notice = third_party_notice(PKGS)
    for p in PKGS:
        assert p["name"] in notice


def test_notice_sorted():
    notice = third_party_notice(PKGS)
    idx = [notice.index(p) for p in ["clicky", "mystery", "numpy", "requests"]]
    assert idx == sorted(idx)


def test_notice_total():
    assert "Total: 4 components" in third_party_notice(PKGS)


def test_notice_deterministic():
    assert third_party_notice(PKGS) == third_party_notice(PKGS)


def test_notice_empty():
    notice = third_party_notice([])
    assert "Total: 0 components" in notice


# ═══════════════ 보안 ═══════════════
_PKG = os.path.dirname(os.path.dirname(__file__))
_SRC = [os.path.join(_PKG, f) for f in os.listdir(_PKG) if f.endswith(".py")]

_FORBIDDEN = ("jarvis.execution", "jarvis.broker", "jarvis.portfolio", "jarvis.risk",
              "jarvis.permission", "jarvis.deployment", "jarvis.live", "jarvis.order")


@pytest.mark.parametrize("path", _SRC)
def test_no_forbidden_imports(path):
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(f) for f in _FORBIDDEN), node.module


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert "claude-opus" not in open(path).read().lower()
