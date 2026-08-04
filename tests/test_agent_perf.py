"""Per-agent FIFO performance ledger."""
from api_server.agent_perf import compute_performance


def _cycle(n, symbol, side, qty, price, note=""):
    return {"cycle": n, "ts": f"t{n}", "symbol": symbol, "decision": side.upper(),
            "note": note, "fill": {"side": side, "qty": qty, "price": price}}


def test_no_fills_is_empty():
    perf = compute_performance([{"cycle": 1, "decision": "WATCH", "symbol": "AAPL"}])
    assert perf.trades == []
    assert perf.realized_pnl == 0.0
    assert perf.open_positions == []


def test_single_buy_opens_position():
    perf = compute_performance([_cycle(1, "AAPL", "buy", 10, 100.0, "저평가")])
    assert len(perf.trades) == 1
    assert perf.trades[0]["reason"] == "저평가"
    assert perf.open_positions == [{"symbol": "AAPL", "qty": 10, "avg_price": 100.0}]
    assert perf.realized_pnl == 0.0
    assert perf.invested == 1000.0


def test_buy_then_sell_realizes_pnl():
    perf = compute_performance([
        _cycle(1, "AAPL", "buy", 10, 100.0),
        _cycle(2, "AAPL", "sell", 10, 110.0, "익절"),
    ])
    assert perf.realized_pnl == 100.0  # (110-100)*10
    assert perf.open_positions == []
    assert perf.trades[1]["realized_pnl"] == 100.0


def test_budget_gate_shrinks_after_realized_loss_even_when_flat():
    # api_server/routers/agents.py의 신규진입 budget 게이트는
    # `alloc + realized_pnl - invested`여야 한다. invested만 빼면(구버전 버그)
    # 포지션을 다 청산한 뒤엔 realized 손실이 누적됐어도 budget이 alloc으로
    # 원복돼 다시 풀배팅 가능해진다 — lv5 가상화폐 에이전트가 -78% 찍고도
    # 계속 도는 원인이었다.
    perf = compute_performance([
        _cycle(1, "BTC", "buy", 1, 100.0),
        _cycle(2, "BTC", "sell", 1, 10.0, "손절"),  # -90 realized, 지금은 flat
    ])
    assert perf.invested == 0.0
    assert perf.realized_pnl == -90.0
    alloc = 100.0
    budget = max(alloc + perf.realized_pnl - perf.invested, 0.0)
    assert budget == 10.0  # 살아남은 자본만, alloc 전액 아님


def test_partial_sell_keeps_remainder():
    perf = compute_performance([
        _cycle(1, "AAPL", "buy", 10, 100.0),
        _cycle(2, "AAPL", "sell", 4, 120.0),
    ])
    assert perf.realized_pnl == 80.0  # (120-100)*4
    assert perf.open_positions == [{"symbol": "AAPL", "qty": 6, "avg_price": 100.0}]


def test_fifo_matching_across_lots():
    perf = compute_performance([
        _cycle(1, "AAPL", "buy", 5, 100.0),
        _cycle(2, "AAPL", "buy", 5, 200.0),
        _cycle(3, "AAPL", "sell", 5, 150.0),  # matches first lot @100 -> (150-100)*5=250
    ])
    assert perf.realized_pnl == 250.0
    assert perf.open_positions == [{"symbol": "AAPL", "qty": 5, "avg_price": 200.0}]


def test_multiple_symbols_independent():
    perf = compute_performance([
        _cycle(1, "AAPL", "buy", 10, 100.0),
        _cycle(2, "NVDA", "buy", 2, 800.0),
        _cycle(3, "NVDA", "sell", 2, 900.0),  # +200
    ])
    assert perf.realized_pnl == 200.0
    syms = {p["symbol"] for p in perf.open_positions}
    assert syms == {"AAPL"}


def test_invalid_fill_ignored():
    perf = compute_performance([
        {"cycle": 1, "symbol": "AAPL", "fill": {"side": "buy", "qty": 0, "price": 100}},
        {"cycle": 2, "symbol": "AAPL", "fill": {"side": "hold", "qty": 5, "price": 100}},
        {"cycle": 3, "symbol": "AAPL", "fill": "garbage"},
    ])
    assert perf.trades == []
    assert perf.open_positions == []
