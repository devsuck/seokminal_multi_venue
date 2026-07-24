"""Unified Navigation(P43) 테스트 — 섹션/항목 매핑·트리·커버리지·중복 페이지·패널 통합·매니페스트·렌더·CLI·안전.

**읽기전용, 결정 권한 없음.** 합성 모듈 목록(주입)으로 결정적 매핑 검증 + 실제 트리로 커버리지/규모 검증.
"""
from __future__ import annotations

import ast
import json
import pathlib

import pytest

from jarvis.research_navigation import models as M
from jarvis.research_navigation.engine import NavigationEngine

SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"

# 합성 모듈 목록(다양한 카테고리·항목 커버)
SYNTH = [
    "research_strategy_generation",  # Research/Alpha
    "alpha_intelligence",            # Research/Alpha
    "experiment_tracking",           # Research/Experiments  (simulation category → Research, item Experiments via 'experiment')
    "experiment_orchestration",      # Research/Experiments
    "simulation_environment",        # Research/Simulation
    "paper",                         # Research/Simulation
    "research_kg",                   # Knowledge/Graph
    "knowledge_intelligence",        # Knowledge/Graph  ('graph'? no) -> Insights? 'knowledge' has no graph kw -> Insights
    "research_memory_intelligence",  # Knowledge/Memory
    "research_memory_system",        # Knowledge/Memory
    "research_literature",           # Knowledge/Insights
    "agent_runtime",                 # Agents/Tasks
    "research_agent_coordination",   # Agents/Tasks
    "agent_history",                 # Agents/History ('history')
    "research_evolution",            # Research/Alpha (categorized Research via 'evolution')
    "research_observability",        # System/Monitoring
    "diagnostics",                   # System/Monitoring
    "access_governance",             # System/Configuration
    "security_audit",                # System/Configuration
    "execution_cost",                # System/Configuration (execution -> System, default Configuration)
    "zzz_unknown",                   # System/Configuration (other -> System default)
]


@pytest.fixture()
def eng():
    return NavigationEngine(modules=SYNTH)


@pytest.fixture()
def real():
    return NavigationEngine()


# ──────────────────────── 섹션 매핑 ────────────────────────
@pytest.mark.parametrize("name,section", [
    ("research_strategy_generation", M.SEC_RESEARCH),
    ("alpha_intelligence", M.SEC_RESEARCH),
    ("simulation_environment", M.SEC_RESEARCH),
    ("experiment_tracking", M.SEC_RESEARCH),
    ("research_kg", M.SEC_KNOWLEDGE),
    ("research_memory_system", M.SEC_KNOWLEDGE),
    ("knowledge_intelligence", M.SEC_KNOWLEDGE),
    ("agent_runtime", M.SEC_AGENTS),
    ("research_agent_coordination", M.SEC_AGENTS),
    ("research_observability", M.SEC_SYSTEM),
    ("diagnostics", M.SEC_SYSTEM),
    ("access_governance", M.SEC_SYSTEM),
    ("execution_cost", M.SEC_SYSTEM),
    ("zzz_unknown", M.SEC_SYSTEM),
])
def test_section_for(name, section):
    assert M.section_for(name) == section


# ──────────────────────── 항목 매핑 ────────────────────────
@pytest.mark.parametrize("name,section,item", [
    ("research_strategy_generation", M.SEC_RESEARCH, "Alpha"),
    ("alpha_intelligence", M.SEC_RESEARCH, "Alpha"),
    ("experiment_tracking", M.SEC_RESEARCH, "Experiments"),
    ("experiment_orchestration", M.SEC_RESEARCH, "Experiments"),
    ("simulation_environment", M.SEC_RESEARCH, "Simulation"),
    ("paper", M.SEC_RESEARCH, "Simulation"),
    ("research_kg", M.SEC_KNOWLEDGE, "Graph"),
    ("research_memory_intelligence", M.SEC_KNOWLEDGE, "Memory"),
    ("research_memory_system", M.SEC_KNOWLEDGE, "Memory"),
    ("research_literature", M.SEC_KNOWLEDGE, "Insights"),
    ("knowledge_intelligence", M.SEC_KNOWLEDGE, "Insights"),
    ("agent_runtime", M.SEC_AGENTS, "Tasks"),
    ("research_agent_coordination", M.SEC_AGENTS, "Tasks"),
    ("agent_history", M.SEC_AGENTS, "History"),
    ("research_evolution", M.SEC_RESEARCH, "Alpha"),
    ("research_observability", M.SEC_SYSTEM, "Monitoring"),
    ("diagnostics", M.SEC_SYSTEM, "Monitoring"),
    ("access_governance", M.SEC_SYSTEM, "Configuration"),
    ("execution_cost", M.SEC_SYSTEM, "Configuration"),
    ("zzz_unknown", M.SEC_SYSTEM, "Configuration"),
])
def test_item_for(name, section, item):
    assert M.item_for(name) == (section, item)


def test_item_for_deterministic():
    assert M.item_for("research_kg") == M.item_for("research_kg")


# ──────────────────────── 구조 상수 ────────────────────────
def test_sections_count():
    assert len(M.SECTIONS) == 4


def test_nav_items_structure():
    assert M.NAV_ITEMS[M.SEC_RESEARCH] == ("Alpha", "Simulation", "Experiments")
    assert M.NAV_ITEMS[M.SEC_KNOWLEDGE] == ("Graph", "Memory", "Insights")
    assert M.NAV_ITEMS[M.SEC_AGENTS] == ("Tasks", "History")
    assert M.NAV_ITEMS[M.SEC_SYSTEM] == ("Monitoring", "Configuration")


def test_all_sections_have_items():
    for s in M.SECTIONS:
        assert len(M.NAV_ITEMS[s]) >= 2


def test_total_item_count():
    assert sum(len(v) for v in M.NAV_ITEMS.values()) == 10


# ──────────────────────── 엔진 매핑 ────────────────────────
def test_modules_sorted(eng):
    assert eng.modules() == sorted(SYNTH)


def test_assign_covers_all(eng):
    placed = {m for v in eng.assign().values() for m in v}
    assert placed == set(SYNTH)


def test_nav_items_all_present(eng):
    items = eng.nav_items()
    keys = {(i.section, i.item) for i in items}
    expected = {(s, it) for s in M.SECTIONS for it in M.NAV_ITEMS[s]}
    assert keys == expected


def test_nav_item_alpha(eng):
    alpha = next(i for i in eng.nav_items() if (i.section, i.item) == (M.SEC_RESEARCH, "Alpha"))
    assert "alpha_intelligence" in alpha.modules
    assert "research_strategy_generation" in alpha.modules


def test_nav_item_memory(eng):
    mem = next(i for i in eng.nav_items() if (i.section, i.item) == (M.SEC_KNOWLEDGE, "Memory"))
    assert set(mem.modules) == {"research_memory_intelligence", "research_memory_system"}


def test_nav_sections(eng):
    secs = eng.nav_sections()
    assert len(secs) == 4
    research = next(s for s in secs if s.section == M.SEC_RESEARCH)
    assert research.item_count == 3
    assert research.module_count >= 6


def test_section_module_count_sums(eng):
    for s in eng.nav_sections():
        assert s.module_count == sum(i["module_count"] for i in s.items)


def test_tree_structure(eng):
    t = eng.tree()
    assert "Home" in t
    assert set(t["Home"].keys()) == set(M.SECTIONS)
    assert "Alpha" in t["Home"][M.SEC_RESEARCH]


def test_tree_leaves_are_modules(eng):
    t = eng.tree()
    assert "research_memory_system" in t["Home"][M.SEC_KNOWLEDGE]["Memory"]


# ──────────────────────── 커버리지·중복 ────────────────────────
def test_coverage_full(eng):
    assert eng.coverage() == 1.0


def test_unplaced_empty(eng):
    assert eng.unplaced() == []


def test_coverage_empty_modules():
    assert NavigationEngine(modules=[]).coverage() == 1.0


def test_duplicate_pages(eng):
    dups = eng.duplicate_pages()
    # research_memory_intelligence + research_memory_system share family research_memory in Memory
    fams = {(d.section, d.item, d.family) for d in dups}
    assert (M.SEC_KNOWLEDGE, "Memory", "research_memory") in fams


def test_duplicate_pages_members_sorted(eng):
    for d in eng.duplicate_pages():
        assert d.members == sorted(d.members)


def test_no_false_duplicate_single(eng):
    # Alpha has research_strategy_generation(family research_strategy) + alpha_intelligence
    # (family alpha) — different families, no dup for those
    dups = eng.duplicate_pages()
    assert not any(d.family == "alpha" for d in dups)


# ──────────────────────── 패널 통합 ────────────────────────
def test_panel_mapping(eng):
    pm = eng.panel_mapping()
    assert pm["STATISTICS"] == M.SEC_RESEARCH
    assert pm["KNOWLEDGE_SUMMARY"] == M.SEC_KNOWLEDGE
    assert pm["MONITORING"] == M.SEC_SYSTEM
    assert pm["HEALTH"] == M.SEC_SYSTEM


def test_panel_mapping_covers_known_panels(eng):
    pm = eng.panel_mapping()
    for p in ("STATISTICS", "TIMELINE", "HEALTH", "KNOWLEDGE_SUMMARY", "RESEARCH_PROGRESS",
              "MONITORING"):
        assert p in pm


# ──────────────────────── 매니페스트 ────────────────────────
def test_build_manifest(eng):
    man = eng.build_manifest("2026-01-01T00:00:00Z")
    assert man.section_count == 4
    assert man.item_count == 10
    assert man.module_count == len(SYNTH)
    assert man.coverage == 1.0
    assert man.digest.startswith("sha256:")


def test_manifest_deterministic(eng):
    assert eng.build_manifest("t").digest == eng.build_manifest("t").digest
    assert eng.build_manifest("t").to_dict() == eng.build_manifest("t").to_dict()


def test_summary(eng):
    s = eng.summary()
    assert s["section_count"] == 4
    assert s["item_count"] == 10
    assert "digest" in s


# ──────────────────────── 문서 렌더 ────────────────────────
def test_render_docs(eng, tmp_path):
    out = tmp_path / "nav"
    written = eng.render_docs(str(out))
    assert len(written) == 2
    assert (out / "navigation.md").exists()
    assert (out / "navigation_manifest.json").exists()


def test_render_docs_content(eng, tmp_path):
    out = tmp_path / "nav"
    eng.render_docs(str(out))
    md = (out / "navigation.md").read_text(encoding="utf-8")
    assert "Home" in md
    assert "Research" in md and "Knowledge" in md and "Agents" in md and "System" in md


def test_render_manifest_json_valid(eng, tmp_path):
    out = tmp_path / "nav"
    eng.render_docs(str(out))
    data = json.loads((out / "navigation_manifest.json").read_text(encoding="utf-8"))
    assert data["section_count"] == 4


def test_render_idempotent(eng, tmp_path):
    out = tmp_path / "nav"
    eng.render_docs(str(out))
    c1 = (out / "navigation.md").read_text(encoding="utf-8")
    eng.render_docs(str(out))
    c2 = (out / "navigation.md").read_text(encoding="utf-8")
    assert c1 == c2


# ──────────────────────── 실제 트리 ────────────────────────
def test_real_module_count(real):
    assert len(real.modules()) >= 100


def test_real_coverage_full(real):
    # 모든 모듈은 default 로라도 배치 → 커버리지 100%
    assert real.coverage() == 1.0
    assert real.unplaced() == []


def test_real_all_sections_populated(real):
    for s in real.nav_sections():
        assert s.module_count > 0


def test_real_research_section_large(real):
    research = next(s for s in real.nav_sections() if s.section == M.SEC_RESEARCH)
    assert research.module_count >= 10


def test_real_manifest_deterministic(real):
    assert real.build_manifest("t").digest == real.build_manifest("t").digest


def test_real_new_packages_placed(real):
    tree = real.tree()
    allmods = [m for sec in tree["Home"].values() for item in sec.values() for m in item]
    assert "agent_runtime" in allmods
    assert "local_runtime" in allmods
    assert "integration_audit" in allmods


def test_real_duplicate_pages_found(real):
    # 실제 트리에는 research_memory_* 등 동일 계열이 같은 항목에 모임
    assert len(real.duplicate_pages()) >= 1


def test_real_every_module_valid_section(real):
    for name in real.modules():
        assert M.section_for(name) in M.SECTIONS


def test_real_every_module_valid_item(real):
    for name in real.modules():
        sec, item = M.item_for(name)
        assert sec in M.SECTIONS
        assert item in M.NAV_ITEMS[sec]


def test_real_item_modules_sorted(real):
    for i in real.nav_items():
        assert i.modules == sorted(i.modules)


def test_real_tree_json_serializable(real):
    json.dumps(real.tree())


def test_real_section_module_counts_sum_to_total(real):
    total = sum(s.module_count for s in real.nav_sections())
    assert total == len(real.modules())


def test_nav_item_to_dict_roundtrip(eng):
    i = eng.nav_items()[0]
    assert i.to_dict()["section"] == i.section


def test_manifest_to_dict(eng):
    man = eng.build_manifest("t")
    d = man.to_dict()
    assert d["item_count"] == 10
    assert isinstance(d["sections"], list)


# ──────────────────────── 안전 스캔 ────────────────────────
_SRC_FILES = [str(SRC / f) for f in ("engine.py", "models.py", "__main__.py", "__init__.py")]
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
           "decide", "make_decision")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC_FILES)
def test_no_model_id_leak(path):
    assert MODEL_LEAK_TOKEN not in open(path).read().lower()


def test_engine_no_execution_methods(eng):
    for m in ("execute", "trade", "deploy", "allocate", "approve", "decide"):
        assert not hasattr(eng, m)


@pytest.mark.parametrize("verb", ["EXECUTE", "DEPLOY", "TRADE", "ALLOCATE", "APPROVE", "DECIDE",
                                  "APPROVE_FOR_TRADING"])
def test_forbidden_verbs(verb):
    assert M.is_forbidden_verb(verb)


def test_not_forbidden_verbs():
    for v in ("navigate", "categorize", "render", "map"):
        assert not M.is_forbidden_verb(v)


# ──────────────────────── CLI ────────────────────────
def _cli(argv, capsys):
    from jarvis.research_navigation import __main__ as cli
    rc = cli.main(argv)
    return rc, capsys.readouterr().out


def test_cli_tree(capsys):
    rc, out = _cli(["tree"], capsys)
    assert rc == 0
    assert "Home" in out


def test_cli_sections(capsys):
    rc, out = _cli(["sections"], capsys)
    assert rc == 0
    assert "Research" in out


def test_cli_duplicates(capsys):
    rc, out = _cli(["duplicates"], capsys)
    assert rc == 0


def test_cli_panels(capsys):
    rc, out = _cli(["panels"], capsys)
    assert rc == 0
    assert "STATISTICS" in out


def test_cli_coverage(capsys):
    rc, out = _cli(["coverage"], capsys)
    assert rc == 0
    assert "coverage" in out


def test_cli_summary(capsys):
    rc, out = _cli(["summary"], capsys)
    assert rc == 0
    assert "digest" in out


def test_cli_render(tmp_path, capsys):
    rc, out = _cli(["render", "--out", str(tmp_path / "nav")], capsys)
    assert rc == 0
    assert "written" in out
