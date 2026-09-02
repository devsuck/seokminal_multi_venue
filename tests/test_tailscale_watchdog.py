"""tailscale_watchdog 로컬-vs-tailscale IP 판별 + dedup 테스트."""
import ops.tailscale_watchdog as watchdog


def test_tailscale_down_local_up_restarts_and_alerts(monkeypatch):
    watchdog._DOWN = False
    sent, restarted = [], []
    monkeypatch.setattr("api_server.lv6_notify.send", lambda text: sent.append(text))
    monkeypatch.setattr(watchdog, "_restart_tailscale", lambda: restarted.append(True))
    monkeypatch.setattr(watchdog, "_own_tailscale_ip", lambda: "100.108.67.7")
    # 127.0.0.1은 되고 tailscale IP는 안 됨
    monkeypatch.setattr(watchdog, "_url_ok", lambda url, timeout=5.0: "127.0.0.1" in url)

    assert watchdog.run_once() is False
    assert restarted == [True]
    assert "Tailscale" in sent[0]

    monkeypatch.setattr(watchdog, "_url_ok", lambda url, timeout=5.0: True)
    assert watchdog.run_once() is True
    assert "복구" in sent[1]


def test_stays_down_only_alerts_once(monkeypatch):
    watchdog._DOWN = False
    sent = []
    monkeypatch.setattr("api_server.lv6_notify.send", lambda text: sent.append(text))
    monkeypatch.setattr(watchdog, "_restart_tailscale", lambda: None)
    monkeypatch.setattr(watchdog, "_own_tailscale_ip", lambda: "100.108.67.7")
    monkeypatch.setattr(watchdog, "_url_ok", lambda url, timeout=5.0: "127.0.0.1" in url)

    watchdog.run_once()
    watchdog.run_once()
    assert len(sent) == 1


def test_local_also_down_defers_to_api_watchdog(monkeypatch):
    """로컬까지 죽으면 서버 자체 문제(api_watchdog 소관) — tailscale_watchdog은 손 안 댐."""
    watchdog._DOWN = False
    sent, restarted = [], []
    monkeypatch.setattr("api_server.lv6_notify.send", lambda text: sent.append(text))
    monkeypatch.setattr(watchdog, "_restart_tailscale", lambda: restarted.append(True))
    monkeypatch.setattr(watchdog, "_own_tailscale_ip", lambda: "100.108.67.7")
    monkeypatch.setattr(watchdog, "_url_ok", lambda url, timeout=5.0: False)

    assert watchdog.run_once() is True
    assert restarted == []
    assert sent == []


def test_interface_gone_restarts(monkeypatch):
    """tailscale 인터페이스 자체가 안 잡히는 경우(IP None)도 로컬 살아있으면 재시작 대상."""
    watchdog._DOWN = False
    sent, restarted = [], []
    monkeypatch.setattr("api_server.lv6_notify.send", lambda text: sent.append(text))
    monkeypatch.setattr(watchdog, "_restart_tailscale", lambda: restarted.append(True))
    monkeypatch.setattr(watchdog, "_own_tailscale_ip", lambda: None)
    monkeypatch.setattr(watchdog, "_url_ok", lambda url, timeout=5.0: "127.0.0.1" in url)

    assert watchdog.run_once() is False
    assert restarted == [True]
