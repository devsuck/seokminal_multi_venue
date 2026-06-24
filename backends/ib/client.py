# backends/ib/client.py
from collections.abc import AsyncIterator

from ib_async import IB
from ib_async.contract import Stock
from ib_async.objects import BarData, TickByTickAllLast

TICK_TYPE = "AllLast"
DAILY_BAR_SIZE = "1 day"
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

    async def get_daily_bars(self, symbol: str, end_date: str, duration: str) -> list[BarData]:
        await self._ib.connectAsync(self._host, self._port, self._client_id)
        contract = Stock(symbol, "SMART", "USD")
        await self._ib.qualifyContractsAsync(contract)
        bars = await self._ib.reqHistoricalDataAsync(
            contract,
            endDateTime=end_date,
            durationStr=duration,
            barSizeSetting=DAILY_BAR_SIZE,
            whatToShow=DAILY_WHAT_TO_SHOW,
            useRTH=True,
        )
        if not bars:
            raise ValueError(
                f"no historical daily bars returned for {symbol} "
                f"(end_date={end_date!r}, duration={duration!r}) -- "
                "check IB market data permissions"
            )
        return bars
