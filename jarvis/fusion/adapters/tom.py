"""Turn-of-Month 어댑터 — 계절성 캘린더 규칙을 바스켓 롱 신호로 번역.

전략 규칙: 월 마지막 거래일 진입 → HOLD_DAYS 보유. 이를 as_of 시점의 롱/플랫으로 번역.
캘린더(평일)만 사용 = 미래 가격데이터 미사용(no-lookahead). 정확한 KR 거래소
휴장일 반영은 KRX 데이터 필요 → 블로커로 문서화(현재는 평일 근사).

바스켓 단일 계기(KR_TOM_BASKET). 창 안이면 +1, 아니면 신호 없음.
"""
from __future__ import annotations

import datetime as _dt

from jarvis.fusion.adapters.base import add_business_days, as_date, last_business_day
from jarvis.fusion.types import StrategySignal

STRATEGY_ID = "kr_turn_of_month_v1_PORTFOLIO"
BASKET = "KR_TOM_BASKET"
DEFAULT_HOLD_DAYS = 4


class TurnOfMonthAdapter:
    strategy_id = STRATEGY_ID

    def __init__(self, hold_days: int = DEFAULT_HOLD_DAYS) -> None:
        self.hold_days = hold_days

    def _entry_and_window(self, month_ref: _dt.date) -> tuple[str, str]:
        """(진입일=월말평일, 창종료일=진입+hold 영업일)."""
        entry = last_business_day(month_ref.year, month_ref.month)
        end = add_business_days(entry, self.hold_days)
        return entry, end

    def _in_window(self, d: str) -> dict | None:
        cur = _dt.date.fromisoformat(d)
        # 현재월 + 전월(전월 말 진입 창이 이번달 초로 넘어오는 경우) 둘 다 검사
        prev_month = (cur.replace(day=1) - _dt.timedelta(days=1))
        for ref in (cur, prev_month):
            entry, end = self._entry_and_window(ref)
            if entry <= d <= end:
                return {"entry": entry, "window_end": end}
        return None

    def signals(self, as_of: str = "") -> list[StrategySignal]:
        d = as_date(as_of)
        if d is None:
            return []
        win = self._in_window(d)
        if win is None:
            return []
        return [StrategySignal(
            strategy_id=self.strategy_id, instrument=BASKET, direction=1, strength=1.0,
            as_of=as_of, source="tom_calendar",
            meta={"entry": win["entry"], "window_end": win["window_end"],
                  "hold_days": self.hold_days, "calendar": "business_day_approx"})]
