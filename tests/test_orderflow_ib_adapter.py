import datetime as dt

from ib_async.contract import Future

from orderflow.ib_adapter import IBOrderflowClient
from orderflow.models import OrderBookSnapshot, TradeEvent


class FakeTickByTickLast:
    def __init__(self, time, price, size):
        self.time = time
        self.price = price
        self.size = size


class FakeTickByTickBidAsk:
    def __init__(self, time, bidPrice, askPrice):
        self.time = time
        self.bidPrice = bidPrice
        self.askPrice = askPrice


class FakeUpdateEvent:
    def __init__(self, ticker, batches):
        self._ticker = ticker
        self._batches = batches

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for batch in self._batches:
            self._ticker.tickByTicks = list(batch)
            yield self._ticker


class FakeTicker:
    def __init__(self, batches):
        self.tickByTicks: list = []
        self.updateEvent = FakeUpdateEvent(self, batches)


class FakeDomLevel:
    def __init__(self, price, size):
        self.price = price
        self.size = size


class FakeDepthUpdateEvent:
    def __init__(self, ticker, batches):
        self._ticker = ticker
        self._batches = batches

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for bids, asks in self._batches:
            self._ticker.domBids = bids
            self._ticker.domAsks = asks
            yield self._ticker


class FakeDepthTicker:
    def __init__(self, batches):
        self.domBids: list = []
        self.domAsks: list = []
        self.updateEvent = FakeDepthUpdateEvent(self, batches)


class FakeMultiIB:
    def __init__(self, last_batches, bidask_batches, depth_batches, contract_details=None):
        self.connect_calls: list[tuple] = []
        self.qualify_calls: list[str] = []
        self.contract_details_calls: list[str] = []
        self.tick_calls: list[str] = []
        self.depth_calls = 0
        self._last_ticker = FakeTicker(last_batches)
        self._bidask_ticker = FakeTicker(bidask_batches)
        self._depth_ticker = FakeDepthTicker(depth_batches)
        self._contract_details = contract_details or {}

    async def connectAsync(self, host, port, client_id, timeout=15):
        self.connect_calls.append((host, port, client_id))

    async def qualifyContractsAsync(self, contract):
        self.qualify_calls.append(contract.symbol)
        if contract.symbol not in self._contract_details:
            contract.conId = 1  # 정상 qualify 시뮬레이션(단일 매치)

    async def reqContractDetailsAsync(self, contract):
        self.contract_details_calls.append(contract.symbol)
        return self._contract_details.get(contract.symbol, [])

    def reqTickByTickData(self, contract, tickType):
        self.tick_calls.append(tickType)
        return self._bidask_ticker if tickType == "BidAsk" else self._last_ticker

    def reqMktDepth(self, contract, numRows=10):
        self.depth_calls += 1
        return self._depth_ticker


class FakeContractDetails:
    def __init__(self, contract):
        self.contract = contract


def test_contract_resolves_mnq_as_future_not_stock():
    """MNQ가 _FUTURES_SYMBOLS에 없으면 Stock으로 fallback해 라이브 IB Gateway에서
    깨진다(2026-07 발견) — Future(exchange=CME)로 resolve되는지 고정."""
    client = IBOrderflowClient(ib=object(), client_id=1)
    contract = client._contract("MNQ")
    assert isinstance(contract, Future)
    assert contract.exchange == "CME"


async def test_stream_yields_trade_classified_by_bidask_then_book_snapshot(monkeypatch):
    # .env의 실제 IB_PORT(7498)가 다른 모듈 임포트 체인의 load_dotenv()로 새어들어와
    # 기본값(7497) assertion과 충돌하는 걸 방지 — 이 테스트는 기본값 자체를 검증한다.
    monkeypatch.delenv("IB_PORT", raising=False)
    t = dt.datetime(2026, 7, 9, 12, 0, 0, tzinfo=dt.timezone.utc)
    ib = FakeMultiIB(
        last_batches=[[FakeTickByTickLast(time=t, price=101.0, size=2.0)]],
        bidask_batches=[[FakeTickByTickBidAsk(time=t, bidPrice=100.0, askPrice=101.0)]],
        depth_batches=[([FakeDomLevel(99.0, 5.0)], [FakeDomLevel(102.0, 3.0)])],
    )
    client = IBOrderflowClient(ib=ib, client_id=1)
    agen = client.stream("NQ")
    try:
        trade = await agen.__anext__()
        book = await agen.__anext__()
    finally:
        await agen.aclose()

    assert isinstance(trade, TradeEvent)
    assert trade.symbol == "NQ"
    assert trade.price == 101.0
    assert trade.side == "buy"  # price == ask -> buy (tick_rule.classify)

    assert isinstance(book, OrderBookSnapshot)
    assert book.symbol == "NQ"
    assert book.bids[0].price == 99.0
    assert book.asks[0].price == 102.0

    assert set(ib.tick_calls) == {"Last", "BidAsk"}
    assert ib.depth_calls == 1
    assert ib.connect_calls == [("127.0.0.1", 7497, 1)]


async def test_stream_skips_trade_before_any_bidask_seen():
    t = dt.datetime(2026, 7, 9, 12, 0, 0, tzinfo=dt.timezone.utc)
    ib = FakeMultiIB(
        last_batches=[[FakeTickByTickLast(time=t, price=101.0, size=2.0)]],
        bidask_batches=[[]],  # 빈 배치 — best_bid/ask 갱신 없음
        depth_batches=[([], [])],
    )
    client = IBOrderflowClient(ib=ib, client_id=2)
    agen = client.stream("NQ")
    try:
        first = await agen.__anext__()  # bidask 배치가 비어 트레이드 스킵 -> 다음은 depth 스냅샷
    finally:
        await agen.aclose()
    assert isinstance(first, OrderBookSnapshot)


async def test_stream_resolves_front_month_when_future_is_ambiguous():
    """만기월 미지정 Future는 qualify가 ambiguous로 실패(conId=0) —
    reqContractDetailsAsync로 받은 후보 중 만기 지나지 않은 최근월물을 골라야 한다."""
    t = dt.datetime(2026, 7, 9, 12, 0, 0, tzinfo=dt.timezone.utc)
    far_expiry = Future(symbol="ES", exchange="CME", currency="USD")
    far_expiry.conId = 999
    far_expiry.lastTradeDateOrContractMonth = "20271217"

    near_expiry = Future(symbol="ES", exchange="CME", currency="USD")
    near_expiry.conId = 111
    near_expiry.lastTradeDateOrContractMonth = "20260918"

    expired = Future(symbol="ES", exchange="CME", currency="USD")
    expired.conId = 222
    expired.lastTradeDateOrContractMonth = "20260315"  # 이미 만기 지남 -> 제외돼야 함

    ib = FakeMultiIB(
        last_batches=[[FakeTickByTickLast(time=t, price=101.0, size=2.0)]],
        bidask_batches=[[FakeTickByTickBidAsk(time=t, bidPrice=100.0, askPrice=101.0)]],
        depth_batches=[([FakeDomLevel(99.0, 5.0)], [FakeDomLevel(102.0, 3.0)])],
        contract_details={
            "ES": [
                FakeContractDetails(far_expiry),
                FakeContractDetails(near_expiry),
                FakeContractDetails(expired),
            ]
        },
    )
    client = IBOrderflowClient(ib=ib, client_id=3)
    agen = client.stream("ES")
    try:
        trade = await agen.__anext__()
    finally:
        await agen.aclose()

    assert isinstance(trade, TradeEvent)
    assert ib.contract_details_calls == ["ES"]
