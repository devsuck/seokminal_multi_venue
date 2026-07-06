"""Lv3(구Lv5) 자가학습 — 기대값 라벨 + 검증 게이트 테스트."""
from api_server.lv5_learner import (
    COST_PCT,
    compute_lv5_params,
    extract_trade_outcomes,
    validate_proposal,
)


def _cycle_buy(sym: str, score: float, price: float = 100.0) -> dict:
    return {
        "fill": {"side": "buy", "qty": 1, "price": price},
        "fill_symbol": sym,
        "best_score": score,
        "lv5_threshold": 40,
        "actions": [],
    }


def _cycle_close(sym: str, reason: str) -> dict:
    return {"fill": None, "fill_symbol": "", "actions": [f"close {sym} ({reason})"]}


def test_extract_parses_korean_tp_sl_labels():
    """익절/손절 한글 라벨이 tp/sl/win으로 정확히 분류돼야 함 (기존 버그 회귀 방지)."""
    cycles = [
        _cycle_buy("NVDA", 70),
        _cycle_close("NVDA", "익절 +5.2%"),
        _cycle_buy("TSLA", 55),
        _cycle_close("TSLA", "손절 -3.1%"),
    ]
    out = extract_trade_outcomes(cycles)
    assert len(out) == 2
    assert out[0]["tp"] is True and out[0]["win"] is True
    assert abs(out[0]["net_ret"] - 0.052) < 1e-9
    assert out[1]["sl"] is True and out[1]["win"] is False
    assert abs(out[1]["net_ret"] - (-0.031)) < 1e-9


def test_extract_signal_exit_has_no_net_ret():
    cycles = [
        _cycle_buy("AAPL", 60),
        _cycle_close("AAPL", "신호 반전"),
    ]
    out = extract_trade_outcomes(cycles)
    assert len(out) == 1
    assert out[0]["net_ret"] is None
    assert out[0]["win"] is False


def _make_history(rets: list[float], score: float = 60.0) -> list[dict]:
    cycles: list[dict] = []
    for i, r in enumerate(rets):
        sym = f"S{i}"
        cycles.append(_cycle_buy(sym, score))
        label = "익절" if r >= 0 else "손절"
        cycles.append(_cycle_close(sym, f"{label} {r*100:+.1f}%"))
    return cycles


def test_compute_negative_expectancy_tightens():
    """비용 못 이기는 기대값 → 임계값 상향 + 사이즈 축소."""
    cycles = _make_history([-0.02, -0.015, 0.005, -0.01, -0.02, 0.003])
    p = compute_lv5_params(cycles, base_threshold=50, base_position_pct=0.10)
    assert p["expectancy"] is not None and p["expectancy"] < 0
    assert p["threshold"] > 50
    assert p["position_pct"] < 0.10
    assert "기대값" in p["lv5_note"]


def test_compute_positive_expectancy_reports_metrics():
    cycles = _make_history([0.04, 0.05, -0.02, 0.045, 0.05, 0.04])
    p = compute_lv5_params(cycles, base_threshold=50, base_position_pct=0.10)
    assert p["expectancy"] is not None and p["expectancy"] > 0
    assert p["mdd"] is not None
    assert p["n_trades"] == 6


def test_gate_rejects_when_subset_worse():
    """제안 임계값 부분집합 기대값이 더 나쁘면 기각."""
    # 고득점(80+) 거래는 손실, 저득점(60) 거래는 수익 → 임계값 올리면 나빠짐
    outcomes = (
        [{"entry_score": 85, "net_ret": -0.02, "tp": False, "sl": True, "win": False,
          "symbol": "A", "lv5_threshold": 40} for _ in range(5)]
        + [{"entry_score": 60, "net_ret": 0.04, "tp": True, "sl": False, "win": True,
            "symbol": "B", "lv5_threshold": 40} for _ in range(5)]
    )
    g = validate_proposal(outcomes, current_threshold=50, proposed_threshold=80)
    assert g["passed"] is False
    assert g["n_subset"] == 5


def test_gate_passes_when_subset_better():
    outcomes = (
        [{"entry_score": 85, "net_ret": 0.05, "tp": True, "sl": False, "win": True,
          "symbol": "A", "lv5_threshold": 40} for _ in range(6)]
        + [{"entry_score": 55, "net_ret": -0.02, "tp": False, "sl": True, "win": False,
            "symbol": "B", "lv5_threshold": 40} for _ in range(4)]
    )
    g = validate_proposal(outcomes, current_threshold=50, proposed_threshold=80)
    assert g["passed"] is True


def test_gate_loosening_needs_positive_expectancy():
    """완화(임계값 하향)는 counterfactual 불가 — 현재 기대값 플러스 + 폭 5 이내만 허용."""
    losing = [{"entry_score": 70, "net_ret": -0.01, "tp": False, "sl": True, "win": False,
               "symbol": "A", "lv5_threshold": 40} for _ in range(8)]
    assert validate_proposal(losing, 50, 45)["passed"] is False

    winning = [{"entry_score": 70, "net_ret": 0.03, "tp": True, "sl": False, "win": True,
                "symbol": "A", "lv5_threshold": 40} for _ in range(8)]
    assert validate_proposal(winning, 50, 45)["passed"] is True
    # 폭 5 초과는 기대값 플러스여도 기각
    assert validate_proposal(winning, 50, 40)["passed"] is False


def test_gate_insufficient_data_rejects():
    few = [{"entry_score": 70, "net_ret": 0.03, "tp": True, "sl": False, "win": True,
            "symbol": "A", "lv5_threshold": 40} for _ in range(3)]
    g = validate_proposal(few, 50, 60)
    assert g["passed"] is False
    assert "판단 불가" in g["reason"]


def test_cost_is_subtracted():
    """기대값은 항상 왕복 비용 차감 후여야 함."""
    # 비용과 정확히 같은 수익 → 기대값 0 근처(shrinkage로 더 작음)
    cycles = _make_history([COST_PCT] * 6)
    p = compute_lv5_params(cycles, base_threshold=50, base_position_pct=0.10)
    assert p["expectancy"] is not None
    assert abs(p["expectancy"]) < 1e-6
