"""Integration Audit(P41) 테스트 — 카테고리 분류·스캐너(합성/실제 트리)·의존성·중복·미사용·통합제안·렌더·안전.

**읽기전용 정적 분석.** 합성 트리(tmp)로 결정적 동작을 검증하고, 실제 jarvis 트리로 규모를 검증한다.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from jarvis.integration_audit import models as M
from jarvis.integration_audit import scanner
from jarvis.integration_audit.engine import IntegrationAuditEngine

SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"


# ──────────────────────── 합성 트리 픽스처 ────────────────────────
def _mk_pkg(root: pathlib.Path, name: str, files=("__init__.py",), tests=False, cli=False):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    for f in files:
        (d / f).write_text("", encoding="utf-8")
    if "__init__.py" not in files:
        (d / "__init__.py").write_text("", encoding="utf-8")
    if tests:
        (d / "tests").mkdir(exist_ok=True)
        (d / "tests" / "__init__.py").write_text("", encoding="utf-8")
    if cli:
        (d / "__main__.py").write_text("", encoding="utf-8")
    return d


@pytest.fixture()
def synth(tmp_path):
    root = tmp_path / "jarvis"
    root.mkdir()
    # standard 패턴 + 서로 import 하는 계열
    _mk_pkg(root, "research_memory", ("__init__.py", "engine.py", "ledger.py", "models.py"),
            tests=True, cli=True)
    _mk_pkg(root, "research_memory_system", ("__init__.py", "engine.py", "ledger.py", "models.py"))
    _mk_pkg(root, "research_agent", ("__init__.py", "engine.py", "models.py"))   # partial
    _mk_pkg(root, "research_agent_coordinator", ("__init__.py", "engine.py", "ledger.py",
                                                 "models.py"))
    _mk_pkg(root, "knowledge", ("__init__.py", "engine.py", "ledger.py", "models.py"))
    _mk_pkg(root, "orphan_module", ("__init__.py", "util.py"))                   # other, 고립
    # 의존성: research_memory_system → research_memory, knowledge → research_memory
    (root / "research_memory_system" / "engine.py").write_text(
        "from jarvis.research_memory import engine\n", encoding="utf-8")
    (root / "knowledge" / "engine.py").write_text(
        "import jarvis.research_memory.models\n", encoding="utf-8")
    return str(root)


# ──────────────────────── categorize ────────────────────────
@pytest.mark.parametrize("name,cat", [
    ("research_strategy_generation", M.CAT_RESEARCH),
    ("alpha_intelligence", M.CAT_RESEARCH),
    ("causal_intelligence", M.CAT_RESEARCH),
    ("knowledge_intelligence", M.CAT_KNOWLEDGE),
    ("research_memory_intelligence", M.CAT_KNOWLEDGE),
    ("research_kg", M.CAT_KNOWLEDGE),
    ("agent_runtime", M.CAT_AGENTS),
    ("research_council", M.CAT_AGENTS),
    ("simulation_environment", M.CAT_SIMULATION),
    ("paper", M.CAT_SIMULATION),
    ("experiment_tracking", M.CAT_SIMULATION),
    ("research_observability", M.CAT_MONITORING),
    ("diagnostics", M.CAT_MONITORING),
    ("watchdog", M.CAT_MONITORING),
    ("access_governance", M.CAT_SYSTEM),
    ("security_audit", M.CAT_SYSTEM),
    ("research_api_gateway", M.CAT_SYSTEM),
    ("execution_cost", M.CAT_EXECUTION),
    ("live_execution", M.CAT_EXECUTION),
    ("broker_readonly", M.CAT_EXECUTION),
    ("portfolio", M.CAT_EXECUTION),
])
def test_categorize(name, cat):
    assert M.categorize(name) == cat


def test_categorize_unknown_is_other():
    assert M.categorize("zzz_qux") == M.CAT_OTHER
    assert M.categorize("") == M.CAT_OTHER


def test_categorize_deterministic():
    assert M.categorize("research_memory") == M.categorize("research_memory")


def test_all_categories_defined():
    assert len(M.CATEGORIES) == 8
    assert M.CAT_RESEARCH in M.CATEGORIES


@pytest.mark.parametrize("name,fam", [
    ("research_memory_system", "research_memory"),
    ("agent_runtime", "agent"),
    ("knowledge", "knowledge"),
    ("a_b_c", "a_b"),
])
def test_family_of(name, fam):
    assert M.family_of(name) == fam


# ──────────────────────── 스캐너(합성) ────────────────────────
def test_list_modules(synth):
    mods = scanner.list_modules(synth)
    assert "research_memory" in mods
    assert "knowledge" in mods
    assert len(mods) == 6


def test_list_modules_excludes_non_package(synth, tmp_path):
    (pathlib.Path(synth) / "not_a_pkg").mkdir()
    (pathlib.Path(synth) / "not_a_pkg" / "x.py").write_text("", encoding="utf-8")
    assert "not_a_pkg" not in scanner.list_modules(synth)


def test_module_py_files_excludes_tests(synth):
    files = scanner.module_py_files(synth, "research_memory")
    assert not any("tests" in f for f in files)


def test_classify_pattern_standard(synth):
    assert scanner.classify_pattern(synth, "research_memory") == "standard"


def test_classify_pattern_partial(synth):
    assert scanner.classify_pattern(synth, "research_agent") == "partial"


def test_classify_pattern_other(synth):
    assert scanner.classify_pattern(synth, "orphan_module") == "other"


def test_module_info_fields(synth):
    info = scanner.module_info(synth, "research_memory")
    assert info.category == M.CAT_KNOWLEDGE
    assert info.pattern == "standard"
    assert info.has_tests is True
    assert info.has_cli is True
    assert info.py_files >= 4


def test_inventory_count(synth):
    assert len(scanner.inventory(synth)) == 6


def test_import_edges(synth):
    edges = scanner.import_edges(synth)
    assert ("research_memory_system", "research_memory") in edges
    assert ("knowledge", "research_memory") in edges


def test_import_edges_no_self_loop(synth):
    assert all(s != d for s, d in scanner.import_edges(synth))


def test_in_degrees(synth):
    deg = scanner.in_degrees(synth)
    assert deg["research_memory"] == 2
    assert deg["knowledge"] == 0


def test_orphan_modules(synth):
    orph = scanner.orphan_modules(synth)
    assert "orphan_module" in orph
    assert "research_memory" not in orph


def test_name_clusters(synth):
    # family_of 는 마지막 토큰만 제거 → research_agent, research_memory 는 family "research"
    clusters = scanner.name_clusters(scanner.list_modules(synth))
    assert "research" in clusters
    assert set(clusters["research"]) == {"research_agent", "research_memory"}
    assert clusters["research_memory"] == ["research_memory_system"]


def test_duplicate_clusters(synth):
    # size>=2 계열은 "research"(research_agent + research_memory), 카테고리 혼합(MIXED)
    clusters = scanner.duplicate_clusters(synth)
    fams = {c.family for c in clusters}
    assert "research" in fams
    research = next(c for c in clusters if c.family == "research")
    assert research.category == "MIXED"
    assert research.size == 2


def test_duplicate_clusters_min_size(synth):
    # min_size=3 이면 크기 2 계열은 제외
    assert scanner.duplicate_clusters(synth, min_size=3) == []


def test_bad_syntax_file_ignored(synth):
    (pathlib.Path(synth) / "knowledge" / "broken.py").write_text("def (:\n", encoding="utf-8")
    # 파싱 실패 파일은 무시하고 계속
    edges = scanner.import_edges(synth)
    assert ("knowledge", "research_memory") in edges


# ──────────────────────── 엔진(합성) ────────────────────────
@pytest.fixture()
def eng(synth):
    return IntegrationAuditEngine(root=synth)


def test_engine_module_names(eng):
    assert len(eng.module_names()) == 6


def test_engine_category_distribution(eng):
    dist = eng.category_distribution()
    assert dist.get(M.CAT_KNOWLEDGE, 0) >= 2
    assert sum(dist.values()) == 6


def test_engine_pattern_distribution(eng):
    dist = eng.pattern_distribution()
    assert dist.get("standard", 0) >= 3
    assert sum(dist.values()) == 6


def test_engine_dependency_stats(eng):
    s = eng.dependency_stats()
    assert s.node_count == 6
    assert s.edge_count == 2
    assert "orphan_module" in s.orphans
    assert s.top_imported[0][0] == "research_memory"


def test_engine_duplicate_clusters(eng):
    clusters = eng.duplicate_clusters()
    assert len(clusters) == 1
    assert clusters[0].family == "research"


def test_engine_orphans(eng):
    assert "orphan_module" in eng.orphans()


def test_engine_integration_proposals(eng):
    props = eng.integration_proposals()
    assert props
    assert all(p.action in ("INTEGRATE", "REVIEW", "KEEP") for p in props)


def test_engine_roadmap(eng):
    rm = eng.roadmap()
    assert len(rm) >= 4
    assert any("P42" in s for s in rm)


def test_engine_build_report(eng):
    r = eng.build_report("2026-01-01T00:00:00Z")
    assert r.module_count == 6
    assert r.digest.startswith("sha256:")
    assert len(r.modules) == 6


def test_engine_report_deterministic(eng):
    r1 = eng.build_report("t")
    r2 = eng.build_report("t")
    assert r1.digest == r2.digest
    assert r1.to_dict() == r2.to_dict()


def test_engine_summary(eng):
    s = eng.summary()
    assert s["module_count"] == 6
    assert "digest" in s


def test_engine_render_docs(eng, tmp_path):
    out = tmp_path / "docs_out"
    written = eng.render_docs(str(out))
    assert len(written) == 8
    assert (out / "01_module_inventory.md").exists()
    assert (out / "07_integration_proposal.md").exists()
    assert (out / "README.md").exists()


def test_render_docs_content(eng, tmp_path):
    out = tmp_path / "docs_out"
    eng.render_docs(str(out))
    inv = (out / "01_module_inventory.md").read_text(encoding="utf-8")
    assert "research_memory" in inv
    prop = (out / "07_integration_proposal.md").read_text(encoding="utf-8")
    assert "INTEGRATE" in prop or "REVIEW" in prop or "KEEP" in prop


def test_render_docs_idempotent(eng, tmp_path):
    out = tmp_path / "docs_out"
    w1 = eng.render_docs(str(out))
    c1 = (out / "01_module_inventory.md").read_text(encoding="utf-8")
    w2 = eng.render_docs(str(out))
    c2 = (out / "01_module_inventory.md").read_text(encoding="utf-8")
    assert w1 == w2
    assert c1 == c2


# ──────────────────────── 실제 jarvis 트리 ────────────────────────
@pytest.fixture()
def real():
    return IntegrationAuditEngine()


def test_real_root_is_jarvis(real):
    assert real.root.endswith("jarvis")


def test_real_module_count_large(real):
    assert len(real.module_names()) >= 100


def test_real_contains_known_modules(real):
    names = set(real.module_names())
    for m in ("integration_audit", "research_memory_intelligence", "agent_runtime",
              "workflow_automation", "model_management"):
        assert m in names


def test_real_category_distribution(real):
    dist = real.category_distribution()
    assert dist.get(M.CAT_RESEARCH, 0) > 0
    assert dist.get(M.CAT_KNOWLEDGE, 0) > 0
    assert dist.get(M.CAT_AGENTS, 0) > 0


def test_real_standard_pattern_majority(real):
    dist = real.pattern_distribution()
    assert dist.get("standard", 0) >= 80


def test_real_dependency_stats(real):
    s = real.dependency_stats()
    assert s.edge_count > 0
    assert s.node_count >= 100


def test_real_duplicate_clusters(real):
    fams = {c.family for c in real.duplicate_clusters()}
    assert "research_memory" in fams or "research_agent" in fams


def test_real_ui_inventory(real):
    ui = real.ui_inventory()
    mods = {u["module"] for u in ui}
    assert "research_dashboard_backend" in mods or "operations_console" in mods


def test_real_build_report_deterministic(real):
    assert real.build_report("t").digest == real.build_report("t").digest


def test_real_integration_audit_self_categorized(real):
    info = {i.name: i for i in real.inventory()}
    assert "integration_audit" in info


def test_real_has_integrate_proposal(real):
    # 실제 트리의 대규모 계열(예: research_*)은 INTEGRATE 제안을 낳는다
    actions = {p.action for p in real.integration_proposals()}
    assert "INTEGRATE" in actions


def test_real_roadmap_mentions_all_phases(real):
    rm = " ".join(real.roadmap())
    for tag in ("P42", "P43", "P44", "P45"):
        assert tag in rm


# ──────────────────────── 안전 스캔 ────────────────────────
_SRC_FILES = [str(SRC / f) for f in ("engine.py", "scanner.py", "models.py",
                                     "__main__.py", "__init__.py")]
_FORBIDDEN_IMPORTS = ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
                      "jarvis.live_trading", "jarvis.portfolio_execution", "jarvis.order")


@pytest.mark.parametrize("path", _SRC_FILES)
def test_no_forbidden_imports(path):
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(f) for f in _FORBIDDEN_IMPORTS), node.module
        if isinstance(node, ast.Import):
            for n in node.names:
                assert not any(n.name.startswith(f) for f in _FORBIDDEN_IMPORTS), n.name


@pytest.mark.parametrize("path", _SRC_FILES)
def test_no_dangerous_defs(path):
    tree = ast.parse(open(path).read())
    bad = ("execute", "trade", "deploy", "allocate", "approve", "place_order", "activate_live",
           "execute_trade", "allocate_capital", "deploy_strategy", "approve_for_trading")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC_FILES)
def test_no_model_id_leak(path):
    assert MODEL_LEAK_TOKEN not in open(path).read().lower()


def test_engine_no_execution_methods(real):
    for m in ("execute", "trade", "deploy", "allocate", "approve"):
        assert not hasattr(real, m)


# ──────────────────────── CLI ────────────────────────
def _cli(argv, capsys):
    from jarvis.integration_audit import __main__ as cli
    rc = cli.main(argv)
    return rc, capsys.readouterr().out


def test_cli_inventory(capsys):
    rc, out = _cli(["inventory"], capsys)
    assert rc == 0
    assert "integration_audit" in out


def test_cli_graph(capsys):
    rc, out = _cli(["graph"], capsys)
    assert rc == 0
    assert "edge_count" in out


def test_cli_duplicates(capsys):
    rc, out = _cli(["duplicates"], capsys)
    assert rc == 0


def test_cli_orphans(capsys):
    rc, out = _cli(["orphans"], capsys)
    assert rc == 0


def test_cli_ui(capsys):
    rc, out = _cli(["ui"], capsys)
    assert rc == 0


def test_cli_proposal(capsys):
    rc, out = _cli(["proposal"], capsys)
    assert rc == 0
    assert "roadmap" in out


def test_cli_summary(capsys):
    rc, out = _cli(["summary"], capsys)
    assert rc == 0
    assert "digest" in out


def test_cli_render(tmp_path, capsys):
    rc, out = _cli(["render", "--out", str(tmp_path / "d")], capsys)
    assert rc == 0
    assert "written" in out
