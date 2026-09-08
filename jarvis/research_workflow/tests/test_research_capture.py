"""Research Capture(P201-ops) 테스트 — 추적 전략 → 예측 사전등록 배선.

핵심 계약: TRACKED_STATES만 대상 · (strategy_id, thesis) 중복 skip(멱등) · 기록만(거래·집행 없음) ·
새 원장 없음(rmi_ 재사용) · 자문 전용.
"""
from __future__ import annotations

import ast
import pathlib

from jarvis.research_workflow import research_capture as rc

SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"
_MODULES = ("research_capture.py", "prediction_capture_hook.py")
_N = "2026-09-08T08:00:00Z"


def _strategy(sid, status="paper_active", family=""):
    return {"strategy_id": sid, "status": status, "family": family}


def test_only_tracked_states_captured(monkeypatch):
    from jarvis.registry import StrategyRegistry
    monkeypatch.setattr(StrategyRegistry, "all_current",
                        lambda self: [_strategy("s_tsmom"), _strategy("s_dead", status="retired")])
    monkeypatch.setattr(rc, "_existing_keys", lambda: set())
    calls = []

    def fake_packet(q):
        return {"research_summary": f"summary for {q}"}
    monkeypatch.setattr("jarvis.research_workflow.investment_committee.build_committee_packet", fake_packet)

    def fake_capture(packet, *, strategy_id, strategy_family, now, commit):
        calls.append(strategy_id)
        return {"confidence": "MEDIUM", "evaluation_framework": {"framework": "risk_adjusted_vs_baseline"}}
    monkeypatch.setattr("jarvis.research_workflow.prediction_capture_hook.capture_from_committee", fake_capture)

    r = rc.capture_tracked_research(now=_N, commit=False)
    assert r["tracked_strategies"] == 1
    assert r["captured"] == 1 and calls == ["s_tsmom"]
    assert r["committed"] is False
    assert r["is_advisory"] is True and r["is_decision"] is False


def test_duplicate_thesis_skipped(monkeypatch):
    monkeypatch.setattr(rc, "_tracked_strategies", lambda: [_strategy("s_tsmom")])
    monkeypatch.setattr(rc, "_existing_keys", lambda: {("s_tsmom", "summary for does s_tsmom have durable edge?")})
    monkeypatch.setattr("jarvis.research_workflow.investment_committee.build_committee_packet",
                        lambda q: {"research_summary": f"summary for {q.lower()}"})
    monkeypatch.setattr("jarvis.research_workflow.prediction_capture_hook.capture_from_committee",
                        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("should not capture duplicate")))

    r = rc.capture_tracked_research(now=_N, commit=False)
    assert r["captured"] == 0 and r["skipped_duplicates"] == 1


def test_family_inferred_from_strategy_id_when_registry_blank():
    assert rc._infer_family("kr_futures_tsmom_32mkt") == "momentum"
    assert rc._infer_family("kr_buyback_event") == "event"
    assert rc._infer_family("kr_unknown_thing") == ""
    assert rc._infer_family("kr_unknown_thing", registry_family="Factor") == "factor"


# ── 금지 def/import/모델 누출 없음 (test_prediction_registry.py와 동일 패턴) ──
def test_no_forbidden_defs_imports_leak():
    for f in _MODULES:
        src = open(SRC / f).read()
        assert MODEL_LEAK_TOKEN not in src.lower(), f
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not any(node.module.startswith(b) for b in
                               ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
                                "jarvis.live_trading", "jarvis.portfolio_execution")), (f, node.module)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.name not in ("execute", "trade", "deploy", "allocate", "approve",
                                         "place_order", "deploy_strategy"), (f, node.name)
