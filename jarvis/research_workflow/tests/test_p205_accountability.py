"""P204.5/P205/P206/P208 — Coverage Audit · Validation Score · Deprecation · Expanded Goldens.

핵심: 지표만(대시보드 없음) · graded<20 이면 숫자 미표시(PROVISIONAL) · deprecated 모듈 삭제 안 함 ·
call graph golden 확장(discovery + research workflow) · meaning==meaning 유지 · 새 원장 없음.
"""
from __future__ import annotations

import json
import pathlib

from jarvis.research_workflow import characterization as ch
from jarvis.research_workflow import governance as gv
from jarvis.research_workflow import ledger as wl
from jarvis.research_workflow import prediction_coverage_audit as pca
from jarvis.research_workflow import prediction_registry as pr
from jarvis.research_workflow import research_discovery as rd
from jarvis.research_workflow import research_validation_score as rvs

GOLDEN_DIR = pathlib.Path(__file__).resolve().parent / "golden"


# ── P204 search() 추가(5 메서드) ──
def test_facade_five_methods_exist():
    for m in ("generate", "search", "expand", "criticize", "rank"):
        assert callable(getattr(rd, m))
    h = rd.generate("momentum", limit=2)["hypotheses"][0]
    assert rd.search(h, top_k=4)["stage"] == "search"
    assert rd.expand(h, top_k=4)["stage"] == "expand"


# ── P204.5 Coverage Audit: 지표만 ──
def test_coverage_audit_metrics():
    a = pca.build_coverage_audit()
    for k in ("total_predictions", "confidence_distribution", "source_distribution",
              "missing_captures", "duplicate_predictions", "pending", "evaluated",
              "source_coverage", "ready_for_score"):
        assert k in a, k
    assert a["is_decision"] is False
    # 대시보드 없음(지표만) — note 로 명시
    assert "지표만" in a["note"]


# ── P205 Validation Score: graded<20 이면 PROVISIONAL(숫자 없음) ──
def test_validation_score_provisional_when_insufficient(monkeypatch):
    monkeypatch.setattr(pr, "graded_predictions", lambda: [])
    s = rvs.build_validation_score()
    assert s["status"] == "PROVISIONAL" and s["score"] is None
    assert s["needed"] == 20 and s["is_decision"] is False


def test_validation_score_computed_when_sufficient(monkeypatch):
    graded = ([{"confidence": "HIGH", "outcome": "RIGHT", "source": "committee"}] * 12
              + [{"confidence": "HIGH", "outcome": "WRONG", "source": "committee"}] * 4
              + [{"confidence": "MEDIUM", "outcome": "RIGHT", "source": "agent"}] * 6
              + [{"confidence": "LOW", "outcome": "INVALIDATED", "source": "agent"}] * 3)  # excluded
    monkeypatch.setattr(pr, "graded_predictions", lambda: graded)
    s = rvs.build_validation_score()
    assert s["status"] == "SCORED" and isinstance(s["score"], float)
    for c in ("accuracy", "calibration", "baseline_relative", "sample_confidence"):
        assert c in s["components"], c
    # INVALIDATED 는 scorable 에서 제외
    assert s["graded_scorable"] == 22 and s["is_investment_recommendation"] is False


def test_validation_score_never_numeric_below_threshold(monkeypatch):
    monkeypatch.setattr(pr, "graded_predictions",
                        lambda: [{"confidence": "HIGH", "outcome": "RIGHT", "source": "committee"}] * 19)
    s = rvs.build_validation_score()
    assert s["status"] == "PROVISIONAL" and s["score"] is None  # 19 < 20


# ── P206 Deprecation: 11 모듈 marked, 삭제 안 됨 ──
def test_deprecation_registry():
    dep = gv.deprecations()
    assert dep["all_marked"] is True and dep["count"] == 11
    assert dep["canonical_api"] == ["governance.validate(domain=...)", "governance.validate_all()"]


def test_deprecated_modules_still_functional():
    # deprecated 지만 살아있어야 함(삭제 아님)
    from jarvis.research_workflow.system_validation import validate_system
    from jarvis.research_workflow.agent_validation import validate_agents
    assert validate_system()["validated"] is True
    assert "validated" in validate_agents()


# ── P208 Expanded Golden: discovery + research workflow call graph ──
def test_discovery_call_graph_golden():
    golden = json.loads((GOLDEN_DIR / "call_graph.json").read_text(encoding="utf-8"))
    assert ch.compare_call_graph(golden)["call_graph_identical"] is True


def test_research_workflow_call_graph_golden():
    golden = json.loads((GOLDEN_DIR / "call_graph_research_workflow.json").read_text(encoding="utf-8"))
    cmp = ch.compare_call_graph(golden)
    assert cmp["call_graph_identical"] is True, cmp["diffs"]


def test_research_workflow_topology_captured():
    cg = ch.build_call_graph(ch.RESEARCH_WORKFLOW_MODULES)["graph"]
    # 루프 위상: loop_v3 가 cycle/gate/validation/selection 을 조율
    assert {"research_cycle", "research_gate", "validation_intelligence",
            "research_selection"} <= set(cg["research_loop_v3"])


# ── meaning == meaning 여전히 보존 ──
def test_meaning_preserved():
    golden = json.loads((GOLDEN_DIR / "research_meaning.json").read_text(encoding="utf-8"))
    assert ch.compare_to_golden(golden)["meaning_preserved"] is True


# ── 새 원장 없음 ──
def test_no_new_ledger():
    assert len(wl.ALL_LEDGERS) == 3
