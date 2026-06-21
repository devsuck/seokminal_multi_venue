# tests/test_ws_client.py
import json

from backends.kis.ws_client import KISWebSocketClient


class FakeConnection:
    def __init__(self, messages: list[str]) -> None:
        self.sent: list[str] = []
        self._messages = messages

    async def send(self, message: str) -> None:
        self.sent.append(message)

    def __aiter__(self):
        return self._iter_messages()

    async def _iter_messages(self):
        for message in self._messages:
            yield message

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class FakeConnect:
    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection
        self.called_with: str | None = None

    def __call__(self, uri: str):
        self.called_with = uri
        return self._connection


async def test_stream_trades_sends_subscribe_and_yields_messages():
    connection = FakeConnection(["msg1", "msg2"])
    connect_fn = FakeConnect(connection)
    client = KISWebSocketClient(approval_key="approval123", connect_fn=connect_fn)

    received = []
    async for message in client.stream_trades("005930"):
        received.append(message)

    assert received == ["msg1", "msg2"]
    assert connect_fn.called_with == "ws://ops.koreainvestment.com:21000"

    sent_envelope = json.loads(connection.sent[0])
    assert sent_envelope["header"]["approval_key"] == "approval123"
    assert sent_envelope["header"]["tr_type"] == "1"
    assert sent_envelope["body"]["input"]["tr_id"] == "H0STCNT0"
    assert sent_envelope["body"]["input"]["tr_key"] == "005930"
