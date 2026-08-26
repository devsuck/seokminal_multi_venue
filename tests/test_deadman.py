"""데드맨 스위치 테스트 — heartbeat 없음/만료 시 BUY만 차단, SELL/청산은 항상 통과."""
import datetime as dt
import os
from unittest.mock import patch

import pytest

from jarvis.execution import broker_bridge, deadman


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.config.STATE_DIR", str(tmp_path))


def test_no_heartbeat_is_expired():
    assert deadman.last_heartbeat() is None
    assert deadman.is_expired() is True


def test_fresh_heartbeat_not_expired():
    deadman.record_heartbeat()
    assert deadman.is_expired() is False


def test_stale_heartbeat_is_expired(monkeypatch):
    deadman.record_heartbeat()
    old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=deadman.deadman_days() + 1)
    monkeypatch.setattr(deadman, "last_heartbeat", lambda: old)
    assert deadman.is_expired() is True


def test_deadman_days_env_override(monkeypatch):
    monkeypatch.setenv("DEADMAN_DAYS", "3")
    assert deadman.deadman_days() == 3


def test_deadman_days_default():
    assert deadman.deadman_days() == 7


def test_gate_blocks_buy_when_expired():
    order = {"venue": "KR", "symbol": "005930", "side": "BUY", "quantity": 1, "price": 1000}
    with patch("jarvis.config.AUTONOMY_LEVEL", 6):
        with pytest.raises(broker_bridge.BrokerOrderRejected, match="deadman"):
            broker_bridge._gate(order)


def test_gate_allows_sell_when_expired():
    order = {"venue": "KR", "symbol": "005930", "side": "SELL", "quantity": 1, "price": 1000}
    with patch("jarvis.config.AUTONOMY_LEVEL", 6):
        broker_bridge._gate(order)  # raises only if blocked; risk caps not hit here


def test_gate_allows_buy_after_heartbeat():
    deadman.record_heartbeat()
    order = {"venue": "KR", "symbol": "005930", "side": "BUY", "quantity": 1, "price": 1000}
    with patch("jarvis.config.AUTONOMY_LEVEL", 6):
        broker_bridge._gate(order)


def test_route_close_ignores_deadman():
    """route_close()는 deadman 모듈을 거치지 않음 — 청산은 항상 허용(만료 상태에서도)."""
    import ast
    import pathlib
    src = pathlib.Path(broker_bridge.__file__).read_text()
    tree = ast.parse(src)
    route_close = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "route_close")
    assert "deadman" not in ast.dump(route_close)
