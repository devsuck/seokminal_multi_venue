from api_server.invariants import CYCLE_CAP, check_agent


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
