"""Paper Trading Runtime Loop (P6.5) — 읽기전용 결정적 런타임.

오케스트레이션: MarketDataProvider → Quality → Valuation → Attribution → Risk Monitor.
append-only paper_runtime_events.jsonl. 스케줄(manual/daily/interval). 실패 우아처리.

**절대 안 함: 집행 게이트웨이 호출·주문 생성·리스크거버너 수정·레지스트리 수정.**
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from dataclasses import asdict, dataclass, field

from jarvis.config import state_path

_RUNTIME = "paper_runtime_events.jsonl"


@dataclass(frozen=True)
class RuntimeConfig:
    frequency: str = "daily"       # manual | daily | weekly | interval
    interval_hours: float = 24.0
    capital: float | None = None
    stale_hours: float = 48.0


@dataclass(frozen=True)
class RuntimeEvent:
    timestamp: str
    valuation_status: str          # OK | FAILED | SKIPPED
    nav: float | None
    risk_status: str               # OK | WARN | UNKNOWN
    data_quality: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _hours(a: str, b: str) -> float | None:
    def _p(t):
        try:
            return _dt.datetime.fromisoformat((t or "").replace("Z", "+00:00"))
        except ValueError:
            return None
    da, db = _p(a), _p(b)
    return (db - da).total_seconds() / 3600.0 if da and db else None


# ── append-only 런타임 원장 ──
def read_runtime_events() -> list[dict]:
    p = state_path(_RUNTIME)
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def last_runtime_ts() -> str | None:
    rows = read_runtime_events()
    return rows[-1]["timestamp"] if rows else None


class PaperTradingRunner:
    def __init__(self, provider=None, config: RuntimeConfig | None = None) -> None:
        self.provider = provider
        self.c = config or RuntimeConfig()
        from jarvis.paper_execution.models import PAPER_CAPITAL
        self.capital = self.c.capital if self.c.capital is not None else PAPER_CAPITAL

    # ── 스케줄 판단 ──
    def should_run(self, now: str, last_run: str | None) -> bool:
        if self.c.frequency == "manual" or last_run is None:
            return True
        h = _hours(last_run, now)
        if h is None:
            return True
        if self.c.frequency == "daily":
            return h >= 24.0
        if self.c.frequency == "weekly":
            return h >= 168.0
        return h >= self.c.interval_hours    # interval

    def _default_provider(self, positions: list, now: str):
        from jarvis.market_data.bridge import paper_valuation_provider
        from jarvis.market_data.cache import CacheProvider
        return paper_valuation_provider(CacheProvider(), positions)

    def _quality(self, provider, symbols: list, now: str, warnings: list) -> dict:
        from jarvis.market_data.models import STALE
        ok = stale = fallback = missing = 0
        for s in symbols:
            snap = provider.get_price(s, now) if hasattr(provider, "get_price") else provider.get(s, now)
            if snap is None:
                missing += 1
                warnings.append(f"missing_price:{s}")
            elif getattr(snap, "source", "") == "flat_mark_fallback":
                fallback += 1
                warnings.append(f"no_market_data_fallback:{s}")
            elif getattr(snap, "quality", "OK") == STALE:
                stale += 1
                warnings.append(f"stale_price:{s}")
            else:
                ok += 1
        return {"n_symbols": len(symbols), "ok": ok, "stale": stale,
                "fallback": fallback, "missing": missing}

    # ── 1회 실행(수동) ──
    def run_once(self, now: str, commit: bool = False, provider=None) -> RuntimeEvent:
        warnings: list[str] = []
        try:
            from jarvis.paper_execution.ledger import current_positions
            positions = list(current_positions().values())
        except Exception as exc:  # noqa: BLE001 — 손상 상태 우아처리
            return RuntimeEvent(now, "FAILED", None, "UNKNOWN", {},
                                [f"corrupted_state:{exc}"], "positions_read_failed")

        symbols = [p["strategy_id"] for p in positions]
        prov = provider or self.provider or self._default_provider(positions, now)
        dq = self._quality(prov, symbols, now, warnings)

        try:
            from jarvis.paper_execution.valuation import _history_nav, valuate
            prev_nav, peak_nav = _history_nav()
            snap = valuate(positions, prov, self.capital, now, prev_nav, peak_nav)
        except Exception as exc:  # noqa: BLE001 — 밸류에이션 실패 우아처리
            return RuntimeEvent(now, "FAILED", None, "UNKNOWN", dq,
                                warnings + [f"valuation_error:{exc}"], "valuation_failed")

        try:
            from jarvis.paper_execution.ledger import read_fills
            from jarvis.paper_execution.monitoring import monitor
            monitor(now, provider=prov, capital=self.capital)  # 리스크 리포트(read-only)
            risk = monitor(now, provider=prov, capital=self.capital)
            warnings += risk.warnings
            risk_status = risk.health
        except Exception as exc:  # noqa: BLE001
            risk_status = "UNKNOWN"
            warnings.append(f"risk_monitor_error:{exc}")

        event = RuntimeEvent(now, "OK", snap.nav, risk_status, dq,
                             sorted(set(warnings)), "evaluated")
        if commit:
            self._commit(event, prov, now)
        return event

    # ── 스케줄 반영 실행 ──
    def run(self, now: str, commit: bool = False, provider=None) -> RuntimeEvent:
        if not self.should_run(now, last_runtime_ts()):
            return RuntimeEvent(now, "SKIPPED", None, "OK", {}, [], "not_due")
        return self.run_once(now, commit=commit, provider=provider)

    def _commit(self, event: RuntimeEvent, provider, now: str) -> None:
        from jarvis.agents import PAPER_EXECUTION_AGENT
        from jarvis.audit import record
        from jarvis.paper_execution.valuation import valuate_current
        from jarvis.permissions import require
        require(PAPER_EXECUTION_AGENT, "record_paper_runtime", event.timestamp)
        p = state_path(_RUNTIME)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a") as f:
            f.write(json.dumps({**event.to_dict(), "capital": "paper"},
                               ensure_ascii=False, default=str) + "\n")
        # NAV 스냅샷도 영속(drawdown 이력 축적) — 결정적 재계산
        valuate_current(now, provider=provider, capital=self.capital, commit=True,
                        principal=PAPER_EXECUTION_AGENT)
        record({"layer": "paper_execution", "action": "record_paper_runtime",
                "nav": event.nav, "valuation_status": event.valuation_status,
                "risk_status": event.risk_status, "result": "recorded"})
