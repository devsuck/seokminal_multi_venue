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
