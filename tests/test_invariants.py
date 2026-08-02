import datetime as dt

from api_server.invariants import (
    CYCLE_CAP,
    STUCK_RESOLUTION_DAYS,
    check_agent,
    check_polymarket_bot,
)

TODAY = dt.date(2026, 7, 21)


def _pos(**over):
    base = {
        "condition_id": "c1", "event_id": "e1", "side": "YES", "entry_price": 0.5,
        "usd": 20.0, "shares": 40.0, "end_date": "2026-08-01",
    }
    base.update(over)
    return base


def _cfg(**over):
    base = {"budget": 500.0, "max_positions": 15, "spent": 20.0, "positions": [_pos()]}
    base.update(over)
    return base


# --- polymarket bot ---------------------------------------------------------

def test_polymarket_clean_state_no_violations():
    assert check_polymarket_bot(_cfg(), today=TODAY) == []


def test_polymarket_spent_mismatch_flagged():
    # 오픈 포지션 usd 합은 20인데 spent가 100 -> 회계 드리프트
    out = check_polymarket_bot(_cfg(spent=100.0), today=TODAY)
    codes = {v["code"] for v in out}
    assert "SPENT_MISMATCH" in codes
    assert any(v["severity"] == "error" for v in out)


def test_polymarket_spent_within_rounding_tolerance_ok():
    # 20.005 vs 20.0 은 반올림 허용오차 내 -> 위반 아님
    out = check_polymarket_bot(_cfg(spent=20.005), today=TODAY)
    assert "SPENT_MISMATCH" not in {v["code"] for v in out}


def test_polymarket_spent_over_budget_flagged():
    out = check_polymarket_bot(
        _cfg(budget=10.0, spent=20.0, positions=[_pos(usd=20.0)]), today=TODAY)
    assert "SPENT_OVER_BUDGET" in {v["code"] for v in out}


def test_polymarket_slots_exceeded_flagged():
    positions = [_pos(condition_id=f"c{i}", usd=1.0) for i in range(16)]
    out = check_polymarket_bot(
        _cfg(max_positions=15, spent=16.0, positions=positions), today=TODAY)
    assert "SLOTS_EXCEEDED" in {v["code"] for v in out}


def test_polymarket_position_schema_missing_field_flagged():
    bad = _pos()
    del bad["shares"]
    out = check_polymarket_bot(_cfg(positions=[bad]), today=TODAY)
    assert "POSITION_SCHEMA" in {v["code"] for v in out}


def test_polymarket_stuck_resolution_flagged():
    # 만기가 오늘보다 STUCK+3일 전인데 아직 큐에 있음 -> 정산 멈춤
    stale_end = (TODAY - dt.timedelta(days=STUCK_RESOLUTION_DAYS + 3)).isoformat()
    out = check_polymarket_bot(
        _cfg(positions=[_pos(end_date=stale_end)]), today=TODAY)
    assert "STUCK_RESOLUTION" in {v["code"] for v in out}


def test_polymarket_recently_expired_not_stuck():
    # 만기 지난 지 얼마 안 됨(정상 정산 대기 창) -> 위반 아님
    recent_end = (TODAY - dt.timedelta(days=1)).isoformat()
    out = check_polymarket_bot(
        _cfg(positions=[_pos(end_date=recent_end)]), today=TODAY)
    assert "STUCK_RESOLUTION" not in {v["code"] for v in out}


def test_polymarket_empty_positions_ok():
    assert check_polymarket_bot(_cfg(spent=0.0, positions=[]), today=TODAY) == []


# --- agent ------------------------------------------------------------------

def test_agent_clean_state_no_violations():
    assert check_agent("a1", alloc=100.0, realized_pnl=-5.0, invested=30.0, n_cycles=500) == []


def test_agent_cycle_cap_saturation_warns():
    out = check_agent("a1", alloc=100.0, realized_pnl=0.0, invested=0.0, n_cycles=CYCLE_CAP)
    v = next(v for v in out if v["code"] == "CYCLE_CAP_SATURATION")
    assert v["severity"] == "warn"


def test_agent_invested_negative_flagged():
    out = check_agent("a1", alloc=100.0, realized_pnl=0.0, invested=-5.0, n_cycles=10)
    v = next(v for v in out if v["code"] == "INVESTED_NEGATIVE")
    assert v["severity"] == "error"


def test_agent_over_allocated_warns():
    out = check_agent("a1", alloc=100.0, realized_pnl=0.0, invested=140.0, n_cycles=10)
    assert "OVER_ALLOCATED" in {v["code"] for v in out}


# --- polymarket_sharp_wallet_bot ---------------------------------------------

from api_server.invariants import check_polymarket_sharp_wallet_bot


def _sw_pos(**over):
    base = {
        "condition_id": "c1", "convergence_bucket": 1, "horizon_s": 30,
        "direction": 1.0, "entry_price": 0.5, "entry_ts": 1000.0, "exit_at": 1030.0,
        "usd": 15.0, "shares": 30.0, "outcome_index": 0,
    }
    base.update(over)
    return base


def _sw_cfg(**over):
    base = {"budget": 300.0, "max_concurrent_positions": 30, "spent": 15.0, "positions": [_sw_pos()]}
    base.update(over)
    return base


def test_sharp_wallet_clean_state_no_violations():
    assert check_polymarket_sharp_wallet_bot(_sw_cfg(), now=1030.0) == []


def test_sharp_wallet_spent_mismatch_flagged():
    out = check_polymarket_sharp_wallet_bot(_sw_cfg(spent=100.0), now=1030.0)
    codes = {v["code"] for v in out}
    assert "SPENT_MISMATCH" in codes
    assert any(v["severity"] == "error" for v in out)


def test_sharp_wallet_stuck_exit_flagged():
    # exit_at=1030, now=1030+3601 -> STUCK_EXIT_SECONDS(3600) 초과
    out = check_polymarket_sharp_wallet_bot(_sw_cfg(), now=1030.0 + 3601.0)
    codes = {v["code"] for v in out}
    assert "STUCK_EXIT" in codes


def test_sharp_wallet_missing_field_flagged():
    bad_pos = _sw_pos()
    del bad_pos["exit_at"]
    out = check_polymarket_sharp_wallet_bot(_sw_cfg(positions=[bad_pos], spent=15.0), now=1030.0)
    codes = {v["code"] for v in out}
    assert "POSITION_SCHEMA" in codes
