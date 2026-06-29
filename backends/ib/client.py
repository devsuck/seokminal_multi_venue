# backends/ib/client.py
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
        host: str = "127.0.0.1",
        port: int = 7497,
        client_id: int = 1,
        ib: IB | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._client_id = client_id
        self._ib = ib if ib is not None else IB()

    async def stream_trades(self, symbol: str) -> AsyncIterator[TickByTickAllLast]:
        await self._ib.connectAsync(self._host, self._port, self._client_id)
        contract = Stock(symbol, "SMART", "USD")
        await self._ib.qualifyContractsAsync(contract)
        ticker = self._ib.reqTickByTickData(contract, TICK_TYPE)
        async for _ in ticker.updateEvent:
            for tick in ticker.tickByTicks:
                yield tick
            ticker.tickByTicks.clear()

    async def get_daily_bars(
        self, symbol: str, end_date: str, duration: str, bar_size: str = DEFAULT_BAR_SIZE
    ) -> list[BarData]:
        await self._ib.connectAsync(self._host, self._port, self._client_id)
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
        await self._ib.connectAsync(self._host, self._port, self._client_id)
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
        await self._ib.connectAsync(self._host, self._port, self._client_id)
        contract = Future(symbol, expiry, exchange)
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
        await self._ib.connectAsync(self._host, self._port, self._client_id)
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

    async def get_daily_bars_crypto(
        self, symbol: str, end_date: str, duration: str, bar_size: str = DEFAULT_BAR_SIZE
    ) -> list[BarData]:
        await self._ib.connectAsync(self._host, self._port, self._client_id)
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
