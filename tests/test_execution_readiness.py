"""GET /lab/execution/readiness — 전략별 arm 진행률 요약. read_only, 계산 없음."""
from __future__ import annotations

from api_server import lab_api


def test_readiness_covers_all_three_strategies_with_expected_shape():
    result = lab_api.execution_readiness()
    ids = {s["registry_id"] for s in result["strategies"]}
    assert ids == {"kr_dart_buyback_drift_v1", "futures_tsmom_32mkt", "kr_turn_of_month_v1_PORTFOLIO"}
    for s in result["strategies"]:
        assert s["decision"] in ("GO", "WAIT", "KILL")
        assert s["min_paper_months"] == result["min_paper_months"]
        assert s["months_remaining"] >= 0.0


def test_readiness_paper_months_matches_frozen_at():
    import datetime as _dt
    from research.paper import buyback_config as CFG

    result = lab_api.execution_readiness()
    row = next(s for s in result["strategies"] if s["registry_id"] == "kr_dart_buyback_drift_v1")
    expected = round((_dt.date.today() - _dt.date.fromisoformat(CFG.FROZEN_AT)).days / 30.0, 1)
    assert row["paper_months"] == expected
