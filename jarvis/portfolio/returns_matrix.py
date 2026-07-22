"""Strategy Return Matrix Layer — 이질적 전략 수익을 포트폴리오-호환 일별 시계열로 표준화.

문제: 전략마다 수익 성격이 다름 — 이벤트(buyback: 20일 보유 후 실현), 일별(tom),
선물(tsmom: 일별 MTM). 그대로 합치면 정렬·상관·배분 불가.

해법(어댑터만, 전략 무수정): 두 변환 모드.
  - **realized_at_exit** — 실현수익을 청산일에 계상(가격데이터 불필요, no-lookahead).
    이벤트 전략의 정직한 실현 현금흐름 캘린더.
  - **mtm** — price_provider 주입 시 보유 포지션의 일별 mark-to-market(선물/일별용).

출력: StrategyReturnSeries{strategy_id, dates, returns, equity_curve, exposure}.
정렬: 공통 영업일 캘린더(비활동일 = 0수익 flat). 상관계산은 backtest 모듈과 일치.

P2 Meta Portfolio 입력 인터페이스 — **배분 로직은 여기 없음(별도 P2).**
"""
from __future__ import annotations

import datetime as _dt
from bisect import bisect_left
from dataclasses import asdict, dataclass, field
from typing import Callable, Protocol


# ── 캘린더 유틸 ──────────────────────────────────────────────
def business_days(start: str, end: str) -> list[str]:
    """[start, end] 영업일(월~금) ISO 날짜. KRX 휴장일 미반영(근사)."""
    d = _dt.date.fromisoformat(start)
    last = _dt.date.fromisoformat(end)
    out = []
    while d <= last:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += _dt.timedelta(days=1)
    return out


def _snap_ge(cal: list[str], date: str) -> str | None:
    """cal에서 date 이상인 첫 날짜(없으면 None)."""
    i = bisect_left(cal, date)
    return cal[i] if i < len(cal) else None


# ── 자료형 ───────────────────────────────────────────────────
@dataclass(frozen=True)
class Position:
    """정규화 포지션. realized_return은 청산시점에만 알려짐(None=미청산)."""
    instrument: str
    entry_date: str
    exit_date: str            # 실현/예정 청산일(exposure 창 종료)
    realized_return: float | None = None
    direction: int = 1


@dataclass(frozen=True)
class StrategyReturnSeries:
    strategy_id: str
    dates: list[str]
    returns: list[float]
    equity_curve: list[float]
    exposure: list[float]
    active: bool
    method: str
    source: str = ""
    meta: dict = field(default_factory=dict)

    def rows(self) -> list[dict]:
        """요청 스키마대로 per-date 행: {strategy_id, date, return, equity_curve, exposure}."""
        return [{"strategy_id": self.strategy_id, "date": d, "return": r,
                 "equity_curve": e, "exposure": x}
                for d, r, e, x in zip(self.dates, self.returns, self.equity_curve, self.exposure)]

    def summary(self) -> dict:
        d = asdict(self)
        d.pop("returns"); d.pop("equity_curve"); d.pop("exposure"); d.pop("dates")
        return {**d, "n_dates": len(self.dates),
                "final_equity": self.equity_curve[-1] if self.equity_curve else 1.0,
                "avg_exposure": round(sum(self.exposure) / len(self.exposure), 4) if self.exposure else 0.0}


def _equity(returns: list[float]) -> list[float]:
    eq, cur = [], 1.0
    for r in returns:
        cur *= (1.0 + r)
        eq.append(round(cur, 8))
    return eq


# ── 수익 소스(전략 타입별 어댑터) ───────────────────────────
class ReturnSource(Protocol):
    strategy_id: str

    def daily(self, calendar: list[str], capacity: float) -> tuple[list[float], list[float]]:
        """(returns, exposure) — calendar에 정렬. 둘 다 no-lookahead."""

    def span(self) -> tuple[str, str] | None:
        """(min_date, max_date) 활동범위(없으면 None)."""


class EventReturnSource:
    """이벤트/보유창 전략 — realized_at_exit. 겹침 포지션 = 청산일 평균, exposure=동시보유수."""
    method = "realized_at_exit"

    def __init__(self, strategy_id: str, positions: list[Position], source: str = "") -> None:
        self.strategy_id = strategy_id
        self.positions = positions
        self.source = source

    def span(self) -> tuple[str, str] | None:
        if not self.positions:
            return None
        lo = min(p.entry_date for p in self.positions)
        hi = max(p.exit_date for p in self.positions)
        return lo, hi

    def daily(self, calendar: list[str], capacity: float) -> tuple[list[float], list[float]]:
        n = len(calendar)
        active = [0] * n
        realized: dict[str, list[float]] = {}
        for p in self.positions:
            for i, d in enumerate(calendar):
                if p.entry_date <= d < p.exit_date:   # 보유창(진입 포함, 청산 제외)
                    active[i] += 1
            if p.realized_return is not None:
                day = _snap_ge(calendar, p.exit_date)  # 청산일에 실현 계상(no-lookahead)
                if day is not None:
                    realized.setdefault(day, []).append(p.realized_return * p.direction)
        returns = [round(sum(realized[d]) / len(realized[d]), 8) if d in realized else 0.0
                   for d in calendar]
        expo = [round(min(1.0, active[i] / capacity), 6) for i in range(n)]
        return returns, expo


class MTMReturnSource:
    """일별/선물 전략 — mark-to-market. price_provider(inst, date)->price 필요.

    없으면 inactive(정직). 있으면 보유 포지션의 일별 수익(prev/cur 가격만 = no-lookahead).
    """
    method = "mtm"

    def __init__(self, strategy_id: str, positions: list[Position],
                 price_provider: Callable[[str, str], float | None] | None = None,
                 source: str = "") -> None:
        self.strategy_id = strategy_id
        self.positions = positions
        self.price_provider = price_provider
        self.source = source

    def span(self) -> tuple[str, str] | None:
        if not self.positions:
            return None
        return (min(p.entry_date for p in self.positions),
                max(p.exit_date for p in self.positions))

    def daily(self, calendar: list[str], capacity: float) -> tuple[list[float], list[float]]:
        n = len(calendar)
        active = [0] * n
        for p in self.positions:
            for i, d in enumerate(calendar):
                if p.entry_date <= d < p.exit_date:
                    active[i] += 1
        expo = [round(min(1.0, active[i] / capacity), 6) for i in range(n)]
        if self.price_provider is None:
            return [0.0] * n, expo  # 데이터 미배선 = inactive
        returns = [0.0] * n
        for i in range(1, n):
            d, prev = calendar[i], calendar[i - 1]
            held = [p for p in self.positions if p.entry_date <= d < p.exit_date]
            legs = []
            for p in held:
                p0 = self.price_provider(p.instrument, prev)
                p1 = self.price_provider(p.instrument, d)
                if p0 and p1 and p0 > 0:
                    legs.append((p1 / p0 - 1.0) * p.direction)
            if legs:
                returns[i] = round(sum(legs) / len(legs), 8)
        return returns, expo


# ── buyback 소스(기존 원장 → Position) ──────────────────────
def buyback_source(rows: list[dict] | None = None) -> EventReturnSource:
    """buyback 페이퍼 원장 → EventReturnSource. 청산분(pnl 有)만 실현수익."""
    from jarvis.fusion.adapters.base import add_business_days
    from jarvis.fusion.adapters.buyback import DEFAULT_HOLD_DAYS, _read_rows
    rows = rows if rows is not None else _read_rows()
    positions = []
    for r in rows:
        entry, code = r.get("entry_date"), r.get("stock_code")
        if not entry or not code:
            continue
        hold = int(r.get("hold_days") or DEFAULT_HOLD_DAYS)
        exit_ = r.get("exit_date") or add_business_days(entry, hold)
        pnl = r.get("pnl_pct")
        realized = float(pnl) if (r.get("exit_date") and pnl is not None) else None
        positions.append(Position(code, entry, exit_, realized, direction=1))
    return EventReturnSource("kr_dart_buyback_drift_v1", positions, source="buyback_bot_positions")


# ── Return Matrix ───────────────────────────────────────────
class ReturnMatrix:
    """여러 ReturnSource → 공통 캘린더 정렬 StrategyReturnSeries 집합."""

    def __init__(self, sources: list, capacity: float = 1.0) -> None:
        self.sources = sources
        self.capacity = capacity

    def calendar(self, override: list[str] | None = None) -> list[str]:
        if override is not None:
            return list(override)
        spans = [s.span() for s in self.sources]
        spans = [sp for sp in spans if sp]
        if not spans:
            return []
        lo = min(sp[0] for sp in spans)
        hi = max(sp[1] for sp in spans)
        return business_days(lo, hi)

    def build(self, calendar: list[str] | None = None) -> dict[str, StrategyReturnSeries]:
        cal = self.calendar(calendar)
        out: dict[str, StrategyReturnSeries] = {}
        for s in self.sources:
            returns, expo = s.daily(cal, self.capacity)
            active = any(x > 0 for x in expo)
            out[s.strategy_id] = StrategyReturnSeries(
                strategy_id=s.strategy_id, dates=cal, returns=returns,
                equity_curve=_equity(returns), exposure=expo, active=active,
                method=getattr(s, "method", "unknown"), source=getattr(s, "source", ""))
        return out

    def aligned(self, calendar: list[str] | None = None) -> tuple[list[str], dict[str, list[float]]]:
        """상관/배분용: 공통 캘린더 + active 전략의 수익 벡터."""
        series = self.build(calendar)
        cal = self.calendar(calendar)
        return cal, {sid: s.returns for sid, s in series.items() if s.active}

    def correlation(self, calendar: list[str] | None = None):
        """활동 전략 간 평균 페어 상관 — backtest 모듈과 동일 계산(일관성)."""
        from jarvis.fusion.backtest import avg_pairwise_corr
        _, series = self.aligned(calendar)
        return avg_pairwise_corr(series)
