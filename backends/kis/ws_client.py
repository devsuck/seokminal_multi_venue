# backends/kis/ws_client.py
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import websockets

TRADE_TR_ID = "H0STCNT0"


class KISWebSocketClient:
    def __init__(
        self,
        approval_key: str,
        base_url: str = "ws://ops.koreainvestment.com:21000",
        connect_fn: Callable[[str], Any] = websockets.connect,
    ) -> None:
        self._approval_key = approval_key
        self._base_url = base_url
        self._connect_fn = connect_fn

    async def stream_trades(self, code: str) -> AsyncIterator[str]:
        async with self._connect_fn(self._base_url) as connection:
            await connection.send(json.dumps(self._subscribe_message(code)))
            async for message in connection:
                yield message

    def _subscribe_message(self, code: str) -> dict:
        return {
            "header": {
                "approval_key": self._approval_key,
                "custtype": "P",
                "tr_type": "1",
                "content-type": "utf-8",
            },
            "body": {
                "input": {
                    "tr_id": TRADE_TR_ID,
                    "tr_key": code,
                }
            },
        }
