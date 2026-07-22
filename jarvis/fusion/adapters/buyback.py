"""Buyback 어댑터 — 페이퍼 포지션의 예정된 보유창을 롱 신호로 번역.

전략 로직 무수정. 신호원 = buyback 봇이 남긴 포지션의 entry_date/exit_date
(둘 다 진입시점에 확정되는 예정일 = time-stop). **pnl_pct/exit_price(결과데이터)는
절대 안 읽음** — 방향은 성과와 무관(no-lookahead 보증).

as_of에 롱(+1): entry_date <= as_of AND (exit_date 없음 OR as_of < exit_date).
동일 종목 다중 포지션이 겹치면 +1 하나로 dedup.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path
from jarvis.fusion.adapters.base import as_date
from jarvis.fusion.types import StrategySignal

STRATEGY_ID = "kr_dart_buyback_drift_v1"
_LEDGER = "buyback_bot_positions.jsonl"


def _read_rows() -> list[dict]:
    p = state_path(_LEDGER)
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


class BuybackPositionAdapter:
    strategy_id = STRATEGY_ID

    def __init__(self, rows: list[dict] | None = None) -> None:
        self._rows = rows  # 주입 시 파일 대신 사용(테스트)

    def _positions(self) -> list[dict]:
        return self._rows if self._rows is not None else _read_rows()

    def signals(self, as_of: str = "") -> list[StrategySignal]:
        d = as_date(as_of)
        if d is None:
            return []
        active: dict[str, dict] = {}
        for p in self._positions():
            entry = p.get("entry_date")
            exit_ = p.get("exit_date")
            code = p.get("stock_code")
            if not code or not entry:
                continue
            if entry > d:               # 진입 전 = 아직 알 수 없음(no-lookahead)
                continue
            if exit_ and d >= exit_:     # 예정 time-stop 도달 = 보유 종료
                continue
            active.setdefault(code, p)   # dedup: 종목당 하나
        out = []
        for code, p in sorted(active.items()):
            out.append(StrategySignal(
                strategy_id=self.strategy_id, instrument=code, direction=1, strength=1.0,
                as_of=as_of, source="buyback_bot_positions",
                meta={"corp": p.get("corp_name"), "entry_date": p.get("entry_date"),
                      "exit_date": p.get("exit_date")}))
        return out
