"""KIS broker adapter. Routes XKRX instruments to KIS REST + WebSocket."""
import time
from collections.abc import AsyncIterator

from backends.kis.auth import KISAuth
from backends.kis.order_client import KISOrderClient
from backends.kis.ws_auth import get_approval_key
from backends.kis.ws_client import KISWebSocketClient
from live_engine.broker_interface import BrokerInterface, OrderResult, PriceTick

_TRADE_FIELD_MAP = {
    "stck_prpr": "price",   # 주식현재가
    "stck_cntg_hour": "time",
}


def _instrument_to_code(instrument_id: str) -> str:
    """'005930.XKRX' → '005930'"""
    return instrument_id.split(".")[0]


def _parse_tick(raw_message: str, instrument_id: str) -> PriceTick | None:
    """Parse KIS real-time trade tick message → PriceTick."""
    try:
        parts = raw_message.split("|")
        if len(parts) < 4:
            return None
        tr_id = parts[1]
        if tr_id != "H0STCNT0":
            return None
        data = parts[3].split("^")
        price = float(data[2])  # field index 2 = stck_prpr
        return PriceTick(
            instrument_id=instrument_id,
            price=price,
            ts_ns=int(time.time_ns()),
        )
    except (IndexError, ValueError):
        return None


class KISBroker(BrokerInterface):
    def __init__(
        self,
        app_key: str,
        app_secret: str,
        cano: str,
        acnt_prdt_cd: str,
        mock: bool = True,
    ) -> None:
        self._app_key = app_key
        self._app_secret = app_secret
        base_url = (
            "https://openapivts.koreainvestment.com:29443"
            if mock
            else "https://openapi.koreainvestment.com:9443"
        )
        auth = KISAuth(app_key, app_secret, base_url)
        self._order_client = KISOrderClient(
            app_key=app_key,
            app_secret=app_secret,
            cano=cano,
            acnt_prdt_cd=acnt_prdt_cd,
            auth=auth,
            base_url=base_url,
        )
        self._ws_approval_key: str | None = None
        self._app_key = app_key
        self._app_secret = app_secret

    async def place_order(
        self,
        instrument_id: str,
        side: str,
        quantity: int,
        order_type: str = "MARKET",
        limit_price: float | None = None,
    ) -> OrderResult:
        code = _instrument_to_code(instrument_id)
        result = self._order_client.place_order(
            code=code,
            side=side,
            quantity=quantity,
            order_division=order_type,
            price=int(limit_price) if limit_price else None,
        )
        return OrderResult(**result)

    async def cancel_order(self, order_id: str) -> OrderResult:
        result = self._order_client.cancel_order(order_no=order_id, code="", quantity=0)
        return OrderResult(**result)

    async def stream_prices(self, instrument_id: str) -> AsyncIterator[PriceTick]:
        code = _instrument_to_code(instrument_id)
        if self._ws_approval_key is None:
            self._ws_approval_key = get_approval_key(self._app_key, self._app_secret)
        ws = KISWebSocketClient(approval_key=self._ws_approval_key)
        async for raw in ws.stream_trades(code):
            tick = _parse_tick(raw, instrument_id)
            if tick is not None:
                yield tick

    async def close(self) -> None:
        pass
