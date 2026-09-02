"""api_watchdog 다운/복구 감지 + 알림 dedup 테스트."""
import urllib.error
import urllib.request

import ops.api_watchdog as watchdog


class _FakeResp:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _raise_urlerror(*a, **k):
    raise urllib.error.URLError("down")


def test_down_then_up_sends_alert_and_recovery(monkeypatch):
    watchdog._DOWN = False
    sent = []
    killed = []
    monkeypatch.setattr("api_server.lv6_notify.send", lambda text: sent.append(text))
    monkeypatch.setattr(watchdog, "_kill_port", lambda: killed.append(True))

    monkeypatch.setattr(urllib.request, "urlopen", _raise_urlerror)
    assert watchdog.run_once() is False
    assert killed == [True]
    assert "실패" in sent[0]

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _FakeResp(200))
    assert watchdog.run_once() is True
    assert "복구" in sent[1]


def test_stays_down_only_alerts_once(monkeypatch):
    watchdog._DOWN = False
    sent = []
    monkeypatch.setattr("api_server.lv6_notify.send", lambda text: sent.append(text))
    monkeypatch.setattr(watchdog, "_kill_port", lambda: None)
    monkeypatch.setattr(urllib.request, "urlopen", _raise_urlerror)
    watchdog.run_once()
    watchdog.run_once()
    assert len(sent) == 1


def test_rss_over_limit_restarts_even_when_healthy(monkeypatch):
    watchdog._DOWN = False
    sent = []
    killed = []
    monkeypatch.setattr("api_server.lv6_notify.send", lambda text: sent.append(text))
    monkeypatch.setattr(watchdog, "_kill_port", lambda: killed.append(True))
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _FakeResp(200))
    monkeypatch.setattr(watchdog, "_rss_mb_over_limit", lambda: 4200.0)

    assert watchdog.run_once() is False
    assert killed == [True]
    assert "메모리" in sent[0]
