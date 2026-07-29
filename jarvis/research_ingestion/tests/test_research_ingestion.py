"""Research Ingestion(P53) 테스트 — 스키마·판정·자동분류·수집·멱등·**엔드투엔드(메모리 채움)**·검증·안전.

핵심: 백테스트 수집 → research_assistant.recall/failure_intelligence 가 실제로 채워진다.
모든 관련 원장(ring_/expt_/rmi_/research_assistant)을 같은 tmp _state 로 격리.
"""
from __future__ import annotations

import ast
import json
import pathlib

import pytest

from jarvis.research_ingestion import ledger
from jarvis.research_ingestion import models as M
from jarvis.research_ingestion.engine import ResearchIngestionEngine
from jarvis.research_ingestion.verify import replay, verify_chain

NOW = "2026-01-01T00:00:00Z"
SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """수집·실험·메모리·어시스턴트 원장을 모두 같은 tmp _state 로 격리."""
    state = tmp_path / "_state"
    state.mkdir()
    sp = lambda name: str(state / name)  # noqa: E731
    from jarvis.experiment_tracking import ledger as el
    from jarvis.research_memory_intelligence import ledger as ml
    from jarvis.research_assistant import ledger as al
    monkeypatch.setattr(ledger, "state_path", sp)
    monkeypatch.setattr(el, "state_path", sp)
    monkeypatch.setattr(ml, "state_path", sp)
    monkeypatch.setattr(al, "state_path", sp)
    return ResearchIngestionEngine()


def _bt(name="momentum", **over):
    bt = {
        "strategy_name": name, "strategy_version": "v1",
        "hypothesis": "momentum works in stable regimes",
        "universe": "KOSPI200", "period": {"start": "2020-01", "end": "2023-12"},
        "features": ["ret_12m", "vol_20d"], "entry_rules": "top decile momentum",
        "exit_rules": "monthly rebalance", "risk_rules": "10% per name",
        "metrics": {"return": 0.12, "sharpe": 0.9, "max_drawdown": -0.18, "volatility": 0.14,
                    "walk_forward": 0.8, "out_of_sample": 0.7, "cost_impact": 0.1,
                    "parameter_stability": 0.8, "random_baseline": 0.2},
        "source": "backtest_runner",
    }
    bt.update(over)
    return bt


# ── 스키마 검증 ──
def test_validate_ok(env):
    v = env.validate(_bt())
    assert v["ok"] and v["validation_complete"]
    assert v["missing_validations"] == []


def test_validate_missing_name(env):
    v = env.validate(_bt(strategy_name=""))
    assert not v["ok"]
    assert "strategy_name" in v["missing_fields"]


def test_validate_missing_validations(env):
    v = env.validate(_bt(metrics={"sharpe": 0.5}))
    assert not v["validation_complete"]
    assert "walk_forward" in v["missing_validations"]


# ── 결과 판정 ──
@pytest.mark.parametrize("metrics,expected", [
    ({"sharpe": 0.9, "out_of_sample": 0.7, "max_drawdown": -0.18}, M.OUT_SUCCESS),
    ({"sharpe": 0.3, "out_of_sample": 0.1, "max_drawdown": -0.1}, M.OUT_PARTIAL),
    ({"sharpe": -0.2, "out_of_sample": -0.5, "max_drawdown": -0.4}, M.OUT_FAILURE),
    ({"sharpe": 0.9, "out_of_sample": 0.7, "max_drawdown": -0.5}, M.OUT_FAILURE),  # mdd too deep
])
def test_classify_outcome(metrics, expected):
    assert M.classify_outcome(metrics, "", True) == expected


def test_classify_outcome_incomplete_when_no_sharpe():
    assert M.classify_outcome({"return": 0.1}, "", True) == M.OUT_INCOMPLETE


def test_classify_outcome_incomplete_when_validation_missing():
    assert M.classify_outcome({"sharpe": 0.9}, "", False) == M.OUT_INCOMPLETE


def test_classify_outcome_explicit_wins():
    assert M.classify_outcome({"sharpe": 0.9}, "FAILURE", True) == M.OUT_FAILURE


# ── 실패 자동분류 ──
@pytest.mark.parametrize("metrics,cat", [
    ({"sharpe": 0.9, "out_of_sample": 0.2}, "OVERFITTING"),          # gap 0.7
    ({"sharpe": 0.1, "cost_impact": 0.4}, "COST_SENSITIVITY"),
    ({"sharpe": 0.1, "parameter_stability": 0.2}, "PARAMETER_INSTABILITY"),
    ({"sharpe": 0.1, "random_baseline": 0.2}, "POOR_HYPOTHESIS"),
    ({"sharpe": 0.1, "regime_dependent": True}, "REGIME_CHANGE"),
    ({"sharpe": 0.1}, "UNCLASSIFIED"),
])
def test_auto_classify_failure_from_metrics(metrics, cat):
    assert M.auto_classify_failure(metrics, "") == cat


def test_auto_classify_failure_from_reason():
    assert M.auto_classify_failure({}, "clear look-ahead data leakage") == "DATA_LEAKAGE"


# ── 수집(기존 원장 기록) ──
def test_ingest_writes_experiment(env):
    r = env.ingest(_bt(), NOW, commit=True)
    assert r.experiment_id.startswith("XT") or r.experiment_id
    assert r.run_id
    assert r.parameters_written >= 5
    assert r.results_written >= 9
    from jarvis.experiment_tracking import ledger as el
    assert len(el.read_experiments()) == 1
    assert len(el.read_runs()) == 1
    assert len(el.read_results()) >= 9


def test_ingest_success_writes_memory(env):
    r = env.ingest(_bt(), NOW, commit=True)
    assert r.outcome == M.OUT_SUCCESS
    assert r.memory_written == "success"
    from jarvis.research_memory_intelligence import ledger as ml
    assert len(ml.read_successes()) == 1


def test_ingest_failure_writes_failure_and_lesson(env):
    r = env.ingest(_bt(metrics={**_bt()["metrics"], "sharpe": -0.2, "out_of_sample": -0.5,
                                 "cost_impact": 0.4, "max_drawdown": -0.4}), NOW, commit=True)
    assert r.outcome == M.OUT_FAILURE
    assert r.failure_category == "COST_SENSITIVITY"
    assert r.memory_written == "failure"
    from jarvis.research_memory_intelligence import ledger as ml
    assert len(ml.read_failures()) == 1
    assert len(ml.read_lessons()) == 1


def test_ingest_incomplete(env):
    r = env.ingest(_bt(metrics={"sharpe": 0.9}), NOW, commit=True)
    assert r.outcome == M.OUT_INCOMPLETE
    assert r.validation_complete is False


def test_ingest_idempotent(env):
    a = env.ingest(_bt(), NOW, commit=True)
    b = env.ingest(_bt(), NOW, commit=True)
    assert b.deduplicated is True
    from jarvis.experiment_tracking import ledger as el
    assert len(el.read_experiments()) == 1   # 재수집해도 1건
    assert len(ledger.read_ingestions()) == 1


def test_ingest_no_commit(env):
    env.ingest(_bt(), NOW, commit=False)
    assert ledger.read_ingestions() == []


def test_ingest_many(env):
    rs = env.ingest_many([_bt("a"), _bt("b")], NOW, commit=True)
    assert len(rs) == 2
    assert len(ledger.read_ingestions()) == 2


# ── ★ 엔드투엔드: 수집 → recall/failure_intelligence 가 채워진다 ──
def test_e2e_ingest_fills_recall(env):
    env.ingest(_bt("momentum", metrics={**_bt()["metrics"], "sharpe": -0.2, "out_of_sample": -0.5,
                                        "cost_impact": 0.4, "max_drawdown": -0.4}), NOW, commit=True)
    from jarvis.research_assistant.engine import ResearchAssistantEngine
    asst = ResearchAssistantEngine()
    r = asst.recall("momentum")
    assert r.tried_before is True          # 이제 '해봤어?' 에 실답
    assert "failures" in r.sources_hit


def test_e2e_ingest_fills_failure_intelligence(env):
    env.ingest(_bt("momentum", metrics={**_bt()["metrics"], "sharpe": -0.2, "out_of_sample": -0.5,
                                        "cost_impact": 0.4, "max_drawdown": -0.4}), NOW, commit=True)
    from jarvis.research_assistant.engine import ResearchAssistantEngine
    asst = ResearchAssistantEngine()
    fi = asst.failure_intelligence()
    assert fi.total_failures >= 1
    mc = asst.mistake_check("momentum")
    assert mc["made_this_mistake"] is True   # '같은 실수 했나?' 에 실답


def test_e2e_ingest_success_recall(env):
    env.ingest(_bt("value_rotation"), NOW, commit=True)
    from jarvis.research_assistant.engine import ResearchAssistantEngine
    asst = ResearchAssistantEngine()
    r = asst.recall("value_rotation")
    assert r.tried_before is True
    assert "successes" in r.sources_hit or "experiment_runs" in r.sources_hit


def test_e2e_perspectives_populated(env):
    for i in range(3):
        env.ingest(_bt("momentum", strategy_version=f"v{i}",
                       metrics={**_bt()["metrics"], "sharpe": -0.2, "out_of_sample": -0.5,
                                "cost_impact": 0.4, "max_drawdown": -0.4}), NOW, commit=True)
    from jarvis.research_assistant.engine import ResearchAssistantEngine
    p = ResearchAssistantEngine().perspectives("momentum")
    critic = next(l for l in p["lenses"] if l["lens"] == "Critic")
    assert critic["stance"] in ("OPPOSE", "CAUTION")   # 과거 실패 → 회의론자 경고


# ── 검증·재현 ──
def test_verify_chain(env):
    env.ingest(_bt("a"), NOW, commit=True)
    env.ingest(_bt("b"), NOW, commit=True)
    res = verify_chain()
    assert res["ok"]
    assert res["n"] == 2


def test_verify_empty(env):
    assert verify_chain()["ok"]


def test_tamper_detected(env):
    env.ingest(_bt(), NOW, commit=True)
    p = pathlib.Path(ledger.state_path("ring_ingestions.jsonl"))
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    rows[0]["outcome"] = "TAMPERED"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert not verify_chain()["ok"]


def test_replay(env):
    env.ingest(_bt(), NOW, commit=True)
    assert replay(env, NOW)["deterministic"]


def test_summary(env):
    env.ingest(_bt("a"), NOW, commit=True)
    env.ingest(_bt("b", metrics={**_bt()["metrics"], "sharpe": -0.2, "cost_impact": 0.4,
                                 "out_of_sample": -0.5, "max_drawdown": -0.4}), NOW, commit=True)
    s = env.summary(NOW)
    assert s.ingestion_count == 2
    assert s.by_outcome.get("SUCCESS", 0) >= 1
    assert s.by_outcome.get("FAILURE", 0) >= 1


# ── 원장·안전 ──
def test_one_ledger():
    assert len(ledger.ALL_LEDGERS) == 1
    assert ledger.ALL_LEDGERS[0][0] == "ring_ingestions.jsonl"


def test_hash_helpers():
    assert M.backtest_hash({"a": 1}) == M.backtest_hash({"a": 1})
    assert M.ingestion_id("x", "h").startswith("RING:")


_SRC_FILES = [str(SRC / f) for f in ("engine.py", "ledger.py", "models.py", "verify.py",
                                     "__main__.py", "__init__.py")]


@pytest.mark.parametrize("path", _SRC_FILES)
def test_no_forbidden_imports(path):
    tree = ast.parse(open(path).read())
    bad = ("jarvis.execution", "jarvis.broker", "jarvis.live_execution", "jarvis.live_trading",
           "jarvis.portfolio_execution")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(b) for b in bad), node.module


@pytest.mark.parametrize("path", _SRC_FILES)
def test_no_dangerous_defs(path):
    tree = ast.parse(open(path).read())
    bad = ("execute", "trade", "deploy", "allocate", "approve", "place_order")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC_FILES)
def test_no_model_id_leak(path):
    assert MODEL_LEAK_TOKEN not in open(path).read().lower()


def test_engine_no_execution_methods(env):
    for m in ("execute", "trade", "deploy", "allocate", "approve"):
        assert not hasattr(env, m)


# ── CLI ──
def test_cli_ingest(tmp_path, monkeypatch, capsys):
    state = tmp_path / "_state"
    state.mkdir()
    sp = lambda name: str(state / name)  # noqa: E731
    from jarvis.experiment_tracking import ledger as el
    from jarvis.research_memory_intelligence import ledger as ml
    monkeypatch.setattr(ledger, "state_path", sp)
    monkeypatch.setattr(el, "state_path", sp)
    monkeypatch.setattr(ml, "state_path", sp)
    btf = tmp_path / "bt.json"
    btf.write_text(json.dumps(_bt()), encoding="utf-8")
    from jarvis.research_ingestion import __main__ as cli
    rc = cli.main(["ingest", "--file", str(btf), "--commit"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "outcome" in out


def test_cli_validate(tmp_path, monkeypatch, capsys):
    btf = tmp_path / "bt.json"
    btf.write_text(json.dumps(_bt()), encoding="utf-8")
    from jarvis.research_ingestion import __main__ as cli
    rc = cli.main(["validate", "--file", str(btf)])
    assert rc == 0
    assert "validation_complete" in capsys.readouterr().out
