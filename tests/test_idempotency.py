import pytest

from api_server import idempotency


@pytest.fixture(autouse=True)
def _clear_cache(monkeypatch):
    monkeypatch.setattr(idempotency, "_cache", {})


def test_get_cached_returns_none_when_no_client_order_id():
    assert idempotency.get_cached("US", None) is None


def test_get_cached_returns_none_when_never_stored():
    assert idempotency.get_cached("US", "abc-123") is None


def test_store_then_get_cached_returns_stored_response():
    idempotency.store("US", "abc-123", {"order_id": 1, "status": "SUBMITTED"})
    assert idempotency.get_cached("US", "abc-123") == {"order_id": 1, "status": "SUBMITTED"}


def test_venues_are_isolated_for_same_client_order_id():
    idempotency.store("US", "abc-123", {"order_id": 1})
    assert idempotency.get_cached("KR", "abc-123") is None


def test_store_without_client_order_id_is_noop():
    idempotency.store("US", None, {"order_id": 1})
    assert idempotency._cache == {}


def test_expired_entry_is_evicted(monkeypatch):
    times = iter([100.0, 100.0, 500.0, 500.0])
    monkeypatch.setattr(idempotency.time, "monotonic", lambda: next(times))
    idempotency.store("US", "abc-123", {"order_id": 1})
    assert idempotency.get_cached("US", "abc-123") is None


def test_max_entries_evicts_oldest(monkeypatch):
    monkeypatch.setattr(idempotency, "_MAX_ENTRIES", 2)
    idempotency.store("US", "a", {"order_id": 1})
    idempotency.store("US", "b", {"order_id": 2})
    idempotency.store("US", "c", {"order_id": 3})
    assert idempotency.get_cached("US", "a") is None
    assert idempotency.get_cached("US", "b") == {"order_id": 2}
    assert idempotency.get_cached("US", "c") == {"order_id": 3}
