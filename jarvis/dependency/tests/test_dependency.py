"""P15 dependency 테스트 — 파싱·스캔·중복/미사용/구버전·그래프·리포트·보안."""
from __future__ import annotations

import ast
import os

import pytest

from jarvis.dependency import audit as A
from jarvis.dependency import manifest as MF
from jarvis.dependency.manifest import canonicalize, parse_pyproject, parse_requirement

PYPROJECT = '''
[project]
name = "demo"
dependencies = [
    "requests>=2.31",
    "python-dotenv>=1.0",
    "numpy>=1.26",
    "pandas>=2.0",
    "pydantic>=2.0",
]
[project.optional-dependencies]
dev = ["pytest>=8.0", "httpx>=0.27"]
'''


# ═══════════════ canonicalize ═══════════════
@pytest.mark.parametrize("raw,exp", [
    ("Requests", "requests"), ("python_dotenv", "python-dotenv"),
    ("Foo.Bar", "foo-bar"), ("a__b", "a-b"), ("PyYAML", "pyyaml"),
])
def test_canonicalize(raw, exp):
    assert canonicalize(raw) == exp


# ═══════════════ parse_requirement ═══════════════
def test_parse_simple():
    r = parse_requirement("requests>=2.31")
    assert r.name == "requests"
    assert r.operator == ">="
    assert r.version == "2.31"


def test_parse_no_version():
    r = parse_requirement("nautilus_trader")
    assert r.canonical == "nautilus-trader"
    assert r.operator == ""


def test_parse_pinned():
    r = parse_requirement("foo==1.2.3")
    assert r.operator == "=="


def test_parse_extras():
    r = parse_requirement("uvicorn[standard]>=0.29")
    assert r.extras == ("standard",)


def test_parse_comment_none():
    assert parse_requirement("# a comment") is None


def test_parse_empty_none():
    assert parse_requirement("") is None


@pytest.mark.parametrize("op", [">=", "<=", "==", "!=", "~=", ">", "<"])
def test_parse_operators(op):
    r = parse_requirement(f"pkg{op}1.0")
    assert r.operator == op


def test_requirement_to_dict():
    r = parse_requirement("uvicorn[standard]>=0.29")
    assert r.to_dict()["extras"] == ["standard"]


def test_requirement_frozen():
    r = parse_requirement("foo>=1.0")
    with pytest.raises(Exception):
        r.name = "x"


# ═══════════════ parse_pyproject ═══════════════
def test_parse_pyproject_deps():
    parsed = parse_pyproject(PYPROJECT)
    names = {r.canonical for r in parsed["dependencies"]}
    assert "requests" in names
    assert "numpy" in names


def test_parse_pyproject_optional():
    parsed = parse_pyproject(PYPROJECT)
    assert "dev" in parsed["optional"]
    assert any(r.canonical == "pytest" for r in parsed["optional"]["dev"])


def test_parse_pyproject_count():
    parsed = parse_pyproject(PYPROJECT)
    assert len(parsed["dependencies"]) == 5


def test_parse_pyproject_empty():
    assert parse_pyproject("")["dependencies"] == []


# ═══════════════ scan_dependencies ═══════════════
def test_scan_count():
    assert A.scan_dependencies(PYPROJECT)["count"] == 5


def test_scan_sorted():
    rows = A.scan_dependencies(PYPROJECT)["dependencies"]
    names = [r["canonical"] for r in rows]
    assert names == sorted(names)


def test_scan_unpinned():
    # 모두 >= 이므로 unpinned
    assert len(A.scan_dependencies(PYPROJECT)["unpinned"]) == 5


def test_scan_deterministic():
    assert A.scan_dependencies(PYPROJECT) == A.scan_dependencies(PYPROJECT)


def test_scan_optional_present():
    assert "dev" in A.scan_dependencies(PYPROJECT)["optional"]


# ═══════════════ detect_duplicates ═══════════════
def test_duplicates_none():
    assert A.detect_duplicates(PYPROJECT) == []


def test_duplicates_detected():
    txt = '''
[project]
dependencies = ["requests>=2.0"]
[project.optional-dependencies]
dev = ["requests>=2.31"]
'''
    dups = A.detect_duplicates(txt)
    assert len(dups) == 1
    assert dups[0]["package"] == "requests"


# ═══════════════ detect_unused ═══════════════
def test_unused_none_when_all_imported():
    imported = ["requests", "dotenv", "numpy", "pandas", "pydantic"]
    mapping = {"python-dotenv": "dotenv"}
    out = A.detect_unused(PYPROJECT, imported, mapping=mapping)
    assert out == []


def test_unused_detected():
    imported = ["requests"]
    out = A.detect_unused(PYPROJECT, imported)
    assert any(f["package"] == "numpy" for f in out)


def test_unused_mapping():
    imported = ["dotenv"]
    out = A.detect_unused(PYPROJECT, imported, mapping={"python-dotenv": "dotenv"})
    assert not any(f["package"] == "python-dotenv" for f in out)


# ═══════════════ detect_outdated ═══════════════
def test_outdated_detected():
    out = A.detect_outdated(PYPROJECT, {"numpy": "2.0"})
    assert any(f["package"] == "numpy" for f in out)


def test_outdated_none_when_current():
    out = A.detect_outdated(PYPROJECT, {"numpy": "1.26"})
    assert out == []


def test_outdated_none_when_newer():
    out = A.detect_outdated(PYPROJECT, {"numpy": "1.0"})
    assert out == []


@pytest.mark.parametrize("cur,latest,flag", [
    ("1.0", "2.0", True), ("2.0", "2.0", False), ("2.1", "2.0", False),
    ("1.26", "1.26.4", True), ("1.26.4", "1.26", False),
])
def test_version_tuple_compare(cur, latest, flag):
    txt = f'[project]\ndependencies = ["pkg>={cur}"]'
    out = A.detect_outdated(txt, {"pkg": latest})
    assert (len(out) > 0) == flag


# ═══════════════ dependency_graph ═══════════════
def test_graph_nodes():
    g = A.dependency_graph([("a", "b"), ("b", "c")])
    assert g["nodes"] == ["a", "b", "c"]


def test_graph_no_cycle():
    g = A.dependency_graph([("a", "b"), ("b", "c")])
    assert g["has_cycle"] is False


def test_graph_cycle():
    g = A.dependency_graph([("a", "b"), ("b", "a")])
    assert g["has_cycle"] is True


def test_graph_self_cycle():
    g = A.dependency_graph([("a", "a")])
    assert g["has_cycle"] is True


def test_graph_edges_sorted():
    g = A.dependency_graph([("a", "z"), ("a", "b")])
    assert g["edges"]["a"] == ["b", "z"]


def test_graph_deterministic():
    e = [("a", "b"), ("c", "d")]
    assert A.dependency_graph(e) == A.dependency_graph(e)


# ═══════════════ build_report ═══════════════
def test_report_ok():
    rep = A.build_report(PYPROJECT)
    assert rep["ok"] is True


def test_report_with_all():
    rep = A.build_report(PYPROJECT, imported_modules=["requests"],
                         latest_versions={"numpy": "2.0"},
                         edges=[("requests", "urllib3")])
    assert rep["finding_count"] >= 1
    assert rep["graph"] is not None


def test_report_deterministic():
    rep1 = A.build_report(PYPROJECT, imported_modules=["requests"])
    rep2 = A.build_report(PYPROJECT, imported_modules=["requests"])
    assert rep1 == rep2


def test_report_by_code():
    rep = A.build_report(PYPROJECT, latest_versions={"numpy": "9.0", "pandas": "9.0"})
    assert rep["by_code"].get("OUTDATED_DEP") == 2


def test_report_findings_sorted():
    rep = A.build_report(PYPROJECT, imported_modules=[], latest_versions={"numpy": "9.0"})
    codes = [(f["code"], f["package"]) for f in rep["findings"]]
    assert codes == sorted(codes)


# ═══════════════ real pyproject ═══════════════
def test_real_pyproject_parses():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    path = os.path.join(root, "pyproject.toml")
    if os.path.exists(path):
        scan = A.scan_dependencies(open(path).read())
        assert scan["count"] >= 1
        assert any(d["canonical"] == "requests" for d in scan["dependencies"])


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


@pytest.mark.parametrize("path", _SRC)
def test_no_execution_or_network(path):
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in ("execute_trade", "place_order", "deploy", "install_package")
