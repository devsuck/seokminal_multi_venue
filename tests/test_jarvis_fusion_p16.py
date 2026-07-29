"""P1.6 Signal Coverage Completion 테스트.

1) 어댑터 커버리지: buyback 신선도 만료, tsmom 정적 유니버스+데이터 배선, tom 캘린더 검증
2) 정규화 레이어: 전략-상대 [0,1], raw 보존, 전략간 독립
3) fusion 백테스트: 개별 vs 융합(Sharpe/CAGR/MDD/turnover/corr reduction)
"""
from __future__ import annotations

import pandas as pd

from jarvis.fusion.adapters.buyback import BuybackPositionAdapter
from jarvis.fusion.adapters.tsmom import FUTURES_UNIVERSE, TsmomAdapter
from jarvis.fusion.backtest import (
    avg_pairwise_corr,
    compare_performance,
    diversification,
    turnover,
)
from jarvis.fusion.diagnostics import buyback_freshness, verify_tom_calendar
from jarvis.fusion.normalize import normalize_signals
from jarvis.fusion.types import StrategySignal


# ── 1a. buyback 신선도 만료(exit_date 결측 → hold 규칙) ───────
def test_buyback_expires_stale_missing_exit():
    # exit_date 없는 오래된 진입 — hold(20영업일) 지났으면 신호 없어야
    rows = [{"stock_code": "111", "entry_date": "2026-01-05", "hold_days": 20}]  # exit 미기록
    a = BuybackPositionAdapter(rows=rows)
    assert a.signals("2026-06-01") == []            # 만료됨(과거) → stale 롱 방지
    assert len(a.signals("2026-01-08")) == 1        # 아직 창 안 → 롱


def test_buyback_missing_exit_uses_hold_rule_meta():
    rows = [{"stock_code": "111", "entry_date": "2026-06-15", "hold_days": 20}]
    s = BuybackPositionAdapter(rows=rows).signals("2026-06-16")[0]
    assert s.meta["exit_source"] == "hold_rule"
    assert s.meta["scheduled_exit"] > "2026-06-15"


def test_buyback_freshness_report():
    rows = [
        {"stock_code": "A", "entry_date": "2026-07-15", "hold_days": 20},   # 신선, active
        {"stock_code": "B", "entry_date": "2026-01-05", "hold_days": 20},   # 만료, exit 미기록
    ]
    rep = buyback_freshness("2026-07-22", rows=rows)
    assert rep["newest_entry"] == "2026-07-15"
    assert rep["days_since_newest"] == 7
    assert rep["n_missing_exit"] == 2
    assert rep["n_expired_missing_exit"] == 1        # B는 만료됐는데 exit 없음
    assert rep["n_active"] == 1                       # A만 실제 보유중
    assert rep["ledger_fresh"] is True


# ── 1b. tom 캘린더 검증 ──────────────────────────────────────
def test_verify_tom_calendar_detects_holiday_mismatch():
    # 1월 마지막 평일에 휴장(그날 거래일 목록에서 빠짐) → 불일치 검출
    from jarvis.fusion.adapters.base import last_business_day
    lbd = last_business_day(2026, 1)
    # 실제 거래일 = lbd 하루 전까지만(그날 휴장 가정)
    trading = ["2026-01-02", "2026-01-15", "2026-01-28", "2026-01-29"]  # 29 < lbd(30)
    rep = verify_tom_calendar(trading)
    assert rep["n_months"] == 1
    assert any(mm["approx"] == lbd for mm in rep["mismatches"])


def test_verify_tom_calendar_match():
    from jarvis.fusion.adapters.base import last_business_day
    lbd = last_business_day(2026, 3)
    rep = verify_tom_calendar(["2026-03-02", "2026-03-16", lbd])
    assert rep["mismatches"] == []
    assert rep["match_rate"] == 1.0


# ── 1c. tsmom 정적 유니버스 + 실제 데이터 배선 증명 ──────────
def test_tsmom_static_universe_fallback():
    a = TsmomAdapter("futures_tsmom")           # symbols=None → 폴백
    assert set(a._resolve_symbols()) == set(FUTURES_UNIVERSE)
    assert "ES" in a._resolve_symbols() and len(FUTURES_UNIVERSE) == 32


def test_tsmom_end_to_end_with_real_build_panel(monkeypatch):
    """실 build_panel(load_df) 경로로 데이터 있을 때 신호 산출 증명 = 배선 완결.

    intraday_store.load_df를 합성 DataFrame으로 대체(파케이 I/O 없이 실 함수 경로 사용).
    """
    import research.hypotheses.tsmom as tsmom_mod

    def fake_load_df(symbol, tf):
        ts0 = 1_700_000_000
        # 상승 시리즈(충분한 히스토리) — 작은 파라미터로 모멘텀 +
        rows = [{"ts_utc": ts0 + i * 86400, "open": 100 + i, "high": 100 + i,
                 "low": 100 + i, "close": 100 + i, "volume": 1} for i in range(300)]
        return pd.DataFrame(rows)

    # build_panel이 쓰는 바로 그 이름을 패치(임포트 순서 무관 — 견고)
    monkeypatch.setattr(tsmom_mod, "load_df", fake_load_df)
    from research.hypotheses.tsmom import build_panel, tsmom_weights
    a = TsmomAdapter("futures_tsmom", symbols=["ES"],
                     params={"lookback": 20, "vol_window": 20, "target_vol": 0.15, "cap": 3.0},
                     panel_loader=build_panel, weights_fn=tsmom_weights)
    # build_panel이 만든 마지막 날짜에서 신호가 나와야(데이터 존재 시 = 배선 완결)
    panel = build_panel("ES")
    last = panel["dates"][-1]
    sigs = a.signals(last)
    assert len(sigs) == 1 and sigs[0].direction == 1   # 상승 → 롱


# ── 2. 정규화 레이어 ─────────────────────────────────────────
def test_normalize_rank_scales_within_strategy():
    sigs = [StrategySignal("tsmom", "A", 1, 0.2), StrategySignal("tsmom", "B", 1, 0.9),
            StrategySignal("tsmom", "C", -1, 0.5)]
    out = normalize_signals(sigs, "rank")
    byinst = {s.instrument: s.strength for s in out}
    assert byinst["A"] == 0.0 and byinst["B"] == 1.0 and byinst["C"] == 0.5  # 순위 [0,1]
    assert all(0.0 <= s.strength <= 1.0 for s in out)


def test_normalize_preserves_raw_in_meta():
    out = normalize_signals([StrategySignal("s", "A", 1, 0.3),
                             StrategySignal("s", "B", 1, 0.7)], "minmax")
    a = next(s for s in out if s.instrument == "A")
    assert a.meta["raw_strength"] == 0.3 and a.meta["norm_method"] == "minmax"


def test_normalize_constant_strategy_maps_uniform():
    # buyback처럼 전부 1.0 → 정규화 후에도 균일(1.0), 크래시 없음
    out = normalize_signals([StrategySignal("buyback", "A", 1, 1.0),
                             StrategySignal("buyback", "B", 1, 1.0)], "rank")
    assert all(s.strength == 1.0 for s in out)


def test_normalize_is_per_strategy_independent():
    sigs = [StrategySignal("X", "A", 1, 0.1), StrategySignal("X", "B", 1, 0.9),
            StrategySignal("Y", "C", 1, 5.0)]  # Y 단일 → 1.0
    out = {s.instrument: s.strength for s in normalize_signals(sigs, "rank")}
    assert out["C"] == 1.0                       # Y는 X 스케일에 영향 안 받음
    assert out["A"] == 0.0 and out["B"] == 1.0


# ── 3. fusion 백테스트 ───────────────────────────────────────
def test_turnover_computes_position_change():
    ps = [{"A": 1.0}, {"A": 1.0}, {"A": -1.0}, {"A": -1.0}]  # 1회 반전
    # Δ: 0, 2, 0 → mean(|Δ|/2) = (0+1+0)/3
    assert turnover(ps) == round((0 + 1 + 0) / 3, 6)


def test_diversification_benefit_for_negatively_correlated():
    # 음의 상관(완전헤지 아님) 두 전략 → 융합 변동성↓, DR>1, corr_reduction>0
    up = [0.03, -0.02, 0.03, -0.02, 0.03, -0.02] * 4
    dn = [-0.02, 0.03, -0.01, 0.02, -0.03, 0.01] * 4  # 부호 반대·크기 다름(port vol>0)
    series = {"U": up, "D": dn}
    w = {"U": 0.5, "D": 0.5}
    div = diversification(series, w)
    assert div["avg_pairwise_corr"] < 0
    assert div["diversification_ratio"] > 1.0
    assert div["corr_reduction"] > 0


def test_compare_performance_full_report():
    a = [0.01, 0.02, -0.01, 0.015, 0.005, 0.02] * 5
    b = [0.005, -0.01, 0.02, 0.0, 0.01, -0.005] * 5
    rep = compare_performance({"A": a, "B": b})
    assert rep["n_strategies"] == 2
    assert set(rep["individual"]) == {"A", "B"}
    for m in rep["individual"].values():
        assert "sharpe" in m and "cagr" in m and "max_drawdown" in m
    f = rep["fused"]
    assert "diversification_ratio" in f and "sharpe_vs_avg_individual" in f
    assert abs(sum(f["weights"].values()) - 1.0) < 1e-9


def test_compare_performance_single_strategy_no_diversification():
    rep = compare_performance({"A": [0.01, 0.02, -0.01, 0.015] * 8})
    assert rep["fused"]["diversification_ratio"] is None   # n<2 정직
    assert rep["fused"]["avg_pairwise_corr"] is None


def test_avg_pairwise_corr_none_for_single():
    assert avg_pairwise_corr({"A": [0.01, 0.02, 0.03]}) is None
