"""`python -m jarvis.portfolio <cmd>` — Return Matrix CLI 검증.

  matrix   실 buyback 원장 → StrategyReturnSeries 요약 + 상관(활동전략)
"""
from __future__ import annotations

import argparse
import json


def _cmd_matrix() -> int:
    from jarvis.portfolio.returns_matrix import ReturnMatrix, buyback_source
    m = ReturnMatrix([buyback_source()], capacity=1.0)
    series = m.build()
    cal = m.calendar()
    out = {
        "n_dates": len(cal),
        "calendar_span": [cal[0], cal[-1]] if cal else None,
        "strategies": {sid: s.summary() for sid, s in series.items()},
        "active_strategies": [sid for sid, s in series.items() if s.active],
        "avg_pairwise_correlation": m.correlation(),
        "note": "P1.7 표준화 레이어 — 배분 없음. P2 Meta Portfolio 입력용.",
    }
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_allocate(write: bool) -> int:
    from datetime import datetime, timezone
    from jarvis.portfolio.allocator import RiskConstraints, propose_allocation
    from jarvis.portfolio.returns_matrix import ReturnMatrix, buyback_source
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    m = ReturnMatrix([buyback_source()], capacity=1.0)
    res = propose_allocation(m, RiskConstraints(), ts=ts)
    out = res.to_dict()
    out["note"] = "제안 전용 — 집행 아님. 활동 전략 <2면 폴백."
    if write:
        from jarvis.portfolio.allocation_ledger import write_proposal
        out["ledger"] = write_proposal(res)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_scale(regime: str | None, auto_regime: bool, quality_gate: bool) -> int:
    from datetime import datetime, timezone
    from jarvis.portfolio.allocator import RiskConstraints, propose_allocation
    from jarvis.portfolio.returns_matrix import ReturnMatrix, buyback_source
    from jarvis.portfolio.risk_scaler import scale_allocation
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    m = ReturnMatrix([buyback_source()], capacity=1.0)
    alloc = propose_allocation(m, RiskConstraints(), ts=ts)
    weights = {p.strategy_id: p.target_weight for p in alloc.proposals}
    reg = regime
    if auto_regime:
        from jarvis.portfolio.regime import regime_for_scaler
        reg = regime_for_scaler(m, weights, method="hmm")
    qrep = None
    if quality_gate:
        from jarvis.portfolio.risk_quality import check_matrix
        qrep = check_matrix(m)
    scaled = scale_allocation(alloc, m, regime=reg, ts=ts, quality=qrep)
    out = scaled.to_dict()
    if isinstance(reg, dict):
        out["regime_detected"] = reg
    if qrep is not None:
        out["quality"] = {"mode": qrep.recommended_mode, "confidence": qrep.confidence_score,
                          "valid": qrep.valid}
    out["note"] = "제안 전용 — 집행 아님. gross = vol-target×dd×regime, 품질게이팅 반영."
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_rebalance(write: bool) -> int:
    from datetime import datetime, timezone
    from jarvis.portfolio.allocator import RiskConstraints, propose_allocation
    from jarvis.portfolio.decision_engine import CurrentPortfolio, propose_rebalance
    from jarvis.portfolio.returns_matrix import ReturnMatrix, buyback_source
    from jarvis.portfolio.risk_scaler import scale_allocation
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    now = ts[:10]
    m = ReturnMatrix([buyback_source()], capacity=1.0)
    alloc = propose_allocation(m, RiskConstraints(), ts=ts)
    scaled = scale_allocation(alloc, m, ts=ts)
    # 현재 보유 미상 → 보수 폴백 시연(실운영은 실제 holdings 주입)
    cur = CurrentPortfolio({}, known=False)
    dec = propose_rebalance(scaled, cur, now=now, ts=ts)
    out = dec.to_dict()
    out["note"] = "제안 전용 — 주문 안 냄. 실 holdings 주입 시 delta/turnover/cost 계산."
    if write:
        from jarvis.portfolio.rebalance_ledger import write_proposal
        out["ledger"] = write_proposal(dec)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_quality() -> int:
    from jarvis.portfolio.returns_matrix import ReturnMatrix, buyback_source
    from jarvis.portfolio.risk_quality import check_matrix
    m = ReturnMatrix([buyback_source()], capacity=1.0)
    rep = check_matrix(m)
    print(json.dumps(rep.to_dict(), ensure_ascii=False, indent=2, default=str))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.portfolio")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("matrix")
    a = sub.add_parser("allocate")
    a.add_argument("--write", action="store_true")
    s = sub.add_parser("scale")
    s.add_argument("--regime", default=None)
    s.add_argument("--auto-regime", action="store_true")
    s.add_argument("--quality-gate", action="store_true")
    sub.add_parser("quality")
    rb = sub.add_parser("rebalance")
    rb.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "matrix":
        return _cmd_matrix()
    if args.cmd == "allocate":
        return _cmd_allocate(args.write)
    if args.cmd == "scale":
        return _cmd_scale(args.regime, args.auto_regime, args.quality_gate)
    if args.cmd == "quality":
        return _cmd_quality()
    if args.cmd == "rebalance":
        return _cmd_rebalance(args.write)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
