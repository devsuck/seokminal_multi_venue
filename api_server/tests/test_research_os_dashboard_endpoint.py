"""Research OS Dashboard 엔드포인트(P68-71) 테스트 — 조율 표면, READ ONLY(세션관리 제외). HTTP 없이 함수 호출."""
from __future__ import annotations


def test_research_workflow_shape():
    from api_server.console_api import research_workflow
    r = research_workflow()
    assert set(r) >= {"stages", "runs", "sessions", "queue", "counts", "disclaimer"}
    assert r["is_decision"] is False and r["is_advisory"] is True
    assert len(r["stages"]) == 12          # 파이프라인 12단계
    assert isinstance(r["runs"], list) and isinstance(r["sessions"], list)


def test_decision_memo_sections():
    from api_server.console_api import decision_memo
    d = decision_memo("momentum")
    for s in ("question", "supporting_arguments", "counter_arguments", "historical_similar_cases",
              "risk_summary", "confidence", "remaining_unknowns", "suggested_next_research",
              "requires_human_review"):
        assert s in d, s
    assert d["is_decision"] is False


def test_decision_memo_empty_topic():
    from api_server.console_api import decision_memo
    assert decision_memo("")["is_decision"] is False


def test_explainability_chain():
    from api_server.console_api import explainability
    e = explainability("momentum")
    stages = [n["stage"] for n in e["chain"]]
    assert stages[0] == "Experiment" and stages[-1] == "Final Recommendation"
    assert len(e["edges"]) == len(stages) - 1
    assert "confidence_breakdown" in e and "why_it_may_be_wrong" in e


def test_operating_console_sections():
    from api_server.console_api import operating_console
    o = operating_console()
    assert set(o) >= {"research", "opportunities", "risks", "events", "paper", "exposure",
                      "sessions", "recommendations", "date"}
    assert o["is_decision"] is False


def test_operating_console_read_only():
    from api_server.console_api import operating_console
    assert operating_console()["is_advisory"] is True


# ── 세션 관리(유일한 변경 작업) — rwf_sessions 만, 격리 상태에서 테스트 ──
def test_session_action_lifecycle(tmp_path, monkeypatch):
    from jarvis.research_workflow import ledger as wl
    monkeypatch.setattr(wl, "state_path", lambda n: str(tmp_path / n))
    from api_server.console_api import session_action
    created = session_action("create", goal="momentum research")
    sid = created["session_id"]
    assert created["state"] == "ACTIVE"
    assert session_action("pause", session_id=sid)["state"] == "PAUSED"
    assert session_action("resume", session_id=sid)["state"] == "ACTIVE"
    assert session_action("archive", session_id=sid)["state"] == "ARCHIVED"


def test_session_action_unknown(tmp_path, monkeypatch):
    from jarvis.research_workflow import ledger as wl
    monkeypatch.setattr(wl, "state_path", lambda n: str(tmp_path / n))
    from api_server.console_api import session_action
    assert "error" in session_action("bogus", session_id="x")


def test_session_action_requires_id(tmp_path, monkeypatch):
    from jarvis.research_workflow import ledger as wl
    monkeypatch.setattr(wl, "state_path", lambda n: str(tmp_path / n))
    from api_server.console_api import session_action
    assert "error" in session_action("pause")


def test_autonomous_runtime_shape():
    from api_server.console_api import autonomous_runtime
    r = autonomous_runtime("momentum")
    assert set(r) >= {"topic", "loop_stages", "preview", "loops", "counts", "disclaimer"}
    assert len(r["loop_stages"]) == 9
    assert r["is_decision"] is False


def test_autonomous_runtime_preview():
    from api_server.console_api import autonomous_runtime
    p = autonomous_runtime("momentum")["preview"]
    assert "hypotheses" in p and "critique" in p and "recommended_spec" in p


def test_autonomous_runtime_empty_topic():
    from api_server.console_api import autonomous_runtime
    assert autonomous_runtime("")["preview"] == {}


# ── Research OS Completion (P78-85) ──
def test_research_timeline_shape():
    from api_server.console_api import research_timeline
    r = research_timeline()
    assert set(r) >= {"entries", "count", "stage_order"}
    assert r["is_decision"] is False


def test_research_graph_shape():
    from api_server.console_api import research_graph
    g = research_graph()
    assert set(g) >= {"nodes", "edges", "node_count", "edge_count", "relationship_kinds"}


def test_research_health_shape():
    from api_server.console_api import research_health
    h = research_health()
    assert 0 <= h["overall_health_score"] <= 100
    assert "coverage" in h


def test_cockpit_shape():
    from api_server.console_api import cockpit
    c = cockpit()
    assert set(c) >= {"research", "current_loop", "top_opportunities", "highest_risks",
                      "research_health", "timeline", "knowledge_graph", "human_review_queue"}
    assert c["is_decision"] is False


def test_research_quality_and_cross():
    from api_server.console_api import cross_strategy, research_quality
    assert "note" in research_quality("") or "overall_quality" in research_quality("")
    assert "pairs" in cross_strategy()


def test_continuous_learning_shape():
    from api_server.console_api import continuous_learning
    assert "channels" in continuous_learning()


# ── Market Intelligence (P86-95) ──
def test_market_regime_shape():
    from api_server.console_api import market_regime
    r = market_regime()
    assert "regime" in r and r.get("is_decision", False) is False


def test_opportunity_queue_shape():
    from api_server.console_api import opportunity_queue
    assert "opportunities" in opportunity_queue()


def test_alt_data_catalog():
    from api_server.console_api import alt_data
    assert alt_data()["count"] == 7


def test_council_expanded_seven():
    from api_server.console_api import council_expanded
    c = council_expanded("momentum")
    assert len(c["expanded_perspectives"]) == 7


def test_market_cockpit_shape():
    from api_server.console_api import market_cockpit
    c = market_cockpit()
    assert set(c) >= {"market_state", "research_opportunities", "active_experiments",
                      "validation_status", "risk", "portfolio_context", "decision_queue", "knowledge_growth"}
    assert c["is_decision"] is False


# ── Live Market Intelligence (P96-100) ──
def test_news_intel_shape():
    from api_server.console_api import news_intel
    n = news_intel("TSMC supplier expands production", "TSMC")
    assert n["event_type"] == "SUPPLY_CHAIN_CHANGE"
    assert n.get("is_trade_signal", False) is False


def test_supply_chain_impact_shape():
    from api_server.console_api import supply_chain_impact
    r = supply_chain_impact("TSMC production issue", "TSMC")
    assert r["origin"] == "TSMC"
    assert len(r["affected_entities"]) >= 3


def test_market_intel_feed_shape():
    from api_server.console_api import market_intel_feed
    f = market_intel_feed("TSMC supplier expands", "TSMC")
    assert set(f) >= {"live_event_feed", "impact_map", "research_opportunities", "market_context", "adapters"}
    assert f["is_decision"] is False
    assert len(f["adapters"]) == 5


def test_earnings_intel_fields():
    from api_server.console_api import earnings_intel
    assert len(earnings_intel()["fields"]) == 7
