"""P15 sbom 테스트 — 컴포넌트·생성·검증·직렬번호·의존성그래프·결정성·보안."""
from __future__ import annotations

import ast
import os

import pytest

from jarvis.sbom.generate import (
    SBOM_FORMAT,
    Component,
    component_hash,
    generate_sbom,
    make_component,
    sbom_from_dependencies,
    verify_sbom,
)

COMPS = [
    {"name": "requests", "version": "2.31", "license": "Apache-2.0", "source": "pypi"},
    {"name": "numpy", "version": "1.26", "license": "BSD-3-Clause", "source": "pypi",
     "depends_on": ["libc"]},
    {"name": "pandas", "version": "2.0", "license": "BSD-3-Clause", "source": "pypi",
     "depends_on": ["numpy"]},
]


# ═══════════════ component ═══════════════
def test_make_component_hash():
    c = make_component("x", "1.0", "MIT", "pypi")
    assert c.hash.startswith("sha256:")


def test_component_hash_deterministic():
    assert component_hash("x", "1", "MIT", "pypi") == component_hash("x", "1", "MIT", "pypi")


def test_component_hash_changes():
    assert component_hash("x", "1", "MIT", "pypi") != component_hash("x", "2", "MIT", "pypi")


def test_component_deps_sorted():
    c = make_component("x", "1", "MIT", "pypi", depends_on=["z", "a"])
    assert c.depends_on == ("a", "z")


def test_component_to_dict():
    c = make_component("x", "1", "MIT", "pypi", depends_on=["a"])
    assert c.to_dict()["depends_on"] == ["a"]


def test_component_frozen():
    c = make_component("x", "1", "MIT", "pypi")
    with pytest.raises(Exception):
        c.name = "y"


# ═══════════════ generate_sbom ═══════════════
def test_generate_count():
    sbom = generate_sbom(COMPS)
    assert sbom["component_count"] == 3


def test_generate_format():
    sbom = generate_sbom(COMPS)
    assert sbom["format"] == SBOM_FORMAT


def test_generate_components_sorted():
    sbom = generate_sbom(COMPS)
    names = [c["name"] for c in sbom["components"]]
    assert names == sorted(names)


def test_generate_serial_number():
    sbom = generate_sbom(COMPS)
    assert sbom["serial_number"].startswith("sha256:")


def test_generate_serial_deterministic():
    a = generate_sbom(COMPS)
    b = generate_sbom(COMPS)
    assert a["serial_number"] == b["serial_number"]


def test_generate_serial_ignores_timestamp():
    a = generate_sbom(COMPS, generated_at="2026-01-01")
    b = generate_sbom(COMPS, generated_at="2026-12-31")
    assert a["serial_number"] == b["serial_number"]


def test_generate_dep_graph():
    sbom = generate_sbom(COMPS)
    assert sbom["dependency_graph"]["pandas"] == ["numpy"]


def test_generate_all_components_hashed():
    sbom = generate_sbom(COMPS)
    assert all(c["hash"].startswith("sha256:") for c in sbom["components"])


def test_generate_from_component_objects():
    comps = [make_component("a", "1", "MIT", "pypi")]
    sbom = generate_sbom(comps)
    assert sbom["component_count"] == 1


def test_generate_empty():
    sbom = generate_sbom([])
    assert sbom["component_count"] == 0


def test_generate_project_fields():
    sbom = generate_sbom(COMPS, project="myproj", project_version="0.1")
    assert sbom["project"] == "myproj"
    assert sbom["project_version"] == "0.1"


# ═══════════════ verify_sbom ═══════════════
def test_verify_ok():
    sbom = generate_sbom(COMPS)
    assert verify_sbom(sbom)["ok"] is True


def test_verify_detects_component_tamper():
    sbom = generate_sbom(COMPS)
    sbom["components"][0]["version"] = "9.9.9"
    res = verify_sbom(sbom)
    assert res["ok"] is False
    assert any(i["issue"] == "hash_mismatch" for i in res["issues"])


def test_verify_detects_serial_tamper():
    sbom = generate_sbom(COMPS)
    sbom["serial_number"] = "sha256:deadbeef"
    res = verify_sbom(sbom)
    assert res["ok"] is False
    assert any(i["issue"] == "serial_mismatch" for i in res["issues"])


def test_verify_count():
    sbom = generate_sbom(COMPS)
    assert verify_sbom(sbom)["verified"] == 3


def test_verify_empty():
    assert verify_sbom(generate_sbom([]))["ok"] is True


# ═══════════════ sbom_from_dependencies ═══════════════
def test_from_dependencies():
    scan = {"dependencies": [{"canonical": "requests", "version": "2.31"},
                             {"canonical": "numpy", "version": "1.26"}]}
    sbom = sbom_from_dependencies(scan, licenses={"requests": "Apache-2.0"},
                                  versions={"numpy": "1.26.4"})
    assert sbom["component_count"] == 2
    numpy = next(c for c in sbom["components"] if c["name"] == "numpy")
    assert numpy["version"] == "1.26.4"


def test_from_dependencies_verify():
    scan = {"dependencies": [{"canonical": "requests", "version": "2.31"}]}
    sbom = sbom_from_dependencies(scan)
    assert verify_sbom(sbom)["ok"] is True


def test_from_dependencies_deterministic():
    scan = {"dependencies": [{"canonical": "a", "version": "1"}]}
    assert (sbom_from_dependencies(scan)["serial_number"]
            == sbom_from_dependencies(scan)["serial_number"])


# ═══════════════ 파라미터화 ═══════════════
@pytest.mark.parametrize("n", [1, 3, 10, 50])
def test_generate_scales(n):
    comps = [{"name": f"pkg{i:03d}", "version": "1", "license": "MIT", "source": "pypi"}
             for i in range(n)]
    sbom = generate_sbom(comps)
    assert sbom["component_count"] == n
    assert verify_sbom(sbom)["ok"] is True


@pytest.mark.parametrize("field", ["name", "version", "license", "source"])
def test_hash_sensitive_to_field(field):
    base = {"name": "x", "version": "1", "license": "MIT", "source": "pypi"}
    h1 = component_hash(base["name"], base["version"], base["license"], base["source"])
    mod = dict(base)
    mod[field] = "CHANGED"
    h2 = component_hash(mod["name"], mod["version"], mod["license"], mod["source"])
    assert h1 != h2


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
