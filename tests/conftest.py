import pytest


@pytest.fixture(autouse=True, scope="session")
def _no_real_telegram():
    """route_order 테스트가 실제 TELEGRAM_BOT_TOKEN으로 진짜 메시지를 쏘는 걸 막음
    (api_server.main import가 .env를 로드해버려서 발생). 세션 전체 no-op."""
    from unittest.mock import patch

    with patch("api_server.lv6_notify.send"):
        yield


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
