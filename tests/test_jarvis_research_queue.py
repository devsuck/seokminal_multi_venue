"""Lv2 리서치 큐 테스트 — ingest 가드(dedup·memory consult·rate cap) + run_pending BH-FDR.

스케줄 Claude Code가 쓰는 큐. LLM 없이 결정적 파트만 검증.
"""
from __future__ import annotations

import os

import pytest

from jarvis import research_queue as rq
from jarvis.registry import Status, StrategyRegistry


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    for mod in ("jarvis.audit.log", "jarvis.registry.lifecycle", "jarvis.memory.store",
                "jarvis.paper.ledger", "jarvis.paper.deploy", "jarvis.research_queue"):
        import importlib
        monkeypatch.setattr(importlib.import_module(mod), "state_path", sp)
    return tmp_path


def _spec(sid, **kw):
    base = {"id": sid, "name": sid, "family": "event", "market": "KR",
            "thesis": "t", "required_data": ["daily_ohlcv", "market_cap", "disclosure_event_dates"],
            "edge_bps": 0.0, "n_trades": 40, "hold": 20, "cost_bps": 40.0, "seed": 5}
    base.update(kw)
    return base


def test_submit_accepts_new():
    r = rq.submit(_spec("new_1"))
    assert r["accepted"] is True
    assert len(rq.pending()) == 1


def test_submit_rejects_missing_fields():
    assert rq.submit({"id": "x"})["accepted"] is False


def test_submit_rejects_duplicate_in_queue():
    rq.submit(_spec("dup"))
    r = rq.submit(_spec("dup"))
    assert r["accepted"] is False and r["reason"] == "duplicate_in_queue"


def test_submit_rejects_already_in_registry():
    reg = StrategyRegistry()
    reg.register("known", name="known", config={"x": 1})
    r = rq.submit(_spec("known"))
    assert r["accepted"] is False and r["reason"] == "already_tested_in_registry"


def test_memory_consult_blocks_similar_without_differentiation():
    # 유동성웨이브 = 거부 교훈. 유사 키워드 → differentiation 없으면 거부
    r = rq.submit(_spec("wave_like", keywords=["유동성", "웨이브"]))
    assert r["accepted"] is False
    assert r["reason"] == "similar_rejected_needs_differentiation"
    assert "KR_LIQUIDITY_WAVE_SURVIVORSHIP" in r["similar"]


def test_memory_consult_allows_with_differentiation():
    r = rq.submit(_spec("wave_ok", keywords=["유동성"], differentiation="지수편입 확정이벤트 기반"))
    assert r["accepted"] is True


def test_run_pending_validates_and_clears():
    # 진짜 엣지 + 노이즈 섞어 제출 → run_pending → BH-FDR 판정
    rq.submit(_spec("edge_1", edge_bps=120.0, n_trades=45, hold=10, seed=200))
    rq.submit(_spec("noise_1", edge_bps=0.0, seed=7))
    res = rq.run_pending(alpha=0.1)
    assert res["ran"] == 2
    assert rq.pending() == []          # 처리 후 비워짐
    assert len(rq.processed()) == 2
    assert res["report"]["bh_fdr"]["alpha"] == 0.1


def test_run_pending_rate_cap():
    for i in range(4):
        rq.submit(_spec(f"c_{i}", seed=i))
    res = rq.run_pending(alpha=0.1, cap=2)
    assert res["ran"] == 2 and res["capped"] is True
    assert len(rq.pending()) == 2      # 초과분 유지


def test_synthetic_edge_blocked_by_redteam():
    rq.submit(_spec("edge_dep", edge_bps=120.0, n_trades=45, hold=10, seed=200))
    rq.run_pending(alpha=0.1, auto_deploy=True)
    # 합성 엣지 = critic+BH 통과하나 레드팀이 실통제 미실행으로 페이퍼 차단(정직) → watchlist
    assert StrategyRegistry().state("edge_dep")["status"] == Status.WATCHLIST.value
