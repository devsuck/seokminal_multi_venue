"""Paper Risk Monitoring (P6.3) — drawdown/노출드리프트/스테일가격/이상회전율. 결정적.

PaperRiskReport 반환. 읽기전용 — 리스크 거버너 무수정, 게이트웨이 무호출.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from jarvis.paper_execution.market_data import price_age_hours


@dataclass(frozen=True)
class RiskThresholds:
    max_drawdown: float = 0.20        # 초과 = 경고
    max_gross_exposure: float = 1.5
    max_turnover: float = 3.0
    stale_price_hours: float = 24.0


@dataclass(frozen=True)
class PaperRiskReport:
    timestamp: str
    drawdown: float
    gross_exposure: float
    net_exposure: float
    turnover: float
    stale_prices: int
    warnings: list = field(default_factory=list)
    health: str = "OK"

    def to_dict(self) -> dict:
        return asdict(self)


def monitor(now: str, provider=None, capital: float = None,
            thresholds: RiskThresholds | None = None) -> PaperRiskReport:
    from jarvis.paper_execution.ledger import current_positions
    from jarvis.paper_execution.models import PAPER_CAPITAL
    from jarvis.paper_execution.performance import attribution_current
    from jarvis.paper_execution.valuation import valuate_current
    t = thresholds or RiskThresholds()
    capital = PAPER_CAPITAL if capital is None else capital

    snap = valuate_current(now, provider=provider, capital=capital, commit=False)
    attr = attribution_current(now, capital)

    # 스테일 가격: 결측(stale_symbols) + 오래된 timestamp
    positions = list(current_positions().values())
    stale = set(snap.stale_symbols)
    if provider is not None:
        for p in positions:
            s = provider.get(p["strategy_id"], now)
            age = price_age_hours(s, now)
            if age is not None and age > t.stale_price_hours:
                stale.add(p["strategy_id"])

    warnings = []
    if snap.drawdown > t.max_drawdown:
        warnings.append(f"large_drawdown({round(snap.drawdown, 4)}>{t.max_drawdown})")
    if snap.gross_exposure > t.max_gross_exposure:
        warnings.append(f"exposure_drift(gross={snap.gross_exposure}>{t.max_gross_exposure})")
    if attr["turnover"] > t.max_turnover:
        warnings.append(f"abnormal_turnover({attr['turnover']}>{t.max_turnover})")
    if stale:
        warnings.append(f"stale_prices({len(stale)}): {sorted(stale)}")

    return PaperRiskReport(
        timestamp=now, drawdown=snap.drawdown, gross_exposure=snap.gross_exposure,
        net_exposure=snap.net_exposure, turnover=attr["turnover"], stale_prices=len(stale),
        warnings=warnings, health="OK" if not warnings else "WARN")
