"""P2.25 Regime Auto-Wiring 테스트.

detect_regime_hmm 출력 → 스케일러 배수. 전환·안전폴백·결정성·no-lookahead.
detector 주입으로 hmmlearn 없이도 배선 검증 + 실 HMM 통합 스모크(설치 시).
"""
from __future__ import annotations

import pytest

from jarvis.portfolio.allocator import AllocationProposal, AllocationResult
from jarvis.portfolio.regime import detect_portfolio_regime, regime_for_scaler
from jarvis.portfolio.risk_scaler import scale_allocation

N = 40
DATES = [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(N)]


class FakeMatrix:
    def __init__(self, series, dates=None):
        self._d = dates or DATES
        self._s = series

    def calendar(self):
        return list(self._d)

    def aligned(self, cal):
        idx = [self._d.index(d) for d in cal]
        return cal, {k: [v[i] for i in idx] for k, v in self._s.items()}


def _alloc(w):
    return AllocationResult([AllocationProposal(k, v, 0.0, v, "t", "T") for k, v in w.items()],
                            "t", None, "T")


def _ret(mag):
    return [mag if i % 2 == 0 else -mag for i in range(N)]


# ── 라벨 → 배수 매핑(전환) ───────────────────────────────────
def test_regime_labels_map_to_multipliers():
    mat = FakeMatrix({"A": _ret(0.01)})
    expect = {"bull_low_vol": 1.0, "bull_high_vol": 0.75,
              "bear_low_vol": 0.5, "bear_high_vol": 0.3}
    for label, mult in expect.items():
        det = lambda r, _l=label: {"current_regime": _l}
        reg = regime_for_scaler(mat, {"A": 1.0}, detector=det)
        res = scale_allocation(_alloc({"A": 1.0}), mat, regime=reg, ts="T")
        assert res.regime_multiplier == mult, label


def test_regime_transition_changes_exposure():
    # bull_low_vol → bear_high_vol 전환 시 노출이 줄어야
    mat = FakeMatrix({"A": _ret(0.012)})
    bull = regime_for_scaler(mat, {"A": 1.0}, detector=lambda r: {"current_regime": "bull_low_vol"})
    bear = regime_for_scaler(mat, {"A": 1.0}, detector=lambda r: {"current_regime": "bear_high_vol"})
    g_bull = scale_allocation(_alloc({"A": 1.0}), mat, regime=bull, ts="T").gross_exposure
    g_bear = scale_allocation(_alloc({"A": 1.0}), mat, regime=bear, ts="T").gross_exposure
    assert g_bear < g_bull
    assert abs(g_bear - g_bull * (0.3 / 1.0)) < 1e-6


# ── 안전 폴백 ────────────────────────────────────────────────
def test_unknown_regime_safe_fallback():
    mat = FakeMatrix({"A": _ret(0.012)})
    # detector가 미지 라벨 반환 → 'unknown'으로 정규화
    reg = regime_for_scaler(mat, {"A": 1.0}, detector=lambda r: {"current_regime": "martian_vibes"})
    assert reg["current_regime"] == "unknown"
    res = scale_allocation(_alloc({"A": 1.0}), mat, regime=reg, ts="T")
    assert res.regime_multiplier == 0.5                # 안전(보수) 배수


def test_detector_error_safe_fallback():
    mat = FakeMatrix({"A": _ret(0.012)})
    def boom(r):
        raise RuntimeError("hmm blew up")
    reg = regime_for_scaler(mat, {"A": 1.0}, detector=boom)
    assert reg["current_regime"] == "unknown"
    assert "detector_error" in reg["reason"]


def test_insufficient_history_regime_unknown():
    short = [f"2026-01-{1+i:02d}" for i in range(10)]
    mat = FakeMatrix({"A": _ret(0.012)[:10]}, dates=short)
    reg = detect_portfolio_regime(mat, {"A": 1.0}, min_obs=30,
                                  detector=lambda r: {"current_regime": "bull_low_vol"})
    assert reg["current_regime"] == "unknown"          # 관측<min_obs → 탐지 안 함
    assert "insufficient_history" in reg["reason"]


# ── 결정성 · no-lookahead ────────────────────────────────────
def test_deterministic():
    mat = FakeMatrix({"A": _ret(0.012)})
    det = lambda r: {"current_regime": "bull_high_vol"}
    a = regime_for_scaler(mat, {"A": 1.0}, detector=det)
    b = regime_for_scaler(mat, {"A": 1.0}, detector=det)
    assert a == b


def test_no_lookahead_detector_sees_only_past():
    captured = {}
    def det(returns):
        captured["n"] = len(returns)
        return {"current_regime": "bull_low_vol"}
    base = _ret(0.012)
    mat = FakeMatrix({"A": base})
    detect_portfolio_regime(mat, {"A": 1.0}, as_of=DATES[19], min_obs=10, detector=det)  # 20일까지
    assert captured["n"] == 20                          # detector는 as_of 이하만 봄


# ── 실 HMM 통합 스모크(설치 시) ──────────────────────────────
def test_real_hmm_returns_known_vocab():
    pytest.importorskip("hmmlearn")
    # 전반 저변동 상승 + 후반 고변동 하락 → 실 HMM 실행(결정적 random_state=42)
    up = [0.004 if i % 2 == 0 else -0.002 for i in range(30)]
    down = [-0.03 if i % 2 == 0 else 0.025 for i in range(30)]
    dates = [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(60)]
    mat = FakeMatrix({"A": up + down}, dates=dates)
    reg = detect_portfolio_regime(mat, {"A": 1.0}, method="hmm", min_obs=30)
    assert reg["current_regime"] in (
        "bull_low_vol", "bull_high_vol", "bear_low_vol", "bear_high_vol", "unknown")
    # 라벨이 스케일러 배수 테이블에 있음(unknown 포함)
    res = scale_allocation(_alloc({"A": 1.0}), mat, regime=reg, ts="T")
    assert 0.0 <= res.regime_multiplier <= 1.0
