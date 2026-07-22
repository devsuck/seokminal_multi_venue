"""Paper Execution 검증 (P6.2) — 원장에서 포지션 결정적 재구축 + 스냅샷 일치."""
from __future__ import annotations

from jarvis.paper_execution import ledger
from jarvis.paper_execution.models import apply_fill, zero_position


def rebuild_positions() -> dict:
    """orders+fills 원장에서 포지션 결정적 재구축. 반환: {strategy: PaperPosition dict}."""
    orders = {o["order_id"]: o for o in ledger.read_orders()}
    pos: dict = {}
    # fill 순서 = 원장 append 순서(결정적)
    for f in ledger.read_fills():
        o = orders.get(f["order_id"])
        if not o:
            continue
        strat = o["strategy_id"]
        cur = pos.get(strat) or zero_position(strat)
        cur = apply_fill(cur, o["side"], f["quantity"], f["simulated_price"])
        pos[strat] = cur
    return {s: p.to_dict() for s, p in pos.items()}


def verify() -> dict:
    """재구축 포지션(qty/realized) == 저장 스냅샷인지 확인."""
    rebuilt = rebuild_positions()
    stored = ledger.current_positions()
    keys = set(rebuilt) | set(stored)
    mismatches = []
    for k in sorted(keys):
        r = rebuilt.get(k, {})
        s = stored.get(k, {})
        if (round(r.get("quantity", 0), 6) != round(s.get("quantity", 0), 6)
                or round(r.get("realized_pnl", 0), 4) != round(s.get("realized_pnl", 0), 4)):
            mismatches.append(k)
    return {"ok": not mismatches, "deterministic": not mismatches,
            "n_strategies": len(keys), "mismatches": mismatches}
