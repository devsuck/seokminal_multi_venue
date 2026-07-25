"""P75 Critic + P76 Prioritizer + P72 Autonomous Loop 테스트 — 비판·순위·루프·감사·재현·안전."""
from __future__ import annotations

import ast
import pathlib

import pytest

from jarvis.research_assistant import ledger as al
from jarvis.research_assistant.engine import ResearchAssistantEngine
from jarvis.research_memory_intelligence import ledger as ml
from jarvis.research_workflow import ledger as wl
from jarvis.research_workflow.autonomous_loop import AutonomousResearchLoop, LoopCancelledError
from jarvis.research_workflow.research_critic import BLOCK, PASS, ResearchCritic
from jarvis.research_workflow.research_prioritizer import ResearchPrioritizer
from jarvis.research_workflow.verify import verify_chain

NOW = "2026-01-01T00:00:00Z"
SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"

DATA = {"experiments": [{"name": "momentum study"}, {"name": "insider signal"}],
        "experiment_runs": [{"note": "insider edge"}],
        "failures": [{"reason": "momentum regime"}]}
_GOOD = {"return": 0.14, "sharpe": 0.9, "max_drawdown": -0.18, "volatility": 0.13,
         "walk_forward": 0.8, "out_of_sample": 0.7, "cost_impact": 0.1,
         "parameter_stability": 0.8, "random_baseline": 0.2}
_BAD = {"sharpe": 0.9, "out_of_sample": 0.2, "cost_impact": 0.4, "parameter_stability": 0.2,
        "walk_forward": 0.3}


@pytest.fixture()
def asst():
    return ResearchAssistantEngine(reader=lambda n: DATA.get(n, []))


@pytest.fixture()
def loopenv(tmp_path, monkeypatch):
    state = tmp_path / "_state"
    state.mkdir()
    sp = lambda n: str(state / n)  # noqa: E731
    monkeypatch.setattr(wl, "state_path", sp)
    monkeypatch.setattr(ml, "state_path", sp)
    monkeypatch.setattr(al, "state_path", sp)
    return AutonomousResearchLoop(assistant=ResearchAssistantEngine(reader=lambda n: DATA.get(n, [])))


# ── P75 Critic ──
def _spec(**over):
    s = {"strategy_name": "momentum", "universe": "GLOBAL_FUT", "rebalance": "monthly",
         "feature_set": ["ret_12m", "vol_20d"], "labels": "forward_return_20d"}
    s.update(over)
    return s


def test_critic_covers_8_dimensions():
    rep = ResearchCritic().critique(_spec(), metrics=_GOOD)
    dims = {c.dimension for c in rep.critiques}
    assert dims == {"look_ahead", "survivorship", "data_leakage", "overfitting",
                    "parameter_instability", "regime_dependence", "liquidity", "cost_sensitivity"}


def test_critic_blocks_weak_research():
    rep = ResearchCritic().critique(_spec(), metrics=_BAD)
    assert rep.verdict == BLOCK
    assert rep.blocks is True
    assert "overfitting" in rep.blocking_dimensions
    assert "cost_sensitivity" in rep.blocking_dimensions


def test_critic_lookahead_block_on_future_feature():
    rep = ResearchCritic().critique(_spec(feature_set=["forward_return_5d", "vol"]), metrics=_GOOD)
    la = next(c for c in rep.critiques if c.dimension == "look_ahead")
    assert la.severity == BLOCK


def test_critic_no_auto_acceptance():
    rep = ResearchCritic().critique(_spec(point_in_time=True), metrics=_GOOD)
    assert rep.requires_human_review is True     # PASS 여도 사람 검토
    assert rep.is_decision is False


def test_critic_deterministic():
    a = ResearchCritic().critique(_spec(), metrics=_BAD).to_dict()
    b = ResearchCritic().critique(_spec(), metrics=_BAD).to_dict()
    assert a == b


# ── P76 Prioritizer ──
def _cands():
    return [{"hypothesis_id": "h1", "statement": "Novel supply chain edge", "source": "supply_chain",
             "confidence": "MEDIUM", "expected_edge": "HIGH"},
            {"hypothesis_id": "h2", "statement": "momentum study revisit", "source": "queue:FAILURE_FIX",
             "confidence": "LOW", "expected_edge": "LOW"}]


def test_prioritizer_ranks(asst):
    rq = ResearchPrioritizer(assistant=asst).prioritize(_cands())
    assert rq.count == 2
    assert rq.items[0].rank == 1
    assert set(rq.items[0].scores) >= {"novelty", "expected_information_gain", "implementation_cost",
                                       "portfolio_impact", "historical_relevance", "confidence", "uncertainty"}


def test_prioritizer_consistent(asst):
    a = ResearchPrioritizer(assistant=asst).prioritize(_cands()).to_dict()
    b = ResearchPrioritizer(assistant=asst).prioritize(_cands()).to_dict()
    assert [i["hypothesis_id"] for i in a["items"]] == [i["hypothesis_id"] for i in b["items"]]
    assert a["recommended"] == b["recommended"]


def test_prioritizer_recommend_next(asst):
    nxt = ResearchPrioritizer(assistant=asst).recommend_next(_cands())
    assert nxt["rank"] == 1


def test_prioritizer_advisory(asst):
    rq = ResearchPrioritizer(assistant=asst).prioritize(_cands())
    assert rq.is_advisory is True and rq.is_decision is False


# ── P72 Autonomous Loop ──
def _bt():
    return {"strategy_name": "momentum", "metrics": dict(_GOOD)}


def test_loop_blocks_on_backtest(loopenv):
    st = loopenv.run("research momentum", {"topic": "momentum"}, now=NOW, commit=True)
    assert st.blocked_stage == "BACKTEST"           # 외부 입력 대기(사람 체크포인트)
    assert "HYPOTHESIS" in st.completed_stages


def test_loop_full_pipeline(loopenv):
    st = loopenv.run("research momentum", {"topic": "momentum", "backtest": _bt()}, now=NOW, commit=True)
    assert st.completed_stages == list(__import__("jarvis.research_workflow.models",
                                                  fromlist=["LOOP_STAGES"]).LOOP_STAGES)
    assert st.requires_human_checkpoint is True
    assert "hypothesis" in st.artifacts and "spec" in st.artifacts and "next" in st.artifacts


def test_loop_deterministic(loopenv):
    a = loopenv.run("idea alpha", {"topic": "momentum", "backtest": _bt()}, commit=False).to_dict()
    b = loopenv.run("idea alpha", {"topic": "momentum", "backtest": _bt()}, commit=False).to_dict()
    assert a["completed_stages"] == b["completed_stages"]
    assert a["artifacts"]["spec"]["spec_hash"] == b["artifacts"]["spec"]["spec_hash"]


def test_loop_resume_after_backtest(loopenv):
    st = loopenv.run("research momentum", {"topic": "momentum"}, now=NOW, commit=True)
    lid = st.loop_id
    assert st.blocked_stage == "BACKTEST"
    st2 = loopenv.resume(lid, "research momentum", {"topic": "momentum", "backtest": _bt()},
                         now=NOW, commit=True)
    assert "NEXT_EXPERIMENT" in st2.completed_stages


def test_loop_lesson_persisted(loopenv):
    loopenv.run("research momentum", {"topic": "momentum", "backtest": _bt()}, now=NOW, commit=True)
    assert any("AUTONOMOUS LESSON" in str(x.get("lesson", "")) for x in ml.read_lessons())


def test_loop_audit_trail_hash_chain(loopenv):
    loopenv.run("research momentum", {"topic": "momentum", "backtest": _bt()}, now=NOW, commit=True)
    assert verify_chain()["ok"]                     # rwf_ 해시체인 무결


def test_loop_pause_cancel(loopenv):
    st = loopenv.run("research momentum", {"topic": "momentum"}, now=NOW, commit=True)
    p = loopenv.pause(st.loop_id, now=NOW, commit=True)
    assert p.paused is True
    c = loopenv.cancel(st.loop_id, "stop", now=NOW, commit=True)
    assert c.cancelled is True
    with pytest.raises(LoopCancelledError):
        loopenv.resume(st.loop_id, "research momentum", {"backtest": _bt()}, now=NOW, commit=True)


def test_loop_dry_run_no_ledger_write(loopenv):
    loopenv.run("research momentum", {"topic": "momentum", "backtest": _bt()}, commit=False)
    assert wl.read_loops() == []


# ── 안전 ──
def test_no_forbidden_imports_defs_leak():
    for f in ("research_critic.py", "research_prioritizer.py", "autonomous_loop.py"):
        src = open(SRC / f).read()
        assert MODEL_LEAK_TOKEN not in src.lower()
        tree = ast.parse(src)
        bad_imp = ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
                   "jarvis.live_trading", "jarvis.portfolio_execution")
        bad_def = ("execute", "trade", "deploy", "allocate", "approve", "place_order")
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not any(node.module.startswith(b) for b in bad_imp), (f, node.module)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.name not in bad_def, (f, node.name)
