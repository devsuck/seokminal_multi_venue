"""AI LAB CANDIDATE → jarvis.research_queue 브릿지.

autoresearch 배치가 뽑은 CANDIDATE가 jarvis 감사 큐(research_queue)에 제출되는지 검증.
여기 안 거치면 audit trail·redteam·permission 게이트 없이는 paper_active 승격 불가.
"""
from __future__ import annotations

import os

import pytest

from jarvis import research_queue as rq
from research.lab.service import ResearchService


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    import importlib
    for mod in ("jarvis.audit.log", "jarvis.registry.lifecycle", "jarvis.memory.store",
                "jarvis.paper.ledger", "jarvis.paper.deploy", "jarvis.research_queue"):
        monkeypatch.setattr(importlib.import_module(mod), "state_path", sp)
    return tmp_path


def _status(*rows):
    return {"leaderboard": list(rows)}


def test_candidate_submitted_to_jarvis_queue():
    svc = ResearchService()
    n = svc._bridge_to_jarvis(_status(
        {"cid": "fac_kr_size_smb", "category": "factor", "thesis": "소형주 프리미엄", "verdict": "CANDIDATE"},
    ))
    assert n == 1
    assert rq.pending()[0]["id"] == "auto_fac_kr_size_smb"


def test_non_candidate_verdict_skipped():
    svc = ResearchService()
    n = svc._bridge_to_jarvis(_status(
        {"cid": "fac_kr_amihud", "category": "factor", "thesis": "t", "verdict": "REJECT_REDTEAM"},
    ))
    assert n == 0
    assert rq.pending() == []


def test_already_in_registry_not_resubmitted():
    from jarvis.registry import StrategyRegistry
    StrategyRegistry().register("auto_fac_kr_size_smb", name="x", config={})
    svc = ResearchService()
    n = svc._bridge_to_jarvis(_status(
        {"cid": "fac_kr_size_smb", "category": "factor", "thesis": "t", "verdict": "CANDIDATE"},
    ))
    assert n == 0
    assert rq.pending() == []


def test_bridge_id_matches_engine_prefix_convention():
    # research/autoresearch/engine.py는 hypothesis_id = f"auto_{cid}"로 experiment_registry에 기록.
    # 브릿지가 다른 prefix를 쓰면 jarvis backtest.run의 already_tested()가 못 찾음.
    svc = ResearchService()
    svc._bridge_to_jarvis(_status(
        {"cid": "ev_buyback", "category": "event", "thesis": "t", "verdict": "CANDIDATE"},
    ))
    assert rq.pending()[0]["id"] == "auto_ev_buyback"


def test_jarvis_bridged_total_accumulates_via_autoresearch_batch(monkeypatch):
    import research.autoresearch.engine as eng
    from research.lab import pipeline as pl

    monkeypatch.setattr(eng, "run_batch", lambda: _status(
        {"cid": "fac_kr_size_smb", "category": "factor", "thesis": "t", "verdict": "CANDIDATE"},
    ) | {"n_candidates": 1})
    monkeypatch.setattr(pl.ENGINE, "reconcile_from_batch", lambda status=None: {"reconciled": 0})

    svc = ResearchService()
    svc._autoresearch_batch()

    assert svc.jarvis_bridged_total == 1
    assert svc.status()["jarvis_bridged_total"] == 1
    assert rq.pending()[0]["id"] == "auto_fac_kr_size_smb"
