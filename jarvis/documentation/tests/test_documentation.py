"""P16 documentation 테스트 — 마크다운 유효성·링크·다이어그램·완전성·API 커버리지·보안."""
from __future__ import annotations

import ast
import os

import pytest

from jarvis.documentation import apidoc as AD
from jarvis.documentation import manifest as M
from jarvis.documentation import validate as V

ROOT = M.doc_root()
REQUIRED = M.REQUIRED_DOCS
MERMAID = M.MERMAID_DOCS


def _path(rel):
    return os.path.join(ROOT, rel)


# ═══════════════ validate_markdown ═══════════════
def test_markdown_valid_basic():
    assert V.validate_markdown("# Title\n\nbody")["ok"] is True


def test_markdown_missing_h1():
    assert V.validate_markdown("no title\ntext")["ok"] is False


def test_markdown_empty():
    assert V.validate_markdown("")["ok"] is False


def test_markdown_unbalanced_fence():
    res = V.validate_markdown("# T\n\n```python\nx=1\n")
    assert res["ok"] is False
    assert "unbalanced_code_fence" in res["issues"]


def test_markdown_balanced_fence():
    assert V.validate_markdown("# T\n\n```python\nx=1\n```\n")["ok"] is True


def test_markdown_bad_heading():
    res = V.validate_markdown("# T\n\n#bad\n")
    assert any(i.startswith("bad_heading") for i in res["issues"])


# ═══════════════ links ═══════════════
def test_extract_links_ignores_external():
    links = V.extract_links("[a](http://x.com) [b](rel.md) [c](#anchor)")
    assert links == ["rel.md"]


def test_extract_links_strips_anchor():
    assert V.extract_links("[a](file.md#sec)") == ["file.md"]


def test_validate_links_ok(tmp_path):
    (tmp_path / "a.md").write_text("# A")
    (tmp_path / "b.md").write_text("# B\n[a](a.md)")
    res = V.validate_links(str(tmp_path / "b.md"), "# B\n[a](a.md)")
    assert res["ok"] is True


def test_validate_links_broken(tmp_path):
    res = V.validate_links(str(tmp_path / "b.md"), "# B\n[x](ghost.md)")
    assert res["ok"] is False
    assert "ghost.md" in res["broken"]


# ═══════════════ diagrams ═══════════════
def test_count_mermaid():
    text = "# T\n```mermaid\nA-->B\n```\n```mermaid\nC-->D\n```\n"
    assert V.count_mermaid_blocks(text) == 2


def test_validate_diagram_ok():
    assert V.validate_diagram("```mermaid\nA-->B\n```")["ok"] is True


def test_validate_diagram_empty_block():
    assert V.validate_diagram("```mermaid\n\n```")["ok"] is False


def test_validate_diagram_none():
    assert V.validate_diagram("# just text")["ok"] is False


# ═══════════════ completeness / coverage ═══════════════
def test_completeness_all_present():
    assert V.check_completeness()["ok"] is True


def test_completeness_count():
    comp = V.check_completeness()
    assert comp["present"] == comp["total"] == len(REQUIRED)


def test_api_coverage_ok():
    assert V.check_api_coverage()["ok"] is True


def test_validate_all_ok():
    assert V.validate_all()["ok"] is True


# ═══════════════ 각 필수 문서 파라미터화 ═══════════════
@pytest.mark.parametrize("rel", REQUIRED)
def test_required_doc_exists(rel):
    assert os.path.exists(_path(rel)), rel


@pytest.mark.parametrize("rel", REQUIRED)
def test_required_doc_markdown_valid(rel):
    text = V.read(_path(rel))
    res = V.validate_markdown(text)
    assert res["ok"], (rel, res["issues"])


@pytest.mark.parametrize("rel", REQUIRED)
def test_required_doc_links_resolve(rel):
    p = _path(rel)
    res = V.validate_links(p, V.read(p))
    assert res["ok"], (rel, res["broken"])


@pytest.mark.parametrize("rel", REQUIRED)
def test_required_doc_starts_with_h1(rel):
    assert V.read(_path(rel)).lstrip().startswith("# "), rel


@pytest.mark.parametrize("rel", REQUIRED)
def test_required_doc_nonempty(rel):
    assert len(V.read(_path(rel)).strip()) > 40, rel


@pytest.mark.parametrize("rel", MERMAID)
def test_diagram_has_mermaid(rel):
    assert V.validate_diagram(V.read(_path(rel)))["ok"], rel


# ═══════════════ manifest ═══════════════
def test_discover_packages_nonempty():
    pkgs = M.discover_packages()
    assert len(pkgs) > 50
    assert "research_manager" in pkgs


def test_discover_packages_sorted():
    pkgs = M.discover_packages()
    assert pkgs == sorted(pkgs)


def test_doc_root_exists():
    assert os.path.isdir(M.doc_root())


def test_required_docs_unique():
    assert len(REQUIRED) == len(set(REQUIRED))


def test_core_documented_packages_exist():
    pkgs = set(M.discover_packages())
    for p in M.CORE_DOCUMENTED_PACKAGES:
        assert p in pkgs, p


# ═══════════════ apidoc ═══════════════
def test_introspect_known_package():
    info = AD.introspect_package("research_manager")
    assert info["module"] == "jarvis.research_manager"
    assert info["has_cli"] is True


def test_introspect_has_functions_or_classes():
    info = AD.introspect_package("benchmark")
    assert info["functions"] or info["classes"]


def test_generate_reference_contains_packages():
    ref = AD.generate_reference(["benchmark", "security"])
    assert "jarvis.benchmark" in ref
    assert "jarvis.security" in ref


def test_generate_reference_deterministic():
    a = AD.generate_reference(["benchmark", "security"])
    b = AD.generate_reference(["security", "benchmark"])
    assert a == b  # 정렬로 순서 무관


def test_generate_reference_has_h1():
    assert AD.generate_reference(["benchmark"]).startswith("# API Reference")


def test_cli_inventory_nonempty():
    clis = AD.cli_inventory()
    assert "research_manager" in clis
    assert len(clis) > 20


def test_write_reference(tmp_path):
    p = str(tmp_path / "ref.md")
    AD.write_reference(p, ["benchmark"])
    assert os.path.exists(p)
    assert "jarvis.benchmark" in open(p).read()


def test_reference_file_covers_core():
    ref = V.read(_path("api/reference.md"))
    for pkg in M.CORE_DOCUMENTED_PACKAGES:
        assert f"jarvis.{pkg}" in ref, pkg


def test_reference_markdown_valid():
    assert V.validate_markdown(V.read(_path("api/reference.md")))["ok"] is True


# ═══════════════ CLI ═══════════════
def test_cli_validate(capsys):
    from jarvis.documentation.__main__ import main
    rc = main(["validate"])
    assert rc == 0


def test_cli_packages(capsys):
    import json
    from jarvis.documentation.__main__ import main
    assert main(["packages"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert "research_manager" in out["packages"]


def test_cli_cli_list(capsys):
    import json
    from jarvis.documentation.__main__ import main
    assert main(["cli"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["cli_packages"]) > 20


def test_cli_gen(tmp_path, monkeypatch, capsys):
    import json
    monkeypatch.setattr("jarvis.documentation.apidoc.M.doc_root", lambda: str(tmp_path))
    os.makedirs(str(tmp_path / "api"), exist_ok=True)
    from jarvis.documentation.__main__ import main
    assert main(["gen"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert os.path.exists(out["generated"])


# ═══════════════ 보안 (문서 도구는 실행 능력 없음) ═══════════════
_PKG = os.path.dirname(os.path.dirname(__file__))
_SRC = [os.path.join(_PKG, f) for f in os.listdir(_PKG) if f.endswith(".py")]

_FORBIDDEN = ("jarvis.execution", "jarvis.broker", "jarvis.portfolio", "jarvis.risk",
              "jarvis.permission", "jarvis.deployment", "jarvis.live", "jarvis.order",
              "jarvis.live_execution")


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
def test_no_execution_defs(path):
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in ("execute_trade", "place_order", "deploy_model",
                                     "allocate_capital")
