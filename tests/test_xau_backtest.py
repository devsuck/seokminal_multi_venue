"""XAU 백테스트 러너 유닛테스트 — 리샘플·sizing·통계 산식."""
from datetime import datetime

from research.xau_session.sessions import NY_TZ
from research.xau_session.strategy import Config
from research.run_xau_session_backtest import _resample_ohlc, build_htf_bias, backtest


def _ts(mo, d, h, mi):
    return datetime(2026, mo, d, h, mi, tzinfo=NY_TZ).timestamp()


def _bars(rows):
    return {"ts": [r[0] for r in rows], "o": [r[1] for r in rows], "h": [r[2] for r in rows],
            "l": [r[3] for r in rows], "c": [r[4] for r in rows]}


def _one_long_tp():
    return [
        (_ts(1, 15, 19, 0), 2015, 2030, 2000, 2015),
        (_ts(1, 15, 21, 0), 2015, 2025, 2005, 2020),
        (_ts(1, 16, 2, 45), 2020, 2028, 2010, 2020),
        (_ts(1, 16, 3, 0), 2020, 2022, 2018, 2020),
        (_ts(1, 16, 3, 15), 2031, 2036, 2030, 2035),   # 진입 @2035, risk=35, tp=2052.5
        (_ts(1, 16, 3, 30), 2035, 2053, 2034, 2050),   # tp
    ]


# ── 리샘플 ────────────────────────────────────────────────────────
def test_resample_buckets_by_clock():
    # 15m 바 5개, 1h(3600s) 버킷 → UTC 경계 정렬. 첫 4개 같은 시각대면 1버킷.
    base = 1_700_000_000
    base -= base % 3600                       # 정시 정렬
    rows = [(base + i * 900, 10 + i, 20 + i, 5 + i, 12 + i) for i in range(5)]
    r = _resample_ohlc(_bars(rows), 3600)
    assert len(r["ts"]) == 2                   # 4개 + 1개
    assert r["o"][0] == 10 and r["c"][0] == 15 # open=첫, close=넷째 종가(12+3)
    assert r["h"][0] == 23 and r["l"][0] == 5  # high=max(20+3), low=min(5)
    assert r["ts"][0] == base + 3600           # 버킷 종료 태깅(no-lookahead)


def test_build_htf_bias_shape():
    base = 1_700_000_000
    rows = [(base + i * 900, 100, 101, 99, 100 + i) for i in range(40)]
    htf = build_htf_bias(_bars(rows), tf_seconds=3600, ema_len=5)
    assert set(htf) == {"ts", "bias"}
    assert all(b in (1, -1) for b in htf["bias"])
    assert len(htf["ts"]) == len(htf["bias"])


# ── sizing / 통계 ─────────────────────────────────────────────────
def test_single_winner_known_answer_no_costs():
    # R:R=0.5, risk%=3, 무비용 → 단일 승자 net = 0.5 * 0.03 * equity = 1.5%.
    rep = backtest(_bars(_one_long_tp()), Config(),
                   commission_per_contract=0.0, slippage_ticks=0.0)
    assert rep["n_trades"] == 1 and rep["wins"] == 1
    assert rep["win_rate"] == 1.0
    assert abs(rep["net"] - 1500.0) < 1e-6     # 0.015 * 100000
    assert rep["profit_factor"] == float("inf")  # 손실 0


def test_costs_reduce_net():
    clean = backtest(_bars(_one_long_tp()), Config(),
                     commission_per_contract=0.0, slippage_ticks=0.0)
    costed = backtest(_bars(_one_long_tp()), Config(),
                      commission_per_contract=2.5, slippage_ticks=2.0, tick_size=0.01)
    assert costed["net"] < clean["net"]        # 비용이 순손익 깎음


def test_empty_bars_no_trades():
    rep = backtest({"ts": [], "o": [], "h": [], "l": [], "c": []})
    assert rep["n_trades"] == 0 and rep["net"] == 0.0 and rep["profit_factor"] == 0.0
