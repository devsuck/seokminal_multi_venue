"""P2.2 Portfolio Risk Scaling Layer 테스트.

vol-targeting · drawdown 스케일 · regime 배수. 제안전용.
케이스: 고변동성↓ · 저변동성 복원 · drawdown 축소 · 결측 폴백 · regime 배수.
가드: 결정성 · no-lookahead · 히스토리부족 무레버리지.
"""
from __future__ import annotations

from jarvis.portfolio.allocator import AllocationProposal, AllocationResult
from jarvis.portfolio.risk_scaler import (
    PortfolioState,
    RiskScalingConfig,
    scale_allocation,
)

DATES = [f"2026-01-{1 + i:02d}" for i in range(24)]


class FakeMatrix:
    def __init__(self, series, dates=None):
        self._dates = dates or DATES
        self._series = series

    def calendar(self):
        return list(self._dates)

    def aligned(self, cal):
        idx = [self._dates.index(d) for d in cal]
        return cal, {sid: [r[i] for i in idx] for sid, r in self._series.items()}


def _alloc(weights: dict) -> AllocationResult:
    props = [AllocationProposal(k, v, 0.0, v, "test", "T") for k, v in weights.items()]
    return AllocationResult(props, "test", None, "T")


def _series(vol: float, n=24):
    return [vol if i % 2 == 0 else -vol for i in range(n)]  # 진폭 = periodic stdev


# ── 고변동성 → 노출 축소 ─────────────────────────────────────
def test_high_volatility_reduces_exposure():
    hi = scale_allocation(_alloc({"A": 1.0}), FakeMatrix({"A": _series(0.05)}), ts="T")
    lo = scale_allocation(_alloc({"A": 1.0}), FakeMatrix({"A": _series(0.005)}), ts="T")
    assert hi.gross_exposure < lo.gross_exposure
    assert hi.gross_exposure < 1.0                       # 고변동성 → 1 미만
    assert hi.current_volatility > lo.current_volatility


# ── 저변동성 → 노출 복원(캡까지) ─────────────────────────────
def test_low_volatility_restores_exposure():
    lo = scale_allocation(_alloc({"A": 1.0}), FakeMatrix({"A": _series(0.001)}), ts="T")
    assert lo.gross_exposure == 1.0                      # vol_scalar>1 이지만 cap=1.0로 복원
    # 레버리지 허용 설정이면 1 초과 가능
    lev = scale_allocation(_alloc({"A": 1.0}), FakeMatrix({"A": _series(0.001)}),
                           RiskScalingConfig(max_leverage=2.0), ts="T")
    assert lev.gross_exposure > 1.0


# ── drawdown 축소 ────────────────────────────────────────────
def test_drawdown_reduces_exposure():
    mat = FakeMatrix({"A": _series(0.012)})
    no_dd = scale_allocation(_alloc({"A": 1.0}), mat,
                             state=PortfolioState(equity=100, peak=100), ts="T")
    in_dd = scale_allocation(_alloc({"A": 1.0}), mat,
                             state=PortfolioState(equity=85, peak=100), ts="T")  # dd=15%
    assert in_dd.drawdown_adjustment == 0.5              # 10~20% 구간
    assert no_dd.drawdown_adjustment == 1.0
    assert abs(in_dd.gross_exposure - no_dd.gross_exposure * 0.5) < 1e-6


def test_drawdown_ladder_levels():
    mat = FakeMatrix({"A": _series(0.012)})
    for eq, expect in [(97, 1.0), (92, 0.75), (85, 0.5), (70, 0.25)]:
        r = scale_allocation(_alloc({"A": 1.0}), mat,
                             state=PortfolioState(equity=eq, peak=100), ts="T")
        assert r.drawdown_adjustment == expect


# ── 결측 데이터 폴백 ─────────────────────────────────────────
def test_missing_vol_data_conservative_fallback():
    # 상수(무변동) 시리즈 → current_vol 계산불가 → 보수 스칼라
    r = scale_allocation(_alloc({"A": 1.0}), FakeMatrix({"A": [0.0] * 24}), ts="T")
    assert r.current_volatility is None
    assert r.gross_exposure == 0.5                       # conservative_vol_scalar
    assert "conservative" in r.rationale


def test_insufficient_history_no_leverage():
    short = [f"2026-01-{1 + i:02d}" for i in range(10)]
    r = scale_allocation(_alloc({"A": 1.0}), FakeMatrix({"A": _series(0.001, 10)}, dates=short),
                         RiskScalingConfig(max_leverage=2.0), ts="T")
    assert r.gross_exposure <= 1.0                       # 저변동성이라도 히스토리<20 → 무레버리지
    assert "insufficient_history" in r.rationale


# ── regime 배수 ──────────────────────────────────────────────
def test_regime_multiplier_correctness():
    mat = FakeMatrix({"A": _series(0.012)})
    on = scale_allocation(_alloc({"A": 1.0}), mat, regime="risk_on", ts="T")
    off = scale_allocation(_alloc({"A": 1.0}), mat, regime="risk_off", ts="T")
    assert on.regime_multiplier == 1.0 and off.regime_multiplier == 0.5
    assert abs(off.gross_exposure - on.gross_exposure * 0.5) < 1e-6


def test_regime_accepts_dict_and_unknown():
    mat = FakeMatrix({"A": _series(0.012)})
    d = scale_allocation(_alloc({"A": 1.0}), mat, regime={"regime": "high_vol"}, ts="T")
    assert d.regime_multiplier == 0.5
    unk = scale_allocation(_alloc({"A": 1.0}), mat, regime="martian", ts="T")
    assert unk.regime_multiplier == 1.0                  # 미지 라벨 = 무조정
    none = scale_allocation(_alloc({"A": 1.0}), mat, regime=None, ts="T")
    assert none.regime_multiplier == 1.0


# ── 결정성 · no-lookahead ────────────────────────────────────
def test_deterministic():
    mat = FakeMatrix({"A": _series(0.012)})
    a = scale_allocation(_alloc({"A": 1.0}), mat, regime="neutral", ts="T")
    b = scale_allocation(_alloc({"A": 1.0}), mat, regime="neutral", ts="T")
    assert a.to_dict() == b.to_dict()


def test_no_lookahead_future_ignored():
    base = _series(0.012)
    as_of = DATES[11]
    m1 = FakeMatrix({"A": base})
    m2 = FakeMatrix({"A": base[:12] + [9.9] * 12})       # 미래 오염
    r1 = scale_allocation(_alloc({"A": 1.0}), m1, as_of=as_of, ts="T")
    r2 = scale_allocation(_alloc({"A": 1.0}), m2, as_of=as_of, ts="T")
    assert r1.to_dict() == r2.to_dict()


# ── 스칼라 곱 반영(strategy_weights = weight×gross) ──────────
def test_scaled_weights_reflect_gross():
    mat = FakeMatrix({"A": _series(0.012), "B": _series(0.012)})
    r = scale_allocation(_alloc({"A": 0.6, "B": 0.4}), mat, ts="T")
    g = r.gross_exposure
    assert abs(r.strategy_weights["A"] - 0.6 * g) < 1e-6
    assert abs(sum(r.strategy_weights.values()) - g) < 1e-6
