"""Meta Portfolio Core (P2.1) — 배분 '제안'만. 자율집행/실행 없음.

입력: ReturnMatrix(P1.7) + 전략 메타 + 리스크 제약. 출력: AllocationProposal 집합.
v1 = 역변동성 가중 + 상관 페널티 + 리스크기여. (Black-Litterman/Kelly/RL 미구현.)

원칙: 결정적 · no-lookahead(as_of 이하만) · <2전략/불안정공분산 폴백 · 제안전용.
집행·리스크거버너 무수정 — 이 모듈은 계산+제안만. 승인/집행은 기존 게이트가 별도.
"""
from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field

_EPS = 1e-12


# ── 자료형 ───────────────────────────────────────────────────
@dataclass(frozen=True)
class RiskConstraints:
    max_weight: float = 1.0          # 전략별 상한
    min_weight: float = 0.0
    corr_penalty: float = 0.5        # 상관 페널티 강도(0=없음)
    min_obs: int = 20                # 포함 최소 관측수
    max_corr_threshold: float = 0.98  # 이 이상 = 불안정(near-collinear) → 등가중 폴백


@dataclass(frozen=True)
class AllocationProposal:
    strategy_id: str
    target_weight: float
    expected_risk: float             # w_i · σ_i (포트 내 기대 리스크, periodic)
    risk_contribution: float         # 포트 분산 기여 분율(합 1)
    rationale: str
    timestamp: str


@dataclass(frozen=True)
class AllocationResult:
    proposals: list[AllocationProposal]
    method: str                      # inverse_vol_corr_penalty | equal_weight_fallback | single_strategy | empty
    portfolio_risk: float | None     # periodic σ_p
    timestamp: str
    diagnostics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# ── 선형대수(순수 stdlib) ────────────────────────────────────
def _cov(a: list[float], b: list[float]) -> float:
    return statistics.covariance(a, b)


def _cov_matrix(ids: list[str], series: dict[str, list[float]]) -> dict:
    m: dict = {i: {} for i in ids}
    for x, i in enumerate(ids):
        for j in ids[x:]:
            c = statistics.variance(series[i]) if i == j else _cov(series[i], series[j])
            m[i][j] = m[j][i] = c
    return m


def _sigma(cov: dict, ids: list[str]) -> dict:
    return {i: max(0.0, cov[i][i]) ** 0.5 for i in ids}


def _corr(cov: dict, sig: dict, i: str, j: str) -> float:
    denom = sig[i] * sig[j]
    return (cov[i][j] / denom) if denom > _EPS else 0.0


def _portfolio_var(ids, cov, w: dict) -> float:
    return sum(w[i] * w[j] * cov[i][j] for i in ids for j in ids)


def _sigma_w(ids, cov, w: dict, i: str) -> float:
    return sum(w[j] * cov[i][j] for j in ids)


def _apply_caps(ids: list[str], w: dict, lo: float, hi: float) -> dict:
    """가중치를 [lo,hi]로 water-filling 후 재정규화(합 1)."""
    w = dict(w)
    fixed: dict[str, float] = {}
    for _ in range(len(ids) + 1):
        free = [i for i in ids if i not in fixed]
        if not free:
            break
        rem = 1.0 - sum(fixed.values())
        s = sum(w[i] for i in free) or 1.0
        changed = False
        for i in free:
            nv = w[i] / s * rem
            if nv > hi + 1e-15:
                w[i] = hi; fixed[i] = hi; changed = True
            elif nv < lo - 1e-15:
                w[i] = lo; fixed[i] = lo; changed = True
        if not changed:
            for i in free:
                w[i] = w[i] / s * rem
            break
    return w


# ── Allocator ────────────────────────────────────────────────
class InverseVolCorrelationAllocator:
    """v1 — 역변동성 × 상관페널티. 제안만."""
    method = "inverse_vol_corr_penalty"

    def __init__(self, constraints: RiskConstraints | None = None) -> None:
        self.c = constraints or RiskConstraints()

    def _equal_weight(self, ids, cov, reason, ts, metadata) -> AllocationResult:
        n = len(ids)
        w = _apply_caps(ids, {i: 1.0 / n for i in ids}, self.c.min_weight, self.c.max_weight)
        return self._finalize(ids, cov, w, "equal_weight_fallback", ts, metadata, extra_reason=reason)

    def _finalize(self, ids, cov, w, method, ts, metadata, extra_reason="") -> AllocationResult:
        sig = _sigma(cov, ids)
        pvar = max(0.0, _portfolio_var(ids, cov, w))
        pvol = pvar ** 0.5
        proposals = []
        for i in ids:
            rc = (w[i] * _sigma_w(ids, cov, w, i) / pvar) if pvar > _EPS else (1.0 / len(ids))
            meta_txt = ""
            if metadata and i in metadata:
                fam = metadata[i].get("family") or metadata[i].get("asset_class")
                meta_txt = f" [{fam}]" if fam else ""
            rationale = f"{method}{meta_txt}: w={round(w[i],4)} σ={round(sig[i],6)} RC={round(rc,4)}"
            if extra_reason:
                rationale += f" ({extra_reason})"
            proposals.append(AllocationProposal(
                strategy_id=i, target_weight=round(w[i], 6),
                expected_risk=round(w[i] * sig[i], 8), risk_contribution=round(rc, 6),
                rationale=rationale, timestamp=ts))
        return AllocationResult(
            proposals=sorted(proposals, key=lambda p: -p.target_weight),
            method=method, portfolio_risk=round(pvol, 8), timestamp=ts,
            diagnostics={"n_strategies": len(ids), "strategy_ids": ids,
                         "sigma": {i: round(sig[i], 8) for i in ids},
                         "reason": extra_reason})

    def propose(self, matrix, as_of: str | None = None,
                metadata: dict | None = None, ts: str = "") -> AllocationResult:
        # no-lookahead: as_of 이하로 캘린더 절단 후 정렬 수익 추출
        cal = [d for d in matrix.calendar() if as_of is None or d <= as_of]
        _, raw = matrix.aligned(cal)
        series = {sid: r for sid, r in raw.items()
                  if sum(1 for _ in r) >= self.c.min_obs and statistics.pstdev(r) > _EPS}
        ids = sorted(series)
        n = len(ids)

        if n == 0:
            return AllocationResult([], "empty", None, ts,
                                    {"reason": "no_active_strategy_with_min_obs"})
        if n == 1:
            i = ids[0]
            sig = statistics.stdev(series[i])
            w = min(1.0, self.c.max_weight)
            return AllocationResult(
                [AllocationProposal(i, round(w, 6), round(w * sig, 8), 1.0,
                                    f"single_strategy_fallback: w={round(w,4)} σ={round(sig,6)}", ts)],
                "single_strategy", round(w * sig, 8), ts,
                {"n_strategies": 1, "strategy_ids": ids, "reason": "single_strategy"})

        cov = _cov_matrix(ids, series)
        sig = _sigma(cov, ids)

        # 불안정 공분산 → 등가중 폴백
        min_sig = min(sig.values())
        max_abs_corr = max((abs(_corr(cov, sig, ids[a], ids[b]))
                            for a in range(n) for b in range(a + 1, n)), default=0.0)
        if min_sig < _EPS or max_abs_corr > self.c.max_corr_threshold:
            return self._equal_weight(
                ids, cov, f"unstable_covariance(max|ρ|={round(max_abs_corr,4)})", ts, metadata)

        # 역변동성 + 상관 페널티
        raw_w = {}
        for a, i in enumerate(ids):
            avg_abs_corr = statistics.mean(
                abs(_corr(cov, sig, i, ids[b])) for b in range(n) if ids[b] != i)
            penalty = 1.0 + self.c.corr_penalty * avg_abs_corr
            raw_w[i] = (1.0 / sig[i]) / penalty
        total = sum(raw_w.values())
        w = {i: raw_w[i] / total for i in ids}
        w = _apply_caps(ids, w, self.c.min_weight, self.c.max_weight)

        if _portfolio_var(ids, cov, w) <= _EPS:
            return self._equal_weight(ids, cov, "degenerate_portfolio_variance", ts, metadata)
        return self._finalize(ids, cov, w, self.method, ts, metadata)


def propose_allocation(matrix, constraints: RiskConstraints | None = None,
                       as_of: str | None = None, metadata: dict | None = None,
                       ts: str = "") -> AllocationResult:
    """편의 진입점 — 배분 제안 계산(기록 안 함; 기록은 allocation_ledger.write_proposal)."""
    return InverseVolCorrelationAllocator(constraints).propose(matrix, as_of, metadata, ts)
