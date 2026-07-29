"""Risk Input Quality Layer (P2.25) — 포트폴리오 리스크 스케일러가 신뢰할 만한
입력을 받는지 검사. 제안전용·읽기전용·결정적.

탐지: 이벤트기반 sparse 수익 · 과도한 0수익 비율 · 비정상 변동성 · stale 데이터 ·
히스토리 부족. 출력: RiskQualityReport{valid, warnings, confidence_score, recommended_mode}.

recommended_mode ∈ {normal, conservative, exclude} — 스케일러가 이걸로 레버리지/보수화 게이팅.
"""
from __future__ import annotations

import datetime as _dt
import statistics
from dataclasses import asdict, dataclass, field

_EPS = 1e-12
_SEVERITY_PENALTY = {"high": 0.4, "medium": 0.2, "low": 0.1}
_CRITICAL = {"insufficient_history", "excessive_zero_ratio", "stale_data"}


@dataclass(frozen=True)
class RiskQualityConfig:
    min_history: int = 20
    sparse_zero_ratio: float = 0.5    # 이상 = event-based sparse(경고)
    max_zero_ratio: float = 0.7       # 초과 + 저노출 = 과도한 0수익(치명)
    abnormal_vol: float = 1.0         # 연율 변동성 이 초과 = 비정상
    stale_days: int = 30              # 마지막 활동 이 이상 오래 = stale
    ann_factor: int = 252


@dataclass(frozen=True)
class RiskQualityReport:
    valid: bool
    warnings: list[dict]
    confidence_score: float
    recommended_mode: str            # normal | conservative | exclude
    diagnostics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _days(a: str, b: str) -> int:
    return (_dt.date.fromisoformat(b) - _dt.date.fromisoformat(a)).days


def _finalize(warnings: list[dict], diag: dict) -> RiskQualityReport:
    score = 1.0
    for w in warnings:
        score -= _SEVERITY_PENALTY.get(w["severity"], 0.1)
    score = round(max(0.0, score), 4)
    codes = {w["code"] for w in warnings}
    critical = codes & _CRITICAL
    if critical:
        mode = "exclude"
    elif warnings:
        mode = "conservative"
    else:
        mode = "normal"
    return RiskQualityReport(valid=not critical, warnings=warnings,
                             confidence_score=score, recommended_mode=mode, diagnostics=diag)


def check_series(returns: list[float], dates: list[str] | None = None,
                 exposure: list[float] | None = None, as_of: str | None = None,
                 config: RiskQualityConfig | None = None,
                 label: str = "") -> RiskQualityReport:
    c = config or RiskQualityConfig()
    warnings: list[dict] = []

    def warn(code, severity, detail):
        warnings.append({"code": code, "severity": severity, "detail": detail,
                         **({"strategy_id": label} if label else {})})

    n = len(returns)
    if n < c.min_history:
        warn("insufficient_history", "high", f"n={n} < min_history={c.min_history}")

    zeros = sum(1 for r in returns if abs(r) < _EPS)
    zero_ratio = (zeros / n) if n else 1.0
    active_ratio = (sum(1 for x in exposure if x > _EPS) / len(exposure)
                    if exposure else None)
    if zero_ratio > c.max_zero_ratio:
        if active_ratio is not None and active_ratio > 0.5:
            warn("event_based_sparse", "medium",
                 f"zero_ratio={round(zero_ratio,3)} 이지만 exposure 활성(active={round(active_ratio,3)}) — 이벤트기반")
        else:
            warn("excessive_zero_ratio", "high",
                 f"zero_ratio={round(zero_ratio,3)} > {c.max_zero_ratio}, active={active_ratio}")
    elif zero_ratio > c.sparse_zero_ratio:
        warn("event_based_sparse", "medium", f"zero_ratio={round(zero_ratio,3)} > {c.sparse_zero_ratio}")

    nz = [r for r in returns if abs(r) >= _EPS]
    ann_vol = None
    if len(nz) >= 2:
        ann_vol = statistics.pstdev(returns) * (c.ann_factor ** 0.5)
        if ann_vol > c.abnormal_vol:
            warn("abnormal_volatility", "medium", f"ann_vol={round(ann_vol,3)} > {c.abnormal_vol}")

    # stale: 외부(as_of 대비 마지막 날짜) + 내부(마지막 비영수익 이후 경과)
    if dates and len(dates) == n and n:
        last_date = dates[-1]
        if as_of and _days(last_date, as_of) > c.stale_days:
            warn("stale_data", "high", f"last_date={last_date}, as_of={as_of} ({_days(last_date, as_of)}d)")
        last_nz = next((dates[i] for i in range(n - 1, -1, -1) if abs(returns[i]) >= _EPS), None)
        if last_nz and _days(last_nz, last_date) > c.stale_days:
            warn("stale_data", "high", f"마지막 활동 {last_nz} → 최신 {last_date} ({_days(last_nz, last_date)}d 무활동)")

    diag = {"n_obs": n, "zero_ratio": round(zero_ratio, 4),
            "active_ratio": round(active_ratio, 4) if active_ratio is not None else None,
            "ann_vol": round(ann_vol, 4) if ann_vol is not None else None}
    return _finalize(warnings, diag)


def check_strategy_series(series, as_of: str | None = None,
                          config: RiskQualityConfig | None = None) -> RiskQualityReport:
    """StrategyReturnSeries(P1.7) → 품질 리포트."""
    return check_series(series.returns, series.dates, series.exposure, as_of, config,
                        label=series.strategy_id)


def check_matrix(matrix, as_of: str | None = None,
                 config: RiskQualityConfig | None = None) -> RiskQualityReport:
    """ReturnMatrix 전체 → 전략별 검사 집계(최악 모드/최저 신뢰도)."""
    built = matrix.build()
    per: dict = {}
    all_warnings: list[dict] = []
    for sid, s in built.items():
        rep = check_strategy_series(s, as_of, config)
        per[sid] = rep.to_dict()
        all_warnings.extend(rep.warnings)
    rep = _finalize(all_warnings, {"per_strategy_modes": {k: v["recommended_mode"] for k, v in per.items()}})
    return RiskQualityReport(rep.valid, rep.warnings, rep.confidence_score,
                             rep.recommended_mode, {"per_strategy": per, **rep.diagnostics})
