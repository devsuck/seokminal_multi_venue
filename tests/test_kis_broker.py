from live_engine.kis_broker import KISBroker


def _broker() -> KISBroker:
    return KISBroker(app_key="key", app_secret="secret", cano="12345678", acnt_prdt_cd="01")


async def test_get_position_returns_long_when_holding_matches(monkeypatch):
    broker = _broker()
    monkeypatch.setattr(
        broker._order_client,
        "get_holdings",
        lambda: [{"code": "005930", "qty": 10.0, "avg_price": 65000.0, "current": 66000.0}],
    )

    pos = await broker.get_position("005930.XKRX")

    assert pos is not None
    assert pos.qty == 10.0
    assert pos.avg_price == 65000.0
    assert pos.side == "LONG"


async def test_get_position_returns_none_when_no_matching_code(monkeypatch):
    broker = _broker()
    monkeypatch.setattr(
        broker._order_client,
        "get_holdings",
        lambda: [{"code": "000660", "qty": 5.0, "avg_price": 200000.0, "current": 210000.0}],
    )

    pos = await broker.get_position("005930.XKRX")

    assert pos is None


async def test_get_position_returns_none_when_flat(monkeypatch):
    broker = _broker()
    monkeypatch.setattr(broker._order_client, "get_holdings", lambda: [])

    pos = await broker.get_position("005930.XKRX")

    assert pos is None
