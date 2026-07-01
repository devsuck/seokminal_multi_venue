from ib_async.order import UNSET_DOUBLE

from backends.ib.order_client import IBOrderClient


class FakeOrder:
    def __init__(self, action, totalQuantity, lmtPrice=None):
        self.action = action
        self.totalQuantity = totalQuantity
        self.lmtPrice = lmtPrice
        self.orderId = 0
        self.clientId = 0
        self.permId = 0


class FakeOrderStatus:
    def __init__(self, status="PendingSubmit", filled=0.0, remaining=0.0, avgFillPrice=UNSET_DOUBLE):
        self.status = status
        self.filled = filled
        self.remaining = remaining
        self.avgFillPrice = avgFillPrice


class FakeTrade:
    def __init__(self, order, status="PendingSubmit", filled=0.0, remaining=0.0, avgFillPrice=UNSET_DOUBLE):
        self.order = order
        self.orderStatus = FakeOrderStatus(status, filled, remaining, avgFillPrice)


class FakeIB:
    def __init__(self):
        self.connect_calls: list[tuple] = []
        self.qualify_calls: list[tuple] = []
        self.placed_orders: list = []
        self.cancelled_orders: list = []
        self._connected = False
        self._next_order_id = 100
        self._trades: list[FakeTrade] = []

    def isConnected(self) -> bool:
        return self._connected

    async def connectAsync(self, host, port, client_id, timeout=4):
        self.connect_calls.append((host, port, client_id))
        self._connected = True

    async def qualifyContractsAsync(self, contract):
        self.qualify_calls.append((contract.symbol, contract.exchange, contract.currency))

    def placeOrder(self, contract, order):
        order.orderId = self._next_order_id
        self._next_order_id += 1
        self.placed_orders.append((contract.symbol, order.action, order.totalQuantity, order.lmtPrice))
        trade = FakeTrade(order, status="PendingSubmit", filled=0.0, remaining=order.totalQuantity)
        self._trades.append(trade)
        return trade

    def cancelOrder(self, order):
        self.cancelled_orders.append(order.orderId)
        for trade in self._trades:
            if trade.order.orderId == order.orderId:
                trade.orderStatus.status = "Cancelled"
                return trade
        return None

    def trades(self):
        return list(self._trades)

    async def reqHistoricalDataAsync(self, contract, endDateTime, durationStr,
                                     barSizeSetting, whatToShow, useRTH):
        self.hist_calls = getattr(self, "hist_calls", [])
        self.hist_calls.append((contract.symbol, durationStr, barSizeSetting, whatToShow, useRTH))
        return getattr(self, "_bars", [])


class FakeBar:
    def __init__(self, date, o, h, l, c, v):
        self.date = date; self.open = o; self.high = h; self.low = l; self.close = c; self.volume = v


class FillingIB(FakeIB):
    """placeOrder immediately reports a fill so wait_fill can capture avg price."""
    def __init__(self, fill_price=101.5):
        super().__init__()
        self._fill_price = fill_price

    def placeOrder(self, contract, order):
        order.orderId = self._next_order_id
        self._next_order_id += 1
        self.placed_orders.append((contract.symbol, order.action, order.totalQuantity, order.lmtPrice))
        trade = FakeTrade(order, status="Filled", filled=order.totalQuantity,
                          remaining=0.0, avgFillPrice=self._fill_price)
        self._trades.append(trade)
        return trade


def _client(ib):
    return IBOrderClient(host="127.0.0.1", port=7497, client_id=2, ib=ib)


async def test_place_order_market_buy_connects_qualifies_and_returns_status_dict():
    fake_ib = FakeIB()
    client = _client(fake_ib)

    result = await client.place_order(symbol="AAPL", side="BUY", quantity=1, order_type="MARKET")

    assert fake_ib.connect_calls == [("127.0.0.1", 7497, 2)]
    assert fake_ib.qualify_calls == [("AAPL", "SMART", "USD")]
    assert fake_ib.placed_orders == [("AAPL", "BUY", 1, UNSET_DOUBLE)]
    assert result["order_id"] == 100
    assert result["status"] == "PendingSubmit"
    assert result["filled"] == 0.0
    assert result["remaining"] == 1
    assert result["avg_fill_price"] is None


async def test_place_order_limit_sell_passes_limit_price():
    fake_ib = FakeIB()
    client = _client(fake_ib)

    await client.place_order(symbol="AAPL", side="SELL", quantity=1, order_type="LIMIT", limit_price=50.0)

    assert fake_ib.placed_orders == [("AAPL", "SELL", 1, 50.0)]


async def test_place_order_does_not_reconnect_if_already_connected():
    fake_ib = FakeIB()
    fake_ib._connected = True
    client = _client(fake_ib)

    await client.place_order(symbol="AAPL", side="BUY", quantity=1, order_type="MARKET")

    assert fake_ib.connect_calls == []


async def test_get_order_status_returns_matching_trade_as_dict():
    fake_ib = FakeIB()
    client = _client(fake_ib)
    await client.place_order(symbol="AAPL", side="BUY", quantity=1, order_type="MARKET")

    result = await client.get_order_status(order_id=100)

    assert result == {"order_id": 100, "status": "PendingSubmit", "filled": 0.0,
                      "remaining": 1, "avg_fill_price": None}


async def test_get_order_status_returns_none_when_not_found():
    fake_ib = FakeIB()
    client = _client(fake_ib)

    result = await client.get_order_status(order_id=999)

    assert result is None


async def test_cancel_order_cancels_matching_trade_and_returns_updated_status():
    fake_ib = FakeIB()
    client = _client(fake_ib)
    await client.place_order(symbol="AAPL", side="BUY", quantity=1, order_type="MARKET")

    result = await client.cancel_order(order_id=100)

    assert fake_ib.cancelled_orders == [100]
    assert result["status"] == "Cancelled"


async def test_cancel_order_raises_value_error_when_not_found():
    fake_ib = FakeIB()
    client = _client(fake_ib)

    try:
        await client.cancel_order(order_id=999)
        assert False, "expected ValueError"
    except ValueError:
        pass


async def test_place_order_wait_fill_captures_avg_fill_price():
    fake_ib = FillingIB(fill_price=101.5)
    client = _client(fake_ib)

    result = await client.place_order(symbol="AAPL", side="BUY", quantity=2,
                                      order_type="MARKET", wait_fill=True)

    assert result["status"] == "Filled"
    assert result["avg_fill_price"] == 101.5


async def test_get_intraday_bars_returns_score_shaped_dicts():
    fake_ib = FakeIB()
    fake_ib._bars = [
        FakeBar("2026-07-01 09:30", 100.0, 101.0, 99.5, 100.5, 1000),
        FakeBar("2026-07-01 09:35", 100.5, 102.0, 100.0, 101.5, 1200),
    ]
    client = _client(fake_ib)

    bars = await client.get_intraday_bars("AAPL")

    assert fake_ib.hist_calls == [("AAPL", "2 D", "5 mins", "TRADES", True)]
    assert bars[0] == {"t": "2026-07-01 09:30", "o": 100.0, "h": 101.0,
                       "l": 99.5, "c": 100.5, "v": 1000.0}
    assert len(bars) == 2
