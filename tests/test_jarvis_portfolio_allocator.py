"""P2.1 Meta Portfolio Core 테스트 — 제안전용 배분(역변동성+상관페널티+리스크기여).

케이스: 단일전략 · 무상관 2 · 강상관 · 결측데이터 · 공분산 불안정.
가드: 결정성 · no-lookahead · <2 폴백 · 불안정→등가중 · 원장 권한/감사.
"""
from __future__ import annotations

import os

import pytest

from jarvis.portfolio.allocator import (
    RiskConstraints,
    propose_allocation,
)


# 결정적 유사난수(LCG) — 시드로 상관 통제(Math.random 미사용)
def stream(seed: int, n: int = 24) -> list[float]:
    x = seed
    out = []
    for _ in range(n):
        x = (1103515245 * x + 12345) % (2 ** 31)
        out.append((x / 2 ** 31 - 0.5) * 0.02)
    return out


DATES = [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(24)]


class FakeMatrix:
    """allocator가 쓰는 최소 인터페이스(calendar/aligned)만 구현 — 수익 완전통제."""

    def __init__(self, series: dict[str, list[float]], dates=None) -> None:
        self._dates = dates or DATES
        self._series = series

    def calendar(self):
        return list(self._dates)

    def aligned(self, cal):
        idx = [self._dates.index(d) for d in cal]
        return cal, {sid: [r[i] for i in idx] for sid, r in self._series.items()}


def _weights(res):
    return {p.strategy_id: p.target_weight for p in res.proposals}


# ── 단일 전략 ────────────────────────────────────────────────
def test_single_strategy():
    res = propose_allocation(FakeMatrix({"A": stream(16)}), ts="T")
    assert res.method == "single_strategy"
    assert len(res.proposals) == 1
    assert res.proposals[0].target_weight == 1.0
    assert res.proposals[0].risk_contribution == 1.0


# ── 무상관 2전략 ─────────────────────────────────────────────
def test_two_uncorrelated():
    res = propose_allocation(FakeMatrix({"A": stream(16), "B": stream(24)}), ts="T")
    assert res.method == "inverse_vol_corr_penalty"
    w = _weights(res)
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert all(v > 0 for v in w.values())
    rc = sum(p.risk_contribution for p in res.proposals)
    assert abs(rc - 1.0) < 1e-6                          # 리스크기여 합 ≈ 1
    assert res.portfolio_risk is not None


# ── 강상관(안정, <0.98): 상관 페널티가 상관군 비중 축소 ──────
def test_correlation_penalty_reduces_correlated_cluster():
    f, ea, eb = stream(3), stream(4), stream(5)
    A = [f[i] + 0.4 * ea[i] for i in range(24)]          # A-B corr ~0.84
    B = [f[i] + 0.4 * eb[i] for i in range(24)]
    C = stream(7)                                        # 독립
    mat = FakeMatrix({"A": A, "B": B, "C": C})
    w_pen = _weights(propose_allocation(mat, RiskConstraints(corr_penalty=0.7), ts="T"))
    w_none = _weights(propose_allocation(mat, RiskConstraints(corr_penalty=0.0), ts="T"))
    # 페널티 켜면 독립 C 비중↑, 상관군(A+B) 비중↓
    assert w_pen["C"] > w_none["C"]
    assert (w_pen["A"] + w_pen["B"]) < (w_none["A"] + w_none["B"])


# ── 결측/부족 데이터 ─────────────────────────────────────────
def test_min_obs_short_matrix_returns_empty():
    # 캘린더가 짧아 관측<min_obs(20) → 전부 제외 → empty(크래시 없음)
    short = [f"2026-01-{1 + i:02d}" for i in range(10)]
    res = propose_allocation(FakeMatrix({"A": stream(16, 10), "B": stream(24, 10)},
                                        dates=short), ts="T")
    assert res.method == "empty"


def test_constant_strategy_excluded():
    const = [0.0] * 24
    res = propose_allocation(FakeMatrix({"A": stream(16), "FLAT": const}), ts="T")
    ids = [p.strategy_id for p in res.proposals]
    assert "FLAT" not in ids                              # 무분산 = 제외
    assert res.method == "single_strategy"


def test_no_active_strategy_returns_empty():
    res = propose_allocation(FakeMatrix({"FLAT": [0.0] * 24}), ts="T")
    assert res.method == "empty"
    assert res.proposals == []


# ── 공분산 불안정 → 등가중 폴백 ──────────────────────────────
def test_covariance_instability_equal_weight_fallback():
    s1 = stream(6)
    s2 = [x + 1e-7 for x in s1]                           # 거의 동일 → corr≈1
    res = propose_allocation(FakeMatrix({"A": s1, "B": s2}), ts="T")
    assert res.method == "equal_weight_fallback"
    w = _weights(res)
    assert abs(w["A"] - 0.5) < 1e-9 and abs(w["B"] - 0.5) < 1e-9
    assert "unstable_covariance" in res.diagnostics["reason"]


# ── 결정성 ───────────────────────────────────────────────────
def test_deterministic():
    mat = FakeMatrix({"A": stream(16), "B": stream(24), "C": stream(7)})
    r1 = propose_allocation(mat, ts="T")
    r2 = propose_allocation(mat, ts="T")
    assert [p.__dict__ for p in r1.proposals] == [p.__dict__ for p in r2.proposals]


# ── no-lookahead ─────────────────────────────────────────────
def test_no_lookahead_future_data_ignored():
    a_full = stream(16); b_full = stream(24)
    # as_of = 12번째 날. 이후 미래봉을 바꿔도 제안 동일해야.
    as_of = DATES[11]
    mat1 = FakeMatrix({"A": a_full, "B": b_full})
    a_tamper = a_full[:12] + [9.9] * 12                  # 미래 구간 오염
    b_tamper = b_full[:12] + [-9.9] * 12
    mat2 = FakeMatrix({"A": a_tamper, "B": b_tamper})
    r1 = propose_allocation(mat1, as_of=as_of, ts="T")
    r2 = propose_allocation(mat2, as_of=as_of, ts="T")
    assert [p.__dict__ for p in r1.proposals] == [p.__dict__ for p in r2.proposals]


# ── 최대 비중 캡 ─────────────────────────────────────────────
def test_max_weight_cap_respected():
    mat = FakeMatrix({"A": stream(16), "B": stream(24), "C": stream(7)})
    res = propose_allocation(mat, RiskConstraints(max_weight=0.4), ts="T")
    assert all(p.target_weight <= 0.4 + 1e-9 for p in res.proposals)
    assert abs(sum(p.target_weight for p in res.proposals) - 1.0) < 1e-6


# ── 원장 권한 + 감사 ─────────────────────────────────────────
def test_ledger_write_requires_permission_and_audits(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    import jarvis.audit.log as al
    import jarvis.portfolio.allocation_ledger as pl
    monkeypatch.setattr(al, "state_path", sp)
    monkeypatch.setattr(pl, "state_path", sp)

    res = propose_allocation(FakeMatrix({"A": stream(16), "B": stream(24)}), ts="T")
    out = pl.write_proposal(res)
    assert out["written"] is True
    rows = pl.read_latest()
    assert len(rows) == 1 and rows[0]["executed"] is False and rows[0]["capital"] == "proposal_only"
    audit = al.read_all()
    assert any(a.get("action") == "write_allocation_proposal" and a.get("result") == "written"
               for a in audit)
    assert any(a.get("action") == "propose_allocation" and a.get("result") == "allowed"
               for a in audit)
