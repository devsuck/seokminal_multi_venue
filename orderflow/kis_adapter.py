"""KIS(한국투자증권) 해외선물옵션 실시간시세 어댑터 — 체결(HDFFF020/ccnl) + 호가(HDFFF010/asking_price).
CME/SGX 실시간시세는 KIS포털에서 유료시세 신청 필요 (미신청 시 SUBSCRIBE ERROR).

체결 틱에 매수/매도 구분 필드가 없어(국내 H0STCNT0의 side_code와 달리, ccnl의 prev_sign/quotsign/
psttl_sign은 전일대비 등락 표시로 추정되며 체결 공격 방향이 아님 — 공식 문서에 필드 설명 없음),
orderflow/tick_rule.classify()로 직전 호가 스냅샷 대비 분류한다(ib_adapter.py와 동일 방식).

가격 스케일: KIS 공식 예제는 ffcode.mst(해외선물종목마스터) 파일의 sCalcDesz(계산 소수점) 값을
반영해야 정확한 가격이 된다고 명시한다. 이 어댑터는 마스터 파일을 참조하지 않고 수신 필드를 그대로
float() 변환한다 — 실거래소 payload로 스케일 검증 전까지는 가격이 부정확할 수 있음(연구용 미검증 가정,
비용모델의 미검증 IB 수수료율과 동일한 성격).

심볼: tr_key는 KIS 해외선물 종목코드(예: 최근월 NQ 계약 코드)를 그대로 넘겨야 한다. IB 어댑터의
_resolve_contract 같은 최근월물 자동 해석은 없음(ffcode.mst 미보유로 구현 불가)."""
import json
import os
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

import websockets

from backends.kis.ws_auth import get_approval_key
from orderflow.models import OrderBookLevel, OrderBookSnapshot, TradeEvent
from orderflow.tick_rule import classify

KIS_WS_URL = "ws://ops.koreainvestment.com:21000"
TRADE_TR_ID = "HDFFF020"
DEPTH_TR_ID = "HDFFF010"
TRADE_FIELD_COUNT = 25
TRADE_PRICE_IDX = 10  # last_price
TRADE_SIZE_IDX = 11  # last_qntt
DEPTH_FIELD_COUNT = 35
DEPTH_LEVELS = 5
DEPTH_LEVEL_STRIDE = 6  # bid_qntt, bid_num, bid_price, ask_qntt, ask_num, ask_price
DEPTH_LEVEL_BASE = 4  # series_cd, recv_date, recv_time, prev_price 이후 시작


def _subscribe_message(approval_key: str, tr_id: str, tr_key: str) -> dict:
    return {
        "header": {
            "approval_key": approval_key,
            "custtype": "P",
            "tr_type": "1",
            "content-type": "utf-8",
        },
        "body": {"input": {"tr_id": tr_id, "tr_key": tr_key}},
    }


def parse_kis_futures_trade_message(
    raw: str, symbol: str, bid: float, ask: float, now_fn: Callable[[], float] = time.time
) -> TradeEvent | None:
    parts = raw.split("|")
    if len(parts) < 4 or parts[1] != TRADE_TR_ID:
        return None
    fields = parts[3].split("^")
    if len(fields) < TRADE_FIELD_COUNT:
        return None
    try:
        price = float(fields[TRADE_PRICE_IDX])
        size = float(fields[TRADE_SIZE_IDX])
    except (ValueError, IndexError):
        return None
    return TradeEvent(symbol=symbol, ts=now_fn(), price=price, size=size, side=classify(price, bid, ask))


def parse_kis_futures_depth_message(
    raw: str, symbol: str, now_fn: Callable[[], float] = time.time
) -> OrderBookSnapshot | None:
    parts = raw.split("|")
    if len(parts) < 4 or parts[1] != DEPTH_TR_ID:
        return None
    fields = parts[3].split("^")
    if len(fields) < DEPTH_FIELD_COUNT:
        return None
    bids: list[OrderBookLevel] = []
    asks: list[OrderBookLevel] = []
    try:
        for level in range(DEPTH_LEVELS):
            base = DEPTH_LEVEL_BASE + level * DEPTH_LEVEL_STRIDE
            bid_size = float(fields[base])
            bid_price = float(fields[base + 2])
            ask_size = float(fields[base + 3])
            ask_price = float(fields[base + 5])
            if bid_price > 0:
                bids.append(OrderBookLevel(price=bid_price, size=bid_size))
            if ask_price > 0:
                asks.append(OrderBookLevel(price=ask_price, size=ask_size))
    except (ValueError, IndexError):
        return None
    return OrderBookSnapshot(symbol=symbol, ts=now_fn(), bids=bids, asks=asks)


class KISFuturesOrderflowClient:
    def __init__(
        self,
        app_key: str | None = None,
        app_secret: str | None = None,
        approval_key: str | None = None,
        base_url: str = KIS_WS_URL,
        connect_fn: Callable[[str], Any] = websockets.connect,
    ) -> None:
        self._app_key = app_key or os.environ.get("KIS_APP_KEY")
        self._app_secret = app_secret or os.environ.get("KIS_APP_SECRET")
        self._approval_key = approval_key
        self._base_url = base_url
        self._connect_fn = connect_fn

    def _resolve_approval_key(self) -> str:
        if self._approval_key:
            return self._approval_key
        if not self._app_key or not self._app_secret:
            raise ValueError("KIS_APP_KEY/KIS_APP_SECRET not set and no approval_key provided")
        return get_approval_key(self._app_key, self._app_secret)

    async def stream(self, symbol: str) -> AsyncIterator[TradeEvent | OrderBookSnapshot]:
        approval_key = self._resolve_approval_key()
        async with self._connect_fn(self._base_url) as connection:
            await connection.send(json.dumps(_subscribe_message(approval_key, TRADE_TR_ID, symbol)))
            await connection.send(json.dumps(_subscribe_message(approval_key, DEPTH_TR_ID, symbol)))

            best_bid: float | None = None
            best_ask: float | None = None

            async for raw in connection:
                if not raw or raw[0] not in ("0", "1"):
                    await self._handle_control_frame(connection, raw)
                    continue

                parts = raw.split("|")
                if len(parts) < 2:
                    continue
                tr_id = parts[1]

                if tr_id == DEPTH_TR_ID:
                    snapshot = parse_kis_futures_depth_message(raw, symbol)
                    if snapshot is None:
                        continue
                    if snapshot.bids:
                        best_bid = snapshot.bids[0].price
                    if snapshot.asks:
                        best_ask = snapshot.asks[0].price
                    yield snapshot
                elif tr_id == TRADE_TR_ID:
                    if best_bid is None or best_ask is None:
                        continue
                    event = parse_kis_futures_trade_message(raw, symbol, best_bid, best_ask)
                    if event is not None:
                        yield event

    async def _handle_control_frame(self, connection: Any, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except (TypeError, ValueError):
            return
        if not isinstance(msg, dict):
            return
        if msg.get("header", {}).get("tr_id") == "PINGPONG":
            await connection.send(raw)
