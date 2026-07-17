import pytest


@pytest.fixture(autouse=True)
def _reset_pooled_order_state():
    """api_server.main의 풀링된 IB 주문 클라이언트 + 멱등성 캐시 + OMS 상태는 모듈
    전역이라 테스트 간 그대로 누수됨(다른 테스트가 심어둔 mock 인스턴스/주문 상태를
    재사용해버림). 전체 스위트 공통으로 매 테스트 전후 리셋."""
    import api_server.main as main_mod
    from api_server import idempotency, oms

    main_mod._ib_order_clients.clear()
    idempotency._cache.clear()
    oms._orders.clear()
    yield
    main_mod._ib_order_clients.clear()
    idempotency._cache.clear()
    oms._orders.clear()
