# backends/ib/client.py
import asyncio
import datetime as dt
import os
from collections.abc import AsyncIterator

from ib_async import IB
from ib_async.contract import Crypto, Forex, Future, Option, Stock
from ib_async.objects import BarData, TickByTickAllLast

TICK_TYPE = "AllLast"
DEFAULT_BAR_SIZE = "1 day"
DAILY_WHAT_TO_SHOW = "TRADES"


class IBClient:
    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        client_id: int = 1,
        ib: IB | None = None,
    ) -> None:
        # WSL 등에서 TWS가 다른 호스트에 있을 때 IB_HOST로 지정 (기본 로컬)
        self._host = host or os.environ.get("IB_HOST", "127.0.0.1")
        self._port = port if port is not None else int(os.environ.get("IB_PORT", "7497"))
        self._client_id = client_id
        self._ib = ib if ib is not None else IB()

    async def stream_trades(
        self, symbol: str, connect_timeout: float = 15.0
    ) -> AsyncIterator[TickByTickAllLast]:
        # connect_timeout caps the wait so a missing/closed TWS gateway raises
        # promptly instead of leaving the caller (e.g. a WebSocket handler)
        # hanging — the endpoint relays the error and the widget shows offline.
        await self._ib.connectAsync(
            self._host, self._port, self._client_id, timeout=connect_timeout
        )
        contract = Stock(symbol, "SMART", "USD")
        await self._ib.qualifyContractsAsync(contract)
        ticker = self._ib.reqTickByTickData(contract, TICK_TYPE)
        async for _ in ticker.updateEvent:
            for tick in ticker.tickByTicks:
                yield tick
            ticker.tickByTicks.clear()

    async def get_account_summary(self, connect_timeout: float = 15.0) -> dict:
        """Net liquidation / cash / buying power from IB. Requires a running
        TWS/Gateway; raises promptly (connect_timeout) if unreachable."""
        await self._ib.connectAsync(
            self._host, self._port, self._client_id, timeout=connect_timeout
        )
        try:
            # ib_async auto-subscribes account updates on connect and fills
            # accountValues(). reqAccountSummaryAsync returns 0 rows and an
            # explicit reqAccountUpdatesAsync hangs for some accounts, so just
            # wait briefly and read the auto-populated values.
            for _ in range(12):  # up to ~3s for the initial account push
                if self._ib.accountValues():
                    break
                await asyncio.sleep(0.25)
            vals = self._ib.accountValues()
            # Base-currency rows only (skip per-currency BASE duplicates).
            d = {}
            ccy = "USD"
            for v in vals:
                if v.tag in ("NetLiquidation", "TotalCashValue", "BuyingPower") and v.currency and v.currency != "BASE":
                    d[v.tag] = v.value
                    if v.tag == "NetLiquidation":
                        ccy = v.currency
            return {
                "net_liquidation": float(d.get("NetLiquidation", 0) or 0),
                "total_cash": float(d.get("TotalCashValue", 0) or 0),
                "buying_power": float(d.get("BuyingPower", 0) or 0),
                "currency": ccy,
            }
        finally:
            if self._ib.isConnected():
                self._ib.disconnect()

    async def get_daily_bars(
        self, symbol: str, end_date: str, duration: str, bar_size: str = DEFAULT_BAR_SIZE
    ) -> list[BarData]:
        await self._ib.connectAsync(self._host, self._port, self._client_id, timeout=15)
        contract = Stock(symbol, "SMART", "USD")
        await self._ib.qualifyContractsAsync(contract)
        bars = await self._ib.reqHistoricalDataAsync(
            contract,
            endDateTime=end_date,
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow=DAILY_WHAT_TO_SHOW,
            useRTH=True,
        )
        if not bars:
            raise ValueError(
                f"no historical bars returned for {symbol} "
                f"(end_date={end_date!r}, duration={duration!r}, bar_size={bar_size!r}) -- "
                "check IB market data permissions"
            )
        return bars

    async def get_daily_bars_forex(
        self, pair: str, end_date: str, duration: str, bar_size: str = DEFAULT_BAR_SIZE
    ) -> list[BarData]:
        await self._ib.connectAsync(self._host, self._port, self._client_id, timeout=15)
        contract = Forex(pair)
        await self._ib.qualifyContractsAsync(contract)
        bars = await self._ib.reqHistoricalDataAsync(
            contract,
            endDateTime=end_date,
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow="MIDPOINT",
            useRTH=False,
        )
        if not bars:
            raise ValueError(
                f"no historical bars returned for {pair!r} forex pair -- "
                "check IB market data permissions"
            )
        return bars

    async def get_daily_bars_future(
        self, symbol: str, exchange: str, expiry: str, end_date: str, duration: str,
        bar_size: str = DEFAULT_BAR_SIZE,
    ) -> list[BarData]:
        await self._ib.connectAsync(self._host, self._port, self._client_id, timeout=15)
        contract = Future(symbol, expiry, exchange)
        await self._ib.qualifyContractsAsync(contract)
        if not contract.conId:
            # 만기월 미지정 시 qualify가 ambiguous로 실패(conId=0) — 최근월물을 직접 골라온다.
            details = await self._ib.reqContractDetailsAsync(contract)
            if not details:
                raise ValueError(f"IB: no contract details resolved for {symbol!r} future ({exchange!r})")
            today = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
            candidates = sorted(details, key=lambda d: d.contract.lastTradeDateOrContractMonth)
            contract = next(
                (d.contract for d in candidates if d.contract.lastTradeDateOrContractMonth >= today),
                candidates[-1].contract,
            )
        bars = await self._ib.reqHistoricalDataAsync(
            contract,
            endDateTime=end_date,
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow=DAILY_WHAT_TO_SHOW,
            useRTH=True,
        )
        if not bars:
            raise ValueError(
                f"no historical bars returned for {symbol!r} future "
                f"(exchange={exchange!r}, expiry={expiry!r}) -- "
                "check IB market data permissions"
            )
        return bars

    async def get_daily_bars_option(
        self,
        symbol: str,
        expiry: str,
        strike: float,
        right: str,
        end_date: str,
        duration: str,
        bar_size: str = DEFAULT_BAR_SIZE,
    ) -> list[BarData]:
        await self._ib.connectAsync(self._host, self._port, self._client_id, timeout=15)
        contract = Option(
            symbol=symbol,
            lastTradeDateOrContractMonth=expiry,
            strike=strike,
            right=right,
            exchange="SMART",
            currency="USD",
        )
        await self._ib.qualifyContractsAsync(contract)
        bars = await self._ib.reqHistoricalDataAsync(
            contract,
            endDateTime=end_date,
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow=DAILY_WHAT_TO_SHOW,
            useRTH=True,
        )
        if not bars:
            raise ValueError(
                f"no historical bars returned for {symbol!r} {right} option "
                f"(expiry={expiry!r}, strike={strike}) -- "
                "check IB market data permissions"
            )
        return bars

    async def get_option_chain(
        self,
        symbol: str,
        max_expiries: int = 4,
        connect_timeout: float = 15.0,
    ) -> dict:
        """주식의 옵션 체인 조회 (지연 데이터, OPRA 구독 불필요).

        Returns:
            {expiry: [{strike, right, bid, ask, last, volume, open_interest, iv, delta}]}
        """
        await self._ib.connectAsync(self._host, self._port, self._client_id, timeout=connect_timeout)
        try:
            stock = Stock(symbol, "SMART", "USD")
            await self._ib.qualifyContractsAsync(stock)

            # 사용 가능한 만기·행사가 조회
            chains = await self._ib.reqSecDefOptParamsAsync(
                underlyingSymbol=symbol,
                futFopExchange="",
                underlyingSecType="STK",
                underlyingConId=stock.conId,
            )
            if not chains:
                return {}

            chain = chains[0]
            expirations = sorted(chain.expirations)[:max_expiries]
            strikes = sorted(chain.strikes)

            # 현재 주가 근처 ±20% 행사가만 (체인 축소)
            try:
                tickers = await asyncio.wait_for(self._ib.reqTickersAsync(stock), timeout=10.0)
            except asyncio.TimeoutError:
                tickers = []
            await asyncio.sleep(0.5)
            mid = None
            if tickers and tickers[0].marketPrice() > 0:
                mid = tickers[0].marketPrice()
            if mid:
                lo, hi = mid * 0.80, mid * 1.20
                strikes = [s for s in strikes if lo <= s <= hi]
            strikes = strikes[:30]  # 최대 30개 행사가

            result: dict[str, list] = {}
            for expiry in expirations:
                contracts = [
                    Option(symbol, expiry, s, r, "SMART", currency="USD")
                    for s in strikes for r in ("C", "P")
                ]
                # 지연 스냅샷 요청 (15분 지연, OPRA 불필요)
                self._ib.reqMarketDataType(3)  # 3 = delayed
                try:
                    contracts = await asyncio.wait_for(
                        self._ib.qualifyContractsAsync(*contracts), timeout=10.0
                    )
                    contracts = [c for c in contracts if c is not None and c.conId]
                except asyncio.TimeoutError:
                    contracts = []
                try:
                    tks = await asyncio.wait_for(self._ib.reqTickersAsync(*contracts), timeout=15.0) if contracts else []
                except asyncio.TimeoutError:
                    tks = []
                await asyncio.sleep(2.0)  # 데이터 수신 대기

                rows = []
                for tk in tks:
                    c = tk.contract
                    rows.append({
                        "strike": c.strike,
                        "right": c.right,
                        "bid": tk.bid if tk.bid and tk.bid > 0 else None,
                        "ask": tk.ask if tk.ask and tk.ask > 0 else None,
                        "last": tk.last if tk.last and tk.last > 0 else None,
                        "volume": int(tk.volume) if tk.volume and tk.volume > 0 else 0,
                        "open_interest": int(oi) if hasattr(tk, "callOpenInterest") and (oi := (tk.callOpenInterest if c.right == "C" else tk.putOpenInterest)) and oi == oi else 0,
                        "iv": round(tk.modelGreeks.impliedVol, 4) if tk.modelGreeks and tk.modelGreeks.impliedVol else None,
                        "delta": round(tk.modelGreeks.delta, 4) if tk.modelGreeks and tk.modelGreeks.delta else None,
                    })
                result[expiry] = sorted(rows, key=lambda x: (x["strike"], x["right"]))

            return result
        finally:
            if self._ib.isConnected():
                self._ib.disconnect()

    async def get_daily_bars_crypto(
        self, symbol: str, end_date: str, duration: str, bar_size: str = DEFAULT_BAR_SIZE
    ) -> list[BarData]:
        await self._ib.connectAsync(self._host, self._port, self._client_id, timeout=15)
        contract = Crypto(symbol=symbol, exchange="PAXOS", currency="USD")
        await self._ib.qualifyContractsAsync(contract)
        bars = await self._ib.reqHistoricalDataAsync(
            contract,
            endDateTime=end_date,
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow=DAILY_WHAT_TO_SHOW,
            useRTH=False,
        )
        if not bars:
            raise ValueError(
                f"no historical bars returned for {symbol!r} crypto -- "
                "check IB market data permissions (BTC/ETH/LTC/BCH/XRP/SOL supported via PAXOS)"
            )
        return bars
