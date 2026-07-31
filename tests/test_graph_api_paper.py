"""공급망 그래프 페이퍼 트레이딩 mark-to-market 회귀 테스트.

버그: /graph/paper가 진입 시점 스냅샷을 그대로 반환해 평가금액/PnL이 영구 고정됐음.
_mark_to_market()이 오픈 포지션에 live quote를 얹어 반환하는지, 원가(entry_price/value)는
청산 정산용이라 건드리지 않는지 확인.
"""
from __future__ import annotations

from unittest.mock import patch

import api_server.graph_api as g


def _paper_with_one_position():
    return {
        "capital": 10_000.0, "cash": 8_000.0,
        "positions": [{
            "node_id": "tsmc", "symbol": "TSM", "name": "TSMC", "side": "BUY",
            "qty": 10.0, "entry_price": 100.0, "entry_score": 0.5, "current_score": 0.8,
            "score_delta": 0.3, "entry_time": "2026-07-01T00:00:00", "value": 1000.0,
        }],
        "closed": [], "signals": [],
    }


def test_mark_to_market_computes_live_fields_for_buy():
    paper = _paper_with_one_position()
    with patch.object(g, "_fetch_quote", return_value=120.0):
        out = g._mark_to_market(paper)
    pos = out["positions"][0]
    assert pos["current_price"] == 120.0
    assert pos["market_value"] == 1200.0
    assert pos["unrealized_pnl"] == 200.0
    # 원가 필드는 청산 정산에 쓰이므로 그대로 유지
    assert pos["entry_price"] == 100.0
    assert pos["value"] == 1000.0


def test_mark_to_market_sell_side_pnl_sign():
    paper = _paper_with_one_position()
    paper["positions"][0]["side"] = "SELL"
    with patch.object(g, "_fetch_quote", return_value=90.0):
        out = g._mark_to_market(paper)
    assert out["positions"][0]["unrealized_pnl"] == 100.0  # 숏은 가격 하락이 이익


def test_mark_to_market_falls_back_to_entry_price_on_quote_failure():
    paper = _paper_with_one_position()
    with patch.object(g, "_fetch_quote", return_value=None):
        out = g._mark_to_market(paper)
    pos = out["positions"][0]
    assert pos["current_price"] == 100.0
    assert pos["unrealized_pnl"] == 0.0


def test_get_paper_endpoint_returns_marked_to_market(tmp_path):
    paper_file = tmp_path / "lkg_paper.json"
    with patch.object(g, "_PAPER_FILE", paper_file):
        g._save_paper(_paper_with_one_position())
        with patch.object(g, "_fetch_quote", return_value=150.0):
            out = g.get_paper()
    assert out["positions"][0]["market_value"] == 1500.0
