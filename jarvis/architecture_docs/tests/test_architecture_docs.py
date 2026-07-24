"""P36 architecture_docs 테스트 — 문서 생성·검증·아키텍처 일관성(중복책임·의존성위반·소유권모호성).
문서화 전용, 리팩터링 없음."""
from __future__ import annotations

import os

import pytest

from jarvis.architecture_docs import generator, validate
from jarvis.architecture_docs import models as M
from jarvis.architecture_docs.models import ARCHITECTURE_DOCS, LAYER_RESPONSIBILITIES, doc_hash
from jarvis.system_integration.models import LAYER_REGISTRY


# ═══════════════ doc catalog ═══════════════
def test_nine_docs():
    assert len(ARCHITECTURE_DOCS) == 9


@pytest.mark.parametrize("doc", ARCHITECTURE_DOCS)
def test_doc_name_md(doc):
    assert doc.endswith(".md")


def test_generate_docs_complete():
    docs = generator.generate_docs()
    assert set(docs) == set(ARCHITECTURE_DOCS)


@pytest.mark.parametrize("doc", ARCHITECTURE_DOCS)
def test_each_doc_nonempty(doc):
    assert len(generator.generate_docs()[doc]) > 0


@pytest.mark.parametrize("doc", ARCHITECTURE_DOCS)
def test_each_doc_has_heading(doc):
    assert generator.generate_docs()[doc].lstrip().startswith("#")


def test_generate_deterministic():
    assert generator.generate_docs() == generator.generate_docs()


@pytest.mark.parametrize("doc", ARCHITECTURE_DOCS)
def test_doc_hash_deterministic(doc):
    c = generator.generate_docs()[doc]
    assert doc_hash(c) == doc_hash(c)


# ═══════════════ 계층 문서화 커버리지 ═══════════════
@pytest.mark.parametrize("layer", LAYER_REGISTRY)
def test_layer_documented(layer):
    assert M.is_documented(layer["package"])


@pytest.mark.parametrize("layer", LAYER_REGISTRY)
def test_layer_in_overview(layer):
    overview = generator.generate_docs()["01_system_architecture_overview.md"]
    assert layer["package"] in overview
    assert layer["phase"] in overview


@pytest.mark.parametrize("layer", LAYER_REGISTRY)
def test_layer_in_responsibility_map(layer):
    doc = generator.generate_docs()["02_layer_responsibility_map.md"]
    assert layer["package"] in doc


@pytest.mark.parametrize("layer", LAYER_REGISTRY)
def test_layer_prefix_in_ownership(layer):
    doc = generator.generate_docs()["04_ownership_boundary.md"]
    assert layer["prefix"] in doc


@pytest.mark.parametrize("layer", LAYER_REGISTRY)
def test_layer_in_module_reference(layer):
    doc = generator.generate_docs()["09_module_reference.md"]
    assert f"jarvis.{layer['package']}" in doc


@pytest.mark.parametrize("layer", LAYER_REGISTRY)
def test_layer_in_ledger_catalog(layer):
    doc = generator.generate_docs()["05_ledger_catalog.md"]
    assert layer["package"] in doc


@pytest.mark.parametrize("layer", LAYER_REGISTRY)
def test_layer_in_dependency_doc(layer):
    doc = generator.generate_docs()["06_dependency_graph.md"]
    assert layer["package"] in doc


def test_responsibilities_cover_registry():
    for l in LAYER_REGISTRY:
        assert l["package"] in LAYER_RESPONSIBILITIES


# ═══════════════ 문서 내용 일관성 ═══════════════
def test_overview_mentions_no_execution():
    doc = generator.generate_docs()["01_system_architecture_overview.md"]
    assert "No live execution" in doc or "no autonomous trading" in doc.lower()


def test_security_boundary_lists_forbidden():
    doc = generator.generate_docs()["07_security_boundary.md"]
    assert "execute_trade" in doc
    assert "broker" in doc


def test_ledger_catalog_counts_ledgers():
    doc = generator.generate_docs()["05_ledger_catalog.md"]
    assert "Total owned ledgers" in doc


def test_ownership_boundary_immutable_note():
    doc = generator.generate_docs()["04_ownership_boundary.md"]
    assert "immutable" in doc.lower()


def test_workflow_no_execution_note():
    doc = generator.generate_docs()["08_research_workflow.md"]
    assert "never executes" in doc.lower() or "no autonomous" in doc.lower()


def test_data_flow_read_only():
    doc = generator.generate_docs()["03_data_flow_diagram.md"]
    assert "READ ONLY" in doc


@pytest.mark.parametrize("b", M.SECURITY_BOUNDARIES)
def test_security_boundary_each_listed(b):
    doc = generator.generate_docs()["07_security_boundary.md"]
    assert b in doc


# ═══════════════ 아키텍처 일관성 검사 ═══════════════
def test_run_consistency_checks_ok():
    res = validate.run_consistency_checks()
    assert res["ok"] is True


def test_all_layers_documented_check():
    assert validate.check_all_layers_documented()["ok"] is True


def test_no_duplicate_responsibilities():
    assert validate.check_no_duplicate_responsibilities()["ok"] is True


def test_ownership_unambiguous():
    assert validate.check_ownership_unambiguous()["ok"] is True


def test_no_dependency_violations():
    assert validate.check_no_dependency_violations()["ok"] is True


def test_docs_generated_check():
    r = validate.check_docs_generated()
    assert r["ok"] is True
    assert r["count"] == 9


def test_docs_deterministic_check():
    assert validate.check_docs_deterministic()["ok"] is True


def test_consistency_has_six_checks():
    res = validate.run_consistency_checks()
    assert len(res["checks"]) == 6


# ═══════════════ 생성된 문서 파일 존재(디스크) ═══════════════
def test_docs_dir_exists():
    assert os.path.isdir(generator.docs_dir())


@pytest.mark.parametrize("doc", ARCHITECTURE_DOCS)
def test_doc_file_on_disk(doc):
    assert os.path.exists(os.path.join(generator.docs_dir(), doc))


@pytest.mark.parametrize("doc", ARCHITECTURE_DOCS)
def test_doc_file_matches_generated(doc):
    on_disk = open(os.path.join(generator.docs_dir(), doc)).read()
    assert on_disk == generator.generate_docs()[doc]  # 디스크 == 결정적 생성


# ═══════════════ CLI ═══════════════
def test_cli_list(capsys):
    from jarvis.architecture_docs.__main__ import main
    assert main(["list"]) == 0
    import json
    out = json.loads(capsys.readouterr().out)
    assert len(out["docs"]) == 9


def test_cli_validate(capsys):
    from jarvis.architecture_docs.__main__ import main
    assert main(["validate"]) == 0


def test_cli_generate(capsys):
    from jarvis.architecture_docs.__main__ import main
    assert main(["generate"]) == 0
    import json
    out = json.loads(capsys.readouterr().out)
    assert out["count"] == 9


# ═══════════════ 안전성(자체 패키지, 리팩터링/실행 없음) ═══════════════
import ast  # noqa: E402

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


def test_no_new_ledgers():
    # P36 은 문서화 계층 — 새 원장/원장 파일 없음
    assert not os.path.exists(os.path.join(_PKG, "ledger.py"))


# ═══════════════ end-to-end ═══════════════
def test_end_to_end_documentation_freeze():
    # 1. 9개 문서 결정적 생성
    docs = generator.generate_docs()
    assert len(docs) == 9
    # 2. 전 계층 문서화 + 일관성
    res = validate.run_consistency_checks()
    assert res["ok"] is True
    # 3. 중복 책임·의존성 위반·소유권 모호성 없음
    assert validate.check_no_duplicate_responsibilities()["ok"]
    assert validate.check_no_dependency_violations()["ok"]
    assert validate.check_ownership_unambiguous()["ok"]
    # 4. 디스크 문서 == 생성 문서(freeze 일관성)
    for name, content in docs.items():
        assert open(os.path.join(generator.docs_dir(), name)).read() == content
