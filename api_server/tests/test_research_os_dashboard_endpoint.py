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


# ── P101-110 Research Validation Loop ──
def test_research_trigger_endpoint_not_signal():
    from api_server.console_api import research_trigger_endpoint
    t = research_trigger_endpoint(q="TSMC supply disruption", entity="TSMC", kind="supply")
    assert t["trigger"].get("trigger_type")
    assert t.get("is_trade_signal") is False


def test_strategy_lifecycle_endpoint_shape():
    from api_server.console_api import strategy_lifecycle_endpoint
    b = strategy_lifecycle_endpoint()
    assert "strategies" in b and "lifecycle" in b


def test_ops_events_endpoint_types():
    from api_server.console_api import research_ops_events_endpoint
    ev = research_ops_events_endpoint()
    assert len(ev["event_types"]) == 5


def test_v2_release_endpoint_ready():
    from api_server.console_api import v2_release_endpoint
    r = v2_release_endpoint()
    assert r["loop_complete"] is True and r["safety"]["safe"] is True


def test_validation_loop_shape():
    from api_server.console_api import validation_loop
    vl = validation_loop()
    assert set(vl) >= {"lifecycle_board", "validation_panel", "quality_panel", "review_queue",
                       "ops_events", "loop_status"}
    assert vl["validation_panel"]["status"] == "BACKTEST_SUCCESS_PAPER_FAILURE"
    assert vl["is_decision"] is False


# ── P111-120 Live Data Infrastructure ──
def test_data_capability_map_endpoint():
    from api_server.console_api import data_capability_map
    r = data_capability_map()
    assert r["count"] >= 15 and "providers" in r
    assert set(r["interface"]) == {"fetch", "normalize", "validate", "health_check"}


def test_data_health_endpoint():
    from api_server.console_api import data_health
    assert data_health()["overall_status"] in ("HEALTHY", "DEGRADED", "LIMITED")


def test_research_feed_endpoint():
    from api_server.console_api import research_feed
    r = research_feed()
    assert "collected" in r and "opportunity_queue" in r


def test_live_intelligence_endpoint():
    from api_server.console_api import live_intelligence
    x = live_intelligence()
    assert set(x) >= {"data_sources", "market_feed", "research_queue", "data_health"}


def test_operational_validation_endpoint():
    from api_server.console_api import operational_validation
    r = operational_validation()
    assert r["operational"] is True and r["architecture_safety"]["safe"] is True


def test_cockpit_has_data_health():
    from api_server.console_api import cockpit
    assert "data_health" in cockpit()


# ── P121-130 Research Agent OS ──
def test_agent_capability_map_endpoint():
    from api_server.console_api import agent_capability_map_endpoint
    c = agent_capability_map_endpoint()
    assert c["count"] == 6 and c["role_hierarchy"] == ["director", "specialist", "critic", "report"]


def test_agent_validation_endpoint():
    from api_server.console_api import agent_validation_endpoint
    v = agent_validation_endpoint()
    assert v["validated"] is True and v["safety"]["safe"] is True


def test_agent_workspace_endpoint():
    from api_server.console_api import agent_workspace
    w = agent_workspace()
    assert set(w) >= {"agents", "active_research", "agent_status", "current_tasks",
                      "generated_reports", "critic_feedback", "human_review_queue"}
    assert w["active_research"]["pipeline"] == ["Director", "Analyst", "StrategyResearcher",
                                                "Critic", "Writer"]
    assert w["is_decision"] is False


# ── P131-140 Research Knowledge Intelligence ──
def test_memory_audit_endpoint():
    from api_server.console_api import memory_audit_endpoint
    a = memory_audit_endpoint()
    assert len(a["entity_types"]) == 7 and a["memory_stores"]


def test_knowledge_graph_endpoint():
    from api_server.console_api import knowledge_graph_endpoint
    g = knowledge_graph_endpoint()
    assert len(g["research_chain"]) == 6


def test_semantic_recall_endpoint():
    from api_server.console_api import semantic_recall_endpoint
    p = semantic_recall_endpoint("Does momentum work?")
    assert "relevant_experiments" in p and "similar_failures" in p


def test_knowledge_health_endpoint():
    from api_server.console_api import knowledge_health_endpoint
    assert knowledge_health_endpoint()["grade"] in ("HEALTHY", "FAIR", "DEGRADED", "EMPTY")


def test_brain_validation_endpoint():
    from api_server.console_api import brain_validation_endpoint
    v = brain_validation_endpoint()
    assert v["validated"] is True and v["safety"]["safe"] is True


def test_research_brain_endpoint():
    from api_server.console_api import research_brain
    rb = research_brain()
    assert set(rb) >= {"knowledge_graph", "past_research", "failure_patterns", "strategy_memory",
                       "company_memory", "conflicts", "lessons", "knowledge_health"}
    assert rb["is_decision"] is False
