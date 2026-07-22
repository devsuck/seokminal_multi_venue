"""Reconciliation Engine (P7.3) — 페이퍼/브로커/라이브 대조 + 드리프트 + 컨트롤이벤트.

**집행 아님·주문 없음·상태 변경 없음.** 읽기전용·결정적. 소스원장 무변경.
"""
from __future__ import annotations

from jarvis.reconciliation.models import (
    BROKER_UNAVAILABLE,
    CRITICAL,
    ControlEvent,
    DriftThresholds,
    NAV_DRIFT,
    OK,
    POSITION_DRIFT,
    PRICE_DRIFT,
    ReconciliationReport,
    STALE_DATA,
    WARNING,
    max_severity,
)

_EPS = 1e-9


def _paper_mark(pos: dict) -> float | None:
    qty = float(pos.get("quantity", 0.0))
    if abs(qty) < _EPS:
        return float(pos.get("average_price", 0.0)) or None
    return float(pos.get("market_value", 0.0)) / qty


class ReconciliationEngine:
    def __init__(self, thresholds: DriftThresholds | None = None) -> None:
        self.t = thresholds or DriftThresholds()

    def reconcile(self, paper_positions: list, broker_positions: list, *,
                  paper_nav: float | None = None, broker_equity: float | None = None,
                  live_provider=None, broker_health=None, now: str = "") -> ReconciliationReport:
        events: list[ControlEvent] = []
        paper = {p["strategy_id"]: p for p in paper_positions}
        broker = {}
        for b in broker_positions:
            d = b.to_dict() if hasattr(b, "to_dict") else b
            broker[d["symbol"]] = d

        # ── 브로커 가용성 ──
        health = broker_health.to_dict() if hasattr(broker_health, "to_dict") else (broker_health or {})
        connected = health.get("connected", broker_positions != [] or bool(broker))
        if broker_health is not None and not connected:
            events.append(ControlEvent(BROKER_UNAVAILABLE, CRITICAL,
                                       f"broker unavailable: {health.get('error')}", now, "broker"))
        elif health.get("stale"):
            events.append(ControlEvent(STALE_DATA, WARNING, "broker data stale", now, "broker"))

        matched = sorted(set(paper) & set(broker))
        missing_in_broker = sorted(set(paper) - set(broker))
        missing_in_paper = sorted(set(broker) - set(paper))

        # ── 포지션 드리프트 ──
        qty_diff: dict = {}
        avg_diff: dict = {}
        val_diff: dict = {}
        for sym in matched:
            p, b = paper[sym], broker[sym]
            dq = round(float(p.get("quantity", 0)) - float(b.get("quantity", 0)), 8)
            da = round(float(p.get("average_price", 0)) - float(b.get("avg_price", 0)), 6)
            dv = round(float(p.get("market_value", 0)) - float(b.get("market_value", 0)), 4)
            if abs(dq) > self.t.quantity_tol:
                qty_diff[sym] = dq
            if abs(da) > self.t.value_tol:
                avg_diff[sym] = da
            if abs(dv) > self.t.value_tol:
                val_diff[sym] = dv
        if qty_diff:
            events.append(ControlEvent(POSITION_DRIFT, WARNING,
                                       f"quantity mismatch: {qty_diff}", now, "engine"))
        for sym in missing_in_broker:
            events.append(ControlEvent(POSITION_DRIFT, WARNING,
                                       f"symbol in paper not broker: {sym}", now, "engine"))
        for sym in missing_in_paper:
            events.append(ControlEvent(POSITION_DRIFT, WARNING,
                                       f"symbol in broker not paper: {sym}", now, "engine"))

        # ── 가격 드리프트(페이퍼 마크 vs 라이브) ──
        if live_provider is not None:
            for sym in matched:
                tick = live_provider.latest(sym) if hasattr(live_provider, "latest") else None
                if tick is None:
                    events.append(ControlEvent(STALE_DATA, WARNING,
                                               f"missing live price: {sym}", now, "live"))
                    continue
                pm = _paper_mark(paper[sym])
                lp = float(tick.price)
                if pm and lp > _EPS:
                    drift = abs(pm / lp - 1.0)
                    if drift > self.t.price_drift_critical:
                        events.append(ControlEvent(PRICE_DRIFT, CRITICAL,
                                                   f"{sym} paper_mark {round(pm,4)} vs live {round(lp,4)} ({round(drift*100,2)}%)", now, "live"))
                    elif drift > self.t.price_drift_warn:
                        events.append(ControlEvent(PRICE_DRIFT, WARNING,
                                                   f"{sym} price drift {round(drift*100,2)}%", now, "live"))

        # ── NAV 드리프트 ──
        nav_difference = None
        if paper_nav is not None and broker_equity is not None:
            nav_difference = round(paper_nav - broker_equity, 4)
            if broker_equity > _EPS:
                nd = abs(nav_difference) / broker_equity
                if nd > self.t.nav_drift_critical:
                    events.append(ControlEvent(NAV_DRIFT, CRITICAL,
                                               f"NAV {round(paper_nav,2)} vs equity {round(broker_equity,2)} ({round(nd*100,2)}%)", now, "engine"))
                elif nd > self.t.nav_drift_warn:
                    events.append(ControlEvent(NAV_DRIFT, WARNING,
                                               f"NAV drift {round(nd*100,2)}%", now, "engine"))

        return ReconciliationReport(
            timestamp=now, matched_positions=matched, missing_in_broker=missing_in_broker,
            missing_in_paper=missing_in_paper, quantity_difference=qty_diff,
            average_price_difference=avg_diff, market_value_difference=val_diff,
            nav_difference=nav_difference, severity=max_severity(events),
            control_events=[e.to_dict() for e in events])


def reconcile_runtime(broker_provider, live_provider, now: str, capital: float | None = None,
                      thresholds: DriftThresholds | None = None, commit: bool = False):
    """런타임 통합(읽기전용) — 페이퍼 원장 + 브로커 + 라이브 → 리포트. 집행 없음."""
    from jarvis.paper_execution.ledger import current_positions
    from jarvis.paper_execution.models import PAPER_CAPITAL
    from jarvis.paper_execution.valuation import valuate
    cap = capital if capital is not None else PAPER_CAPITAL
    positions = list(current_positions().values())

    paper_nav = None
    if live_provider is not None:
        from jarvis.live_market_data.bridge import live_valuation_provider
        md = live_valuation_provider(live_provider, positions)
        paper_nav = valuate(positions, md, cap, now).nav

    bpos = broker_provider.positions() if broker_provider else []
    bhealth = broker_provider.health_check() if broker_provider else None
    bacct = broker_provider.account_snapshot() if broker_provider else None
    equity = bacct.equity if bacct else None

    report = ReconciliationEngine(thresholds).reconcile(
        positions, bpos, paper_nav=paper_nav, broker_equity=equity,
        live_provider=live_provider, broker_health=bhealth, now=now)
    if commit:
        from jarvis.reconciliation.ledger import record_report
        record_report(report)
    return report
