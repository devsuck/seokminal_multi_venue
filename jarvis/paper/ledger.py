"""Paper Ledger — 내부 시뮬 체결 원장. append-only. live 자본 0.

권한: PAPER_ONLY. paper_active/paper_candidate 전략만. 실제 브로커 안 씀.
(나중에 페이퍼 브로커 연결은 선택 — 지금은 결정적 내부 원장.)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from jarvis.agents import PAPER_AGENT
from jarvis.config import state_path
from jarvis.permissions import require

_LEDGER = "paper_ledger.jsonl"
_ALLOWED_STATUS = {"paper_candidate", "paper_candidate_forward_test_required", "paper_active"}


class PaperLedger:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or state_path(_LEDGER)

    def _append(self, row: dict) -> dict:
        row = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **row}
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        return row

    def all(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        with open(self.path) as f:
            return [json.loads(ln) for ln in f if ln.strip()]

    def _guard(self, strategy_id: str) -> None:
        from jarvis.registry import StrategyRegistry
        st = StrategyRegistry().state(strategy_id)
        if st is None or st["status"] not in _ALLOWED_STATUS:
            raise PermissionError(f"{strategy_id}: 페이퍼 원장 불가(상태 {st['status'] if st else 'none'})")

    def create_entry(self, strategy_id: str, symbol: str, side: str, qty: float, price: float) -> dict:
        require(PAPER_AGENT, "create_paper_order", strategy_id)
        self._guard(strategy_id)
        return self._append({"kind": "entry", "strategy_id": strategy_id, "symbol": symbol,
                             "side": side, "qty": qty, "price": price, "capital": "paper"})

    def create_exit(self, strategy_id: str, symbol: str, qty: float, price: float, pnl: float) -> dict:
        require(PAPER_AGENT, "record_paper_fill", strategy_id)
        self._guard(strategy_id)
        return self._append({"kind": "exit", "strategy_id": strategy_id, "symbol": symbol,
                             "qty": qty, "price": price, "pnl": pnl, "capital": "paper"})

    def summary(self, strategy_id: str) -> dict:
        rows = [r for r in self.all() if r.get("strategy_id") == strategy_id]
        pnl = sum(r.get("pnl", 0.0) for r in rows if r.get("kind") == "exit")
        return {"strategy_id": strategy_id, "entries": sum(1 for r in rows if r["kind"] == "entry"),
                "exits": sum(1 for r in rows if r["kind"] == "exit"), "paper_pnl": round(pnl, 4)}
