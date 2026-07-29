"""Post-Trade Analytics Engine (P8.7) — 완료된 집행의 TCA/품질/벤치마크 분석. **분석 전용.**

ExecutionData → PostTradeReport(벤치마크 + 메트릭). PortfolioExecutionSummary 집계.
**거래를 승인하지 않는다.** 상태: 필수 벤치마크(arrival) 누락 → FAILED, 선택 벤치마크 없음 →
WARNING, 그 외 PASS.

**MUST NOT: 주문 제출/취소/변경/집행/라우팅·브로커 호출·집행 게이트웨이/live/paper/risk거버너
import·포지션/포트폴리오/페이퍼/리스크/레지스트리 변경.** 읽기전용·결정적·append-only.
"""
from __future__ import annotations

import datetime as _dt

from jarvis.post_trade_analytics import benchmarks as B
from jarvis.post_trade_analytics import ledger
from jarvis.post_trade_analytics.models import (
    ExecutionData,
    FAILED,
    GENESIS,
    PASS,
    PortfolioExecutionSummary,
    PostTradeReport,
    WARNING,
    input_hash,
    overall_status,
    report_hash,
    report_id,
    summary_id,
)

_EPS = 1e-12
_BPS = 10_000.0


def _parse(ts: str):
    try:
        return _dt.datetime.fromisoformat((ts or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _median(xs: list) -> float:
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    return s[mid] if n % 2 else round((s[mid - 1] + s[mid]) / 2.0, 8)


class PostTradeAnalyticsEngine:
    """사후 집행분석기. 읽기전용·결정적."""

    def analyze(self, request_id: str, execution, now: str = "", *,
                report_type: str = "TCA", commit: bool = False) -> PostTradeReport:
        ex = execution.to_dict() if hasattr(execution, "to_dict") else (execution or {})
        side = ex.get("side", "")
        fills = ex.get("fills") or []
        warnings: list = []
        errors: list = []

        exec_price = B.vwap(fills)
        arrival = ex.get("arrival_price")
        decision = ex.get("decision_price")
        close = ex.get("close_price")
        mid = ex.get("mid_price") if ex.get("mid_price") is not None else arrival

        # ── 필수/선택 검증 ──
        if not ex or not request_id:
            errors.append("missing_execution")
        if not fills or exec_price is None:
            errors.append("missing_fills")
        if arrival is None:
            errors.append("missing_required_benchmark:arrival")
        for optname, val in (("decision_price", decision), ("close_price", close)):
            if val is None:
                warnings.append(f"benchmark_unavailable:{optname}")

        # ── 벤치마크 ──
        vwap_v = exec_price
        twap_v = B.twap(fills)
        diffs = {
            "arrival": B.slippage_bps(side, arrival, exec_price),
            "decision": B.slippage_bps(side, decision, exec_price),
            "vwap": B.slippage_bps(side, vwap_v, exec_price),
            "twap": B.slippage_bps(side, twap_v, exec_price),
            "close": B.slippage_bps(side, close, exec_price),
        }
        mkt_impact = B.market_impact_bps(side, arrival, exec_price)
        impl_shortfall = B.implementation_shortfall_bps(side, decision, exec_price)
        eff_spread = B.effective_spread_bps(exec_price, mid)
        real_spread = B.realized_spread_bps(side, exec_price, ex.get("future_mid_price"))
        total_q = B.total_quantity(fills)
        order_q = float(ex.get("order_quantity", 0.0)) or total_q
        unfilled = max(order_q - total_q, 0.0)
        opp_cost = B.opportunity_cost(side, unfilled, decision, close)
        price_impr = round(-mkt_impact, 8) if mkt_impact is not None else None
        slippage_attr = {"market_impact_bps": mkt_impact,
                         "spread_bps": round(eff_spread / 2.0, 8) if eff_spread is not None else None,
                         "timing_bps": (round(impl_shortfall - mkt_impact, 8)
                                        if impl_shortfall is not None and mkt_impact is not None else None)}
        cost_attr = dict(ex.get("cost_components") or {}) or {"slippage_bps": mkt_impact}

        benchmarks = {"arrival_price": arrival, "decision_price": decision, "vwap": vwap_v,
                      "twap": twap_v, "close_price": close, "execution_price": exec_price,
                      "benchmark_difference_bps": diffs,
                      "implementation_shortfall_bps": impl_shortfall,
                      "effective_spread_bps": eff_spread, "realized_spread_bps": real_spread,
                      "market_impact_bps": mkt_impact, "opportunity_cost": opp_cost,
                      "slippage_attribution": slippage_attr, "cost_attribution": cost_attr}

        # ── 메트릭 ──
        n_fills = B.dedup_fills(fills).__len__()
        avg_fill = round(total_q / n_fills, 8) if n_fills else 0.0
        fill_eff = round(_clamp(total_q / order_q, 0.0, 1.0), 8) if order_q > _EPS else 0.0
        partial_ratio = round((n_fills - 1) / n_fills, 8) if n_fills else 0.0
        dur = None
        d0, d1 = _parse(ex.get("start_time", "")), _parse(ex.get("end_time", ""))
        if d0 and d1:
            dur = round((d1 - d0).total_seconds(), 6)
        elif fills:
            ts = [f.get("timestamp", "") for f in B.dedup_fills(fills)]
            pd = [_parse(t) for t in ts if _parse(t)]
            if len(pd) >= 2:
                dur = round((max(pd) - min(pd)).total_seconds(), 6)
        vol = ex.get("market_volume")
        participation = round(order_q / float(vol), 8) if vol else None
        adverse = (round(real_spread - eff_spread, 8)
                   if real_spread is not None and eff_spread is not None else None)
        liquidity = round(_clamp(fill_eff, 0.0, 1.0), 8)
        exec_alpha = price_impr
        exec_beta = (round(mkt_impact / eff_spread, 8)
                     if mkt_impact is not None and eff_spread not in (None, 0) else 0.0)
        exec_score = (round(_clamp(100.0 - abs(mkt_impact), 0.0, 100.0), 8)
                      if mkt_impact is not None else 0.0)
        cost_breakdown = dict(ex.get("cost_components") or {}) or {"slippage_bps": mkt_impact}

        metrics = {"execution_price": exec_price, "average_fill_size": avg_fill,
                   "fill_efficiency": fill_eff, "partial_fill_ratio": partial_ratio,
                   "execution_duration_seconds": dur, "participation_rate": participation,
                   "price_improvement_bps": price_impr, "adverse_selection_bps": adverse,
                   "liquidity_score": liquidity, "execution_score": exec_score,
                   "execution_alpha_bps": exec_alpha, "execution_beta": exec_beta,
                   "cost_breakdown": cost_breakdown, "n_fills": n_fills,
                   "total_quantity": total_q, "unfilled_quantity": round(unfilled, 8)}

        # ── 상태 ──
        if errors:
            status = FAILED
        elif warnings:
            status = WARNING
        else:
            status = PASS
        score = exec_score if status != FAILED else 0.0

        ih = input_hash({"request_id": request_id, "execution": ex, "report_type": report_type})
        rid = report_id(request_id, report_type, ih)
        rh = report_hash(rid, request_id, report_type, status, score, benchmarks, metrics, ih)

        prev_hash = GENESIS
        if commit and not ledger.report_exists(rid):
            head = ledger.chain_head()
            prev_hash = head["report_hash"] if head else GENESIS
        report = PostTradeReport(
            report_id=rid, request_id=request_id, timestamp=now, report_type=report_type,
            overall_status=status, overall_score=score, benchmarks=benchmarks, metrics=metrics,
            warnings=warnings, errors=errors, input_hash=ih, report_hash=rh, previous_hash=prev_hash)
        if commit and not ledger.report_exists(rid):
            ledger.append_report(report.to_dict())
        return report

    # ── 포트폴리오 집계 ─────────────────────────────────────────
    def portfolio_summary(self, trades: list, period: str, now: str = "") -> PortfolioExecutionSummary:
        """trades: [{request_id, cost_bps, slippage_bps, fill_quality, success, broker, symbol, strategy}]."""
        costs = [float(t.get("cost_bps", 0.0)) for t in trades]
        slips = [float(t.get("slippage_bps", 0.0)) for t in trades]
        quals = [float(t.get("fill_quality", 0.0)) for t in trades]
        n = len(trades)
        avg_cost = round(sum(costs) / n, 8) if n else 0.0
        med_cost = round(_median(costs), 8) if n else 0.0
        worst = max(trades, key=lambda t: float(t.get("cost_bps", 0.0))) if n else {}
        best = min(trades, key=lambda t: float(t.get("cost_bps", 0.0))) if n else {}
        avg_slip = round(sum(slips) / n, 8) if n else 0.0
        avg_qual = round(sum(quals) / n, 8) if n else 0.0
        succ = round(sum(1 for t in trades if t.get("success")) / n, 8) if n else 0.0

        def _by(key):
            agg: dict = {}
            for t in trades:
                k = t.get(key, "")
                agg.setdefault(k, []).append(float(t.get("cost_bps", 0.0)))
            return {k: round(sum(v) / len(v), 8) for k, v in sorted(agg.items())}

        by_broker, by_symbol, by_strategy = _by("broker"), _by("symbol"), _by("strategy")
        ih = input_hash({"period": period, "trades": trades})
        sid = summary_id(period, ih)
        rh = report_hash(sid, "portfolio", "SUMMARY", "PASS", avg_cost,
                         {"by_broker": by_broker, "by_symbol": by_symbol, "by_strategy": by_strategy},
                         {"n": n, "avg_cost": avg_cost, "med_cost": med_cost}, ih)
        return PortfolioExecutionSummary(
            summary_id=sid, period=period, timestamp=now, n_trades=n, average_cost_bps=avg_cost,
            median_cost_bps=med_cost, worst_trade=worst, best_trade=best, average_slippage_bps=avg_slip,
            average_fill_quality=avg_qual, execution_success_rate=succ, cost_by_broker=by_broker,
            cost_by_symbol=by_symbol, cost_by_strategy=by_strategy, input_hash=ih, report_hash=rh)
