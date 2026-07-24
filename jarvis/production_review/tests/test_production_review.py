"""P39 production_review 테스트 — 운영 문서·준비성 평가(재현성·복구성·관측성·유지보수성). 배포 없음, 평가만."""
from __future__ import annotations

import ast
import os

import pytest

from jarvis.production_review import assess, generator
from jarvis.production_review import models as M
from jarvis.production_review.models import (
    DEPLOYMENT_CHECKLIST,
    ENVIRONMENT_REQUIREMENTS,
    FAILURE_SCENARIOS,
    PRODUCTION_DOCS,
    READINESS_DIMENSIONS,
    doc_hash,
)


# ═══════════════ doc catalog ═══════════════
def test_eight_docs():
    assert len(PRODUCTION_DOCS) == 8


@pytest.mark.parametrize("doc", PRODUCTION_DOCS)
def test_doc_name_md(doc):
    assert doc.endswith(".md")


def test_generate_complete():
    assert set(generator.generate_docs()) == set(PRODUCTION_DOCS)


@pytest.mark.parametrize("doc", PRODUCTION_DOCS)
def test_each_doc_nonempty(doc):
    assert len(generator.generate_docs()[doc]) > 0


@pytest.mark.parametrize("doc", PRODUCTION_DOCS)
def test_each_doc_heading(doc):
    assert generator.generate_docs()[doc].lstrip().startswith("#")


def test_generate_deterministic():
    assert generator.generate_docs() == generator.generate_docs()


@pytest.mark.parametrize("doc", PRODUCTION_DOCS)
def test_doc_hash_deterministic(doc):
    c = generator.generate_docs()[doc]
    assert doc_hash(c) == doc_hash(c)


# ═══════════════ doc content ═══════════════
def test_deployment_checklist_no_deployment():
    doc = generator.generate_docs()["01_deployment_checklist.md"]
    assert "No production deployment" in doc


@pytest.mark.parametrize("item", DEPLOYMENT_CHECKLIST)
def test_checklist_item_present(item):
    doc = generator.generate_docs()["01_deployment_checklist.md"]
    assert item in doc


@pytest.mark.parametrize("req", ENVIRONMENT_REQUIREMENTS)
def test_env_req_present(req):
    doc = generator.generate_docs()["02_environment_requirements.md"]
    assert req in doc


@pytest.mark.parametrize("scen", FAILURE_SCENARIOS)
def test_failure_scenario_present(scen):
    doc = generator.generate_docs()["07_failure_scenarios.md"]
    assert scen in doc


def test_env_requires_python311():
    doc = generator.generate_docs()["02_environment_requirements.md"]
    assert "Python 3.11" in doc


def test_env_no_broker():
    doc = generator.generate_docs()["02_environment_requirements.md"]
    assert "브로커" in doc or "broker" in doc.lower()


def test_recovery_procedures_append_only():
    doc = generator.generate_docs()["04_recovery_procedures.md"]
    assert "append-only" in doc.lower()


def test_backup_strategy_hash():
    doc = generator.generate_docs()["05_backup_strategy.md"]
    assert "SHA256" in doc or "hash" in doc.lower()


def test_monitoring_checklist_layers():
    doc = generator.generate_docs()["06_monitoring_checklist.md"]
    assert "monitoring" in doc.lower()
    assert "security audit" in doc.lower()


def test_operational_procedures_readonly():
    doc = generator.generate_docs()["08_operational_procedures.md"]
    assert "read-only" in doc.lower()
    assert "no automated action" in doc.lower() or "record-only" in doc.lower()


def test_config_review_no_secrets():
    doc = generator.generate_docs()["03_configuration_review.md"]
    assert "No secrets" in doc


# ═══════════════ readiness assessment ═══════════════
def test_readiness_dimensions_count():
    assert len(READINESS_DIMENSIONS) == 4


@pytest.mark.parametrize("d", READINESS_DIMENSIONS)
def test_readiness_dimensions(d):
    assert d in READINESS_DIMENSIONS


def test_run_readiness_ready():
    res = assess.run_readiness_assessment()
    assert res["ready"] is True


def test_no_deployment_performed():
    res = assess.run_readiness_assessment()
    assert res["deployment_performed"] is False


def test_assess_reproducibility():
    r = assess.assess_reproducibility()
    assert r["ok"] is True
    assert r["missing"] == []


def test_assess_recoverability():
    r = assess.assess_recoverability()
    assert r["ok"] is True
    assert r["reliability_layer"] is True
    assert r["verify_all"] is True


def test_assess_observability():
    r = assess.assess_observability()
    assert r["ok"] is True
    assert r["monitoring"] and r["dashboard"] and r["meta"]


def test_assess_maintainability():
    r = assess.assess_maintainability()
    assert r["ok"] is True
    assert r["incomplete"] == []


def test_assessment_has_four_dimensions():
    res = assess.run_readiness_assessment()
    assert len(res["dimensions"]) == 4
    dims = {d["dimension"] for d in res["dimensions"]}
    assert dims == set(READINESS_DIMENSIONS)


def test_docs_complete_check():
    r = assess.docs_complete()
    assert r["ok"] is True
    assert r["count"] == 8


def test_assessment_deterministic():
    assert assess.run_readiness_assessment() == assess.run_readiness_assessment()


# ═══════════════ 각 계층 재현성/복구성 커버리지 ═══════════════
from jarvis.system_integration.models import LAYER_REGISTRY  # noqa: E402


@pytest.mark.parametrize("layer", LAYER_REGISTRY)
def test_layer_has_replay(layer):
    assert assess._has_symbol(layer["package"], "verify.py", "def replay(")


@pytest.mark.parametrize("layer", LAYER_REGISTRY)
def test_layer_has_verify_chain(layer):
    assert assess._has_symbol(layer["package"], "verify.py", "def verify_chain(")


@pytest.mark.parametrize("layer", LAYER_REGISTRY)
def test_layer_maintainable_structure(layer):
    for m in ("models.py", "ledger.py", "engine.py", "verify.py", "__main__.py"):
        assert assess._has_module(layer["package"], m)


# ═══════════════ docs on disk ═══════════════
def test_docs_dir_exists():
    assert os.path.isdir(generator.docs_dir())


@pytest.mark.parametrize("doc", PRODUCTION_DOCS)
def test_doc_file_on_disk(doc):
    assert os.path.exists(os.path.join(generator.docs_dir(), doc))


@pytest.mark.parametrize("doc", PRODUCTION_DOCS)
def test_doc_matches_generated(doc):
    on_disk = open(os.path.join(generator.docs_dir(), doc)).read()
    assert on_disk == generator.generate_docs()[doc]


# ═══════════════ CLI ═══════════════
def test_cli_list(capsys):
    from jarvis.production_review.__main__ import main
    assert main(["list"]) == 0
    import json
    assert len(json.loads(capsys.readouterr().out)["docs"]) == 8


def test_cli_assess(capsys):
    from jarvis.production_review.__main__ import main
    assert main(["assess"]) == 0
    import json
    out = json.loads(capsys.readouterr().out)
    assert out["ready"] is True
    assert out["deployment_performed"] is False


def test_cli_generate(capsys):
    from jarvis.production_review.__main__ import main
    assert main(["generate"]) == 0
    import json
    assert json.loads(capsys.readouterr().out)["count"] == 8


# ═══════════════ 자체 안전성(배포/실행 없음) ═══════════════
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
    bad = ("execute", "deploy", "trade", "allocate", "approve", "provision")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert ("claude" + "-opus") not in open(path).read().lower()


def test_no_ledger():
    assert not os.path.exists(os.path.join(_PKG, "ledger.py"))


# ═══════════════ end-to-end ═══════════════
def test_end_to_end_readiness():
    # 1. 8개 운영 문서 결정적 생성
    docs = generator.generate_docs()
    assert len(docs) == 8
    # 2. 4차원 준비성 평가 통과, 배포 없음
    res = assess.run_readiness_assessment()
    assert res["ready"] is True
    assert res["deployment_performed"] is False
    # 3. 재현성·복구성·관측성·유지보수성 모두 OK
    assert assess.assess_reproducibility()["ok"]
    assert assess.assess_recoverability()["ok"]
    assert assess.assess_observability()["ok"]
    assert assess.assess_maintainability()["ok"]
    # 4. 디스크 문서 == 생성 문서
    for name, content in docs.items():
        assert open(os.path.join(generator.docs_dir(), name)).read() == content
