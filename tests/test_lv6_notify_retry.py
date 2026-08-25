"""lv6_notify._send(): 429는 retry_after만큼 대기 후 재시도, 그 외 실패는 조용히 드롭."""
import io
import json
import urllib.error

from api_server import lv6_notify


def _http_error(code, body=b""):
    return urllib.error.HTTPError(url="x", code=code, msg="x", hdrs=None, fp=io.BytesIO(body))


def test_429_retries_then_succeeds(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    sleeps = []
    monkeypatch.setattr(lv6_notify.time, "sleep", lambda s: sleeps.append(s))

    body = json.dumps({"parameters": {"retry_after": 2}}).encode()
    calls = {"n": 0}

    class _Resp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def _urlopen(req, timeout, context):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _http_error(429, body)
        return _Resp()

    monkeypatch.setattr(lv6_notify.urllib.request, "urlopen", _urlopen)

    lv6_notify._send("hi")

    assert calls["n"] == 2
    assert sleeps == [2.0]


def test_429_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    sleeps = []
    monkeypatch.setattr(lv6_notify.time, "sleep", lambda s: sleeps.append(s))

    def _urlopen(req, timeout, context):
        raise _http_error(429, b"{}")

    monkeypatch.setattr(lv6_notify.urllib.request, "urlopen", _urlopen)

    lv6_notify._send("hi")  # must not raise

    assert len(sleeps) == lv6_notify._MAX_RETRIES - 1


def test_non_429_error_does_not_retry(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    monkeypatch.setattr(lv6_notify.time, "sleep", lambda s: (_ for _ in ()).throw(AssertionError("no sleep")))
    calls = {"n": 0}

    def _urlopen(req, timeout, context):
        calls["n"] += 1
        raise _http_error(500, b"{}")

    monkeypatch.setattr(lv6_notify.urllib.request, "urlopen", _urlopen)

    lv6_notify._send("hi")

    assert calls["n"] == 1


def test_retry_after_capped_at_max_backoff(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    sleeps = []
    monkeypatch.setattr(lv6_notify.time, "sleep", lambda s: sleeps.append(s))
    body = json.dumps({"parameters": {"retry_after": 999}}).encode()

    def _urlopen(req, timeout, context):
        raise _http_error(429, body)

    monkeypatch.setattr(lv6_notify.urllib.request, "urlopen", _urlopen)

    lv6_notify._send("hi")

    assert all(s == lv6_notify._MAX_BACKOFF_S for s in sleeps)
