import pytest

from api_server import oms


@pytest.fixture(autouse=True)
def _clear_orders(monkeypatch):
    monkeypatch.setattr(oms, "_orders", {})


def test_record_event_noop_without_order_id():
    oms.record_event("KR", {"status": "SUBMITTED", "filled": 0.0, "remaining": 1.0})
    assert oms.list_orders() == []


def test_place_then_status_tracks_open_to_filled():
    oms.record_event("KR", {"order_id": "1", "status": "SUBMITTED", "filled": 0.0, "remaining": 1.0})
    assert oms.get_order("KR", "1")["status"] == "OPEN"

    oms.record_event("KR", {"order_id": "1", "status": "OPEN", "filled": 0.5, "remaining": 0.5})
    assert oms.get_order("KR", "1")["status"] == "PARTIALLY_FILLED"

    oms.record_event("KR", {"order_id": "1", "status": "FILLED", "filled": 1.0, "remaining": 0.0})
    order = oms.get_order("KR", "1")
    assert order["status"] == "FILLED"
    assert len(order["history"]) == 3


def test_cancel_marks_cancelled():
    oms.record_event("US", {"order_id": "5", "status": "SUBMITTED", "filled": 0.0, "remaining": 1.0})
    oms.record_event("US", {"order_id": "5", "status": "CANCELLED", "filled": 0.0, "remaining": 0.0})
    assert oms.get_order("US", "5")["status"] == "CANCELLED"


def test_terminal_state_is_not_overwritten_by_later_event():
    oms.record_event("US", {"order_id": "9", "status": "FILLED", "filled": 1.0, "remaining": 0.0})
    oms.record_event("US", {"order_id": "9", "status": "SUBMITTED", "filled": 0.0, "remaining": 1.0})
    order = oms.get_order("US", "9")
    assert order["status"] == "FILLED"
    assert len(order["history"]) == 2  # 무시된 이벤트도 history엔 남음


def test_venues_are_isolated_for_same_order_id():
    oms.record_event("KR", {"order_id": "1", "status": "FILLED", "filled": 1.0, "remaining": 0.0})
    assert oms.get_order("US", "1") is None


def test_list_orders_filters_by_venue_and_status_and_sorts_newest_first():
    oms.record_event("KR", {"order_id": "1", "status": "SUBMITTED", "filled": 0.0, "remaining": 1.0})
    oms.record_event("US", {"order_id": "2", "status": "FILLED", "filled": 1.0, "remaining": 0.0})
    oms.record_event("KR", {"order_id": "3", "status": "FILLED", "filled": 1.0, "remaining": 0.0})

    assert {o["order_id"] for o in oms.list_orders(venue="KR")} == {"1", "3"}
    assert {o["order_id"] for o in oms.list_orders(status="FILLED")} == {"2", "3"}
    newest_first = oms.list_orders()
    assert newest_first[0]["order_id"] == "3"  # 마지막으로 기록된 이벤트


def test_list_orders_respects_limit():
    for i in range(5):
        oms.record_event("KR", {"order_id": str(i), "status": "SUBMITTED", "filled": 0.0, "remaining": 1.0})
    assert len(oms.list_orders(limit=2)) == 2


def test_symbol_and_side_are_captured_at_placement_and_stick():
    oms.record_event("KR", {"order_id": "1", "status": "SUBMITTED", "filled": 0.0, "remaining": 1.0},
                      symbol="005930", side="BUY")
    order = oms.get_order("KR", "1")
    assert order["symbol"] == "005930"
    assert order["side"] == "BUY"

    # 상태 조회 콜은 symbol/side 없이 오지만 기존 값이 유지되어야 함.
    oms.record_event("KR", {"order_id": "1", "status": "FILLED", "filled": 1.0, "remaining": 0.0})
    order = oms.get_order("KR", "1")
    assert order["symbol"] == "005930"
    assert order["side"] == "BUY"


def test_price_captured_from_avg_fill_price():
    oms.record_event("US", {"order_id": "1", "status": "SUBMITTED", "filled": 0.0, "remaining": 1.0})
    assert oms.get_order("US", "1")["price"] is None

    oms.record_event("US", {"order_id": "1", "status": "FILLED", "filled": 1.0, "remaining": 0.0,
                             "avg_fill_price": 190.5})
    assert oms.get_order("US", "1")["price"] == 190.5


def test_price_captured_from_filled_avg_price_alpaca_field():
    oms.record_event("US", {"order_id": "1", "status": "FILLED", "filled": 1.0, "remaining": 0.0,
                             "filled_avg_price": 42.0})
    assert oms.get_order("US", "1")["price"] == 42.0


def test_price_still_refines_after_terminal_state():
    # IB는 Filled 상태가 avg_fill_price보다 먼저 찍힐 수 있음 — 종결 후에도
    # price는 갱신돼야 늦게 온 실 체결가를 놓치지 않음(status/filled는 잠김).
    oms.record_event("US", {"order_id": "1", "status": "FILLED", "filled": 1.0, "remaining": 0.0})
    oms.record_event("US", {"order_id": "1", "status": "FILLED", "filled": 1.0, "remaining": 0.0,
                             "avg_fill_price": 101.25})
    order = oms.get_order("US", "1")
    assert order["price"] == 101.25
    assert order["status"] == "FILLED"
