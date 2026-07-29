"""P204 Research Discovery Facade + Call Graph Golden 테스트.

핵심: 단일 파사드(generate/expand/criticize/rank) · 내부 모듈 유지(deprecated, 삭제 아님) ·
meaning==meaning(golden) + call structure==call structure(call graph golden) 둘 다 보존 · 새 원장 없음.
"""
from __future__ import annotations

import ast
import json
import pathlib

from jarvis.research_workflow import characterization as ch
from jarvis.research_workflow import ledger as wl
from jarvis.research_workflow import research_discovery as rd

SRC = pathlib.Path(__file__).resolve().parent.parent
GOLDEN_DIR = pathlib.Path(__file__).resolve().parent / "golden"
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"


# ── 파사드 4단계(발견→확장→비판→선택) ──
def test_facade_generate_rank():
    g = rd.generate("momentum KR", limit=5)
    assert g["stage"] == "generate" and g["count"] >= 1 and g["is_decision"] is False
    r = rd.rank(g["hypotheses"], limit=5)
    assert r["stage"] == "rank" and r.get("research_queue") is not None


def test_facade_expand_and_criticize():
    h = rd.generate("momentum", limit=3)["hypotheses"][0]
    e = rd.expand(h, top_k=6)
    assert e["stage"] == "expand" and e["is_decision"] is False
    c = rd.criticize(h)
    assert c["stage"] == "criticize" and c["verdict"] in ("PASS", "WARN", "BLOCK")


def test_facade_generate_modes():
    for mode in ("recall_first", "creative", "template"):
        g = rd.generate("momentum", limit=3, mode=mode)
        assert g["mode"] == mode and g["is_decision"] is False


def test_facade_discover_full_flow():
    d = rd.discover("momentum KR", limit=5)
    assert "research_queue" in d and d["is_decision"] is False


# ── Call Graph Golden: 호출 구조 보존 (파사드는 조율만, 재구현 아님) ──
def test_call_graph_matches_golden():
    golden = json.loads((GOLDEN_DIR / "call_graph.json").read_text(encoding="utf-8"))
    cmp = ch.compare_call_graph(golden)
    assert cmp["call_graph_identical"] is True, cmp["diffs"]


def test_facade_composes_not_reimplements():
    # research_discovery 는 내부 가설 모듈들을 '참조'해야 함(조율 증거)
    cg = ch.build_call_graph()["graph"]
    refs = set(cg["research_discovery"])
    assert {"hypothesis_discovery", "creative_hypothesis", "research_search",
            "research_critic", "research_priority"} <= refs


def test_call_graph_deterministic():
    a = ch.build_call_graph()
    b = ch.build_call_graph()
    assert a["graph_hash"] == b["graph_hash"]


# ── 내부 모듈 유지(deprecated, 삭제 아님) ──
def test_internal_modules_still_importable():
    from jarvis.research_workflow.hypothesis_discovery import discover_research
    from jarvis.research_workflow.creative_hypothesis import discover_hypotheses
    from jarvis.research_workflow.research_search import build_search_space
    assert discover_research("m", limit=2)["is_decision"] is False
    assert discover_hypotheses("m", limit=2)["is_decision"] is False
    assert build_search_space("m", top_k=3)["is_decision"] is False


# ── meaning == meaning 도 여전히 보존 ──
def test_meaning_still_preserved():
    golden = json.loads((GOLDEN_DIR / "research_meaning.json").read_text(encoding="utf-8"))
    assert ch.compare_to_golden(golden)["meaning_preserved"] is True


# ── 새 원장 없음 + 금지 스캔 ──
def test_no_new_ledger():
    assert len(wl.ALL_LEDGERS) == 3


def test_no_forbidden_defs_imports_leak():
    src = open(SRC / "research_discovery.py").read()
    assert MODEL_LEAK_TOKEN not in src.lower()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(b) for b in
                           ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
                            "jarvis.live_trading", "jarvis.portfolio_execution")), node.module
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in ("execute", "trade", "deploy", "allocate", "approve",
                                     "place_order", "deploy_strategy"), node.name
