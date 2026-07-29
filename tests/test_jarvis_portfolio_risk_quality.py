"""P2.25 Risk Input Quality Layer 테스트.

탐지: 이벤트 sparse · 과도한 0비율 · 비정상 변동성 · stale · 히스토리 부족.
+ 스케일러 품질 게이팅(exclude→보수).
"""
from __future__ import annotations

from jarvis.portfolio.allocator import AllocationProposal, AllocationResult
from jarvis.portfolio.risk_quality import RiskQualityConfig, check_series
from jarvis.portfolio.risk_scaler import scale_allocation

DATES = [f"2026-01-{1 + i:02d}" for i in range(24)]


def _clean(n=24):
    return [0.01 if i % 2 == 0 else -0.008 for i in range(n)]


# ── 정상 ─────────────────────────────────────────────────────
def test_clean_series_valid_normal():
    rep = check_series(_clean(), DATES, as_of="2026-01-24")
    assert rep.valid is True
    assert rep.recommended_mode == "normal"
    assert rep.confidence_score == 1.0
    assert rep.warnings == []


# ── 히스토리 부족 ────────────────────────────────────────────
def test_insufficient_history():
    rep = check_series(_clean(5), DATES[:5])
    codes = {w["code"] for w in rep.warnings}
    assert "insufficient_history" in codes
    assert rep.valid is False and rep.recommended_mode == "exclude"


# ── 과도한 0수익(비활성) ─────────────────────────────────────
def test_excessive_zero_ratio_no_exposure():
    r = [0.0] * 20 + [0.01, -0.01, 0.02, 0.0]      # 대부분 0, 노출정보 없음
    rep = check_series(r, DATES)
    codes = {w["code"] for w in rep.warnings}
    assert "excessive_zero_ratio" in codes
    assert rep.valid is False


# ── 이벤트기반 sparse(0 많지만 보유중) ───────────────────────
def test_event_based_sparse_with_exposure():
    r = [0.0] * 20 + [0.05, 0.0, 0.0, -0.03]        # 0 많음
    expo = [1.0] * 24                                # 계속 보유중 → 이벤트기반
    rep = check_series(r, DATES, exposure=expo)
    codes = {w["code"] for w in rep.warnings}
    assert "event_based_sparse" in codes
    assert "excessive_zero_ratio" not in codes       # 노출 있으니 치명 아님
    assert rep.recommended_mode == "conservative"    # medium만 → conservative
    assert rep.valid is True


# ── 비정상 변동성 ────────────────────────────────────────────
def test_abnormal_volatility():
    r = [0.15 if i % 2 == 0 else -0.15 for i in range(24)]   # 초고변동
    rep = check_series(r, DATES, config=RiskQualityConfig(abnormal_vol=1.0))
    codes = {w["code"] for w in rep.warnings}
    assert "abnormal_volatility" in codes


# ── stale 데이터 ─────────────────────────────────────────────
def test_stale_data_external():
    rep = check_series(_clean(), DATES, as_of="2026-06-01")  # 마지막 1/24 vs 6/1
    codes = {w["code"] for w in rep.warnings}
    assert "stale_data" in codes
    assert rep.valid is False


def test_stale_data_internal_no_recent_activity():
    r = [0.01, -0.01, 0.02] + [0.0] * 21             # 초반만 활동, 이후 무활동
    rep = check_series(r, DATES, config=RiskQualityConfig(stale_days=10))  # 활동 1/3 → 최신 1/24(21d)
    codes = {w["code"] for w in rep.warnings}
    assert "stale_data" in codes


# ── 신뢰도 점수 단조 ─────────────────────────────────────────
def test_confidence_decreases_with_warnings():
    good = check_series(_clean(), DATES, as_of="2026-01-24").confidence_score
    bad = check_series([0.0] * 24, DATES).confidence_score
    assert good > bad


# ── 스케일러 품질 게이팅 ─────────────────────────────────────
class _FakeMatrix:
    def __init__(self, series):
        self._d = [f"2026-01-{1+i:02d}" for i in range(len(next(iter(series.values()))))]
        self._s = series

    def calendar(self):
        return list(self._d)

    def aligned(self, cal):
        idx = [self._d.index(d) for d in cal]
        return cal, {k: [v[i] for i in idx] for k, v in self._s.items()}


def _alloc(w):
    return AllocationResult([AllocationProposal(k, v, 0.0, v, "t", "T") for k, v in w.items()],
                            "t", None, "T")


def test_quality_exclude_forces_conservative_no_leverage():
    lowvol = [0.001 if i % 2 == 0 else -0.001 for i in range(24)]
    mat = _FakeMatrix({"A": lowvol})
    from jarvis.portfolio.risk_scaler import RiskScalingConfig
    cfg = RiskScalingConfig(max_leverage=3.0)         # 레버리지 허용
    from jarvis.portfolio.risk_quality import RiskQualityReport
    excl = RiskQualityReport(False, [{"code": "stale_data", "severity": "high"}], 0.2, "exclude")
    base = scale_allocation(_alloc({"A": 1.0}), mat, cfg, ts="T")
    gated = scale_allocation(_alloc({"A": 1.0}), mat, cfg, ts="T", quality=excl)
    assert base.gross_exposure > 1.0                  # 저변동성 → 레버리지
    assert gated.gross_exposure <= 1.0                # exclude → 무레버리지+보수
    assert gated.diagnostics["quality_mode"] == "exclude"


def test_quality_none_backward_compatible():
    mat = _FakeMatrix({"A": [0.012 if i % 2 == 0 else -0.012 for i in range(24)]})
    a = scale_allocation(_alloc({"A": 1.0}), mat, ts="T")
    b = scale_allocation(_alloc({"A": 1.0}), mat, ts="T", quality=None)
    assert a.to_dict() == b.to_dict()
