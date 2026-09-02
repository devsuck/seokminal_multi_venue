"""HL+KIS(live/paper) 계좌 병렬 집계 (P8)."""
from __future__ import annotations

import asyncio
import time as _time

from jarvis.broker_readonly.live_providers import HLReadOnlyProvider, KISReadOnlyProvider

_FX_CACHE: dict = {}
_FX_TTL = 60.0
_FX_FALLBACK = 1350.0  # ponytail: yfinance 실패+캐시 없음 시 대략치. 화면은 뜨게.


def _usdkrw_rate() -> float:
    now = _time.time()
    cached = _FX_CACHE.get("rate")
    if cached and now - cached[0] < _FX_TTL:
        return cached[1]
    try:
        import yfinance as yf
        hist = yf.Ticker("USDKRW=X").history(period="1d", interval="1d")
        rate = float(hist["Close"].dropna().iloc[-1])
    except Exception:
        rate = cached[1] if cached else _FX_FALLBACK
    _FX_CACHE["rate"] = (now, rate)
    return rate


def _empty_account(name: str, error: str) -> dict:
    return {"account": name, "connected": False, "error": error,
            "cash": 0.0, "equity": 0.0, "equity_usd": 0.0, "positions": []}


class PortfolioAggregator:
    def __init__(self, mode: str) -> None:
        self._mode = mode
        paper = mode == "paper"
        self._providers = {
            "hl": HLReadOnlyProvider(paper=paper),
            "kis": KISReadOnlyProvider(paper=paper),
        }

    async def summary(self) -> dict:
        fx = await asyncio.to_thread(_usdkrw_rate)
        results = await asyncio.gather(
            *[asyncio.to_thread(self._one, name, p, fx) for name, p in self._providers.items()]
        )
        accounts = []
        total_usd = 0.0
        holdings: list[dict] = []
        for name, account in results:
            accounts.append(account)
            total_usd += account["equity_usd"]
            for pos in account["positions"]:
                if pos["market_value"] == 0:
                    continue
                value_usd = pos["market_value"] / fx if name == "kis" else pos["market_value"]
                holdings.append({"account": name, "symbol": pos["symbol"],
                                  "value_usd": round(value_usd, 2)})
        return {"mode": self._mode, "total_equity_usd": round(total_usd, 2), "fx_usdkrw": fx,
                "accounts": accounts, "holdings": holdings}

    def _one(self, name: str, provider, fx: float) -> tuple[str, dict]:
        try:
            snap = provider.account_snapshot()
            positions = provider.positions()
            health = provider.health_check()
        except Exception as exc:
            return name, _empty_account(name, str(exc))
        if snap is None:
            return name, _empty_account(name, health.error or "계좌 정보 없음")
        equity_usd = snap.equity / fx if name == "kis" else snap.equity
        return name, {
            "account": name, "connected": health.connected, "error": health.error,
            "cash": snap.cash, "equity": snap.equity, "equity_usd": round(equity_usd, 2),
            "positions": [p.to_dict() for p in positions],
        }

    def trades(self, account: str | None = None) -> list[dict]:
        providers = self._providers if account is None else {account: self._providers[account]}
        out: list[dict] = []
        for p in providers.values():
            out.extend(p.orders_history())
        out.sort(key=lambda t: t.get("ts") or "", reverse=True)
        return out
