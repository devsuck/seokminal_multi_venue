# research/polymarket_tick/ws_collector.py
"""CLOB WSS market 채널 구독 + 틱 파싱 (I/O)."""
from __future__ import annotations

import datetime as dt
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import websockets

MARKET_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"


class PolymarketTickWSClient:
    def __init__(
        self,
        base_url: str = MARKET_WS_URL,
        connect_fn: Callable[[str], Any] = websockets.connect,
    ) -> None:
        self._base_url = base_url
        self._connect_fn = connect_fn

    async def stream_ticks(self, asset_ids: list[str]) -> AsyncIterator[str]:
        async with self._connect_fn(self._base_url) as connection:
            await connection.send(json.dumps(self._subscribe_message(asset_ids)))
            async for message in connection:
                yield message

    def _subscribe_message(self, asset_ids: list[str]) -> dict:
        return {"assets_ids": asset_ids, "type": "market"}


def _to_float(v) -> float | None:
    return float(v) if v is not None else None


def _base_row(meta: dict, token_id: str, event_type: str) -> dict:
    return {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        "condition_id": meta["condition_id"],
        "question": meta["question"],
        "family": meta["family"],
        "token_id": token_id,
        "outcome": meta["outcome"],
        "event_type": event_type,
        "price": None,
        "size": None,
        "side": None,
        "best_bid": None,
        "best_ask": None,
    }


def parse_tick_message(raw: str, meta_by_token: dict[str, dict]) -> list[dict]:
    """CLOB WSS raw 메시지(JSON 문자열) 1건을 저장용 틱 dict 리스트로 변환.
    book/price_change 외 event_type, 대상 목록에 없는 token_id는 버린다."""
    try:
        msg = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(msg, dict):
        return []

    event_type = msg.get("event_type")
    if event_type == "book":
        token_id = msg.get("asset_id")
        meta = meta_by_token.get(token_id)
        if meta is None:
            return []
        bids = msg.get("bids") or []
        asks = msg.get("asks") or []
        best_bid = max((float(b["price"]) for b in bids), default=None)
        best_ask = min((float(a["price"]) for a in asks), default=None)
        row = _base_row(meta, token_id, "book")
        row["best_bid"] = best_bid
        row["best_ask"] = best_ask
        return [row]

    if event_type == "price_change":
        rows = []
        for change in msg.get("price_changes") or []:
            token_id = change.get("asset_id")
            meta = meta_by_token.get(token_id)
            if meta is None:
                continue
            row = _base_row(meta, token_id, "price_change")
            row["price"] = _to_float(change.get("price"))
            row["size"] = _to_float(change.get("size"))
            row["side"] = change.get("side")
            row["best_bid"] = _to_float(change.get("best_bid"))
            row["best_ask"] = _to_float(change.get("best_ask"))
            rows.append(row)
        return rows

    return []
