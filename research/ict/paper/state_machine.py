"""FLAT/IN_POSITION 상태머신 — HTF 존 + LTF CISD + 반전형 오더플로우 트리거 컨플루언스로
진입, 스탑/다음 반대편 유동성 레벨 목표로 청산. 단일 포지션만 추적(겹치면 저널 채점이 꼬임)."""
from __future__ import annotations

from research.ict.paper.htf_zones import ZoneTracker
from research.ict.paper.journal_writer import append_trade_row
from research.ict.paper.position_state import (
    PositionState,
    clear_position_state,
    load_position_state,
    save_position_state,
)
from research.ict.primitives import cisd_events

# CISD와 반전형 트리거가 서로 이 봉 수 이내면 컨플루언스로 인정 — 임의 기본값,
# 30건 미만 표본에서는 튜닝하지 않는다(design spec 7절).
CONFLUENCE_WINDOW_BARS = 5

_TRIGGER_TO_ZONE_TYPE = {"buy": "bullish", "sell": "bearish"}


class PaperEngine:
    def __init__(self, symbol: str, state_path: str, journal_path: str) -> None:
        self.symbol = symbol
        self._state_path = state_path
        self._journal_path = journal_path
        self.zones = ZoneTracker()
        self._ltf_bars: list[dict] = []
        self._recent_ltf_triggers: list[dict] = []  # {"bar_index","of_trigger","side"}
        self.position: PositionState | None = load_position_state(state_path)

    def on_htf_bar(self, bar: dict) -> None:
        self.zones.update(bar)

    def on_ltf_bar(self, result: dict) -> None:
        """LTFBarBuilder._finalize()가 반환한 dict를 그대로 받는다."""
        bar = result["bar"]
        self._ltf_bars.append(bar)
        if len(self._ltf_bars) > 200:
            self._ltf_bars.pop(0)
            self._recent_ltf_triggers = [
                {**t, "bar_index": t["bar_index"] - 1} for t in self._recent_ltf_triggers if t["bar_index"] > 0
            ]

        if result["of_trigger"] is not None:
            self._recent_ltf_triggers.append({
                "bar_index": len(self._ltf_bars) - 1,
                "of_trigger": result["of_trigger"],
                "side": result["side"],
            })

        if self.position is None:
            self._check_entry(bar)

    def on_price_tick(self, price: float) -> None:
        if self.position is None:
            return
        pos = self.position
        if pos.side == "bullish":
            if price <= pos.stop:
                self._exit(price, hit="stop")
            elif price >= pos.target:
                self._exit(price, hit="target")
        else:
            if price >= pos.stop:
                self._exit(price, hit="stop")
            elif price <= pos.target:
                self._exit(price, hit="target")

    def _check_entry(self, bar: dict) -> None:
        zone = self.zones.zone_at_price(bar["close"])
        if zone is None:
            return

        o = [b["open"] for b in self._ltf_bars]
        h = [b["high"] for b in self._ltf_bars]
        l = [b["low"] for b in self._ltf_bars]
        c = [b["close"] for b in self._ltf_bars]
        last_idx = len(c) - 1
        window_start = max(0, last_idx - CONFLUENCE_WINDOW_BARS)

        cisd = cisd_events(o, h, l, c)
        cisd_in_window = any(e["idx"] >= window_start and e["type"] == zone["type"] for e in cisd)
        if not cisd_in_window:
            return

        matching_trigger = next(
            (
                t for t in reversed(self._recent_ltf_triggers)
                if t["bar_index"] >= window_start and _TRIGGER_TO_ZONE_TYPE[t["side"]] == zone["type"]
            ),
            None,
        )
        if matching_trigger is None:
            return

        entry_price = bar["close"]
        if zone["type"] == "bullish":
            stop = zone["zone_lo"]
            risk = entry_price - stop
        else:
            stop = zone["zone_hi"]
            risk = stop - entry_price
        if risk <= 0:
            return  # 존 경계가 진입가와 같거나 역전된 기형 케이스 — 진입 스킵

        target = self.zones.next_opposing_level(zone["type"], entry_price)
        if target is None:
            return  # 다음 반대편 유동성 레벨이 아직 안 잡힘 — 목표 미확정, 진입 스킵

        self.position = PositionState(
            side=zone["type"], entry_price=entry_price, stop=stop, target=target,
            zone_source=zone["source"], of_trigger=matching_trigger["of_trigger"],
            entered_ts=bar["ts"],
        )
        self.zones.mark_consumed(zone)
        save_position_state(self._state_path, self.position)

    def _exit(self, price: float, hit: str) -> None:
        pos = self.position
        risk = abs(pos.entry_price - pos.stop)
        if pos.side == "bullish":
            result_r = (price - pos.entry_price) / risk
        else:
            result_r = (pos.entry_price - price) / risk
        append_trade_row(
            self._journal_path,
            entered_ts=pos.entered_ts,
            symbol=self.symbol,
            direction="long" if pos.side == "bullish" else "short",
            ict_context=f"CISD+{pos.zone_source}",
            of_trigger=pos.of_trigger,
            level_basis=pos.zone_source,
            entry=pos.entry_price,
            stop=pos.stop,
            target=pos.target,
            risk_r=1.0,
            result_r=round(result_r, 4),
            note=f"auto paper engine, exit={hit}",
        )
        clear_position_state(self._state_path)
        self.position = None
