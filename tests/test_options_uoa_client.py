"""_SCAN_TIMEOUT 하드 데드라인 — DNS 행처럼 requests timeout=이 못 막는 무한대기를
티커 단위로 잘라내는지 확인 (2026-09-03 실서버 행: socket.getaddrinfo가 무기한 블록)."""
import time
from unittest.mock import patch

from insider.options_uoa_client import get_unusual_options_activity


def test_hung_ticker_does_not_block_the_rest():
    def fake_scan(ticker, *_a, **_kw):
        if ticker == "STUCK":
            time.sleep(5)  # _SCAN_TIMEOUT(20s)보다 짧게 잡아 테스트 자체를 빠르게 유지
            return []
        return [{"ticker": ticker, "vol_oi_ratio": 1.0}]

    with patch("insider.options_uoa_client._KEY", "test-key"), \
         patch("insider.options_uoa_client._SCAN_TIMEOUT", 0.2), \
         patch("insider.options_uoa_client._scan_ticker", side_effect=fake_scan):
        out = get_unusual_options_activity(["AAPL", "STUCK", "MSFT"])

    tickers = {r["ticker"] for r in out}
    assert tickers == {"AAPL", "MSFT"}  # STUCK은 데드라인 넘겨 건너뜀, 나머지는 정상 반환


def test_normal_scan_still_works():
    with patch("insider.options_uoa_client._KEY", "test-key"), \
         patch("insider.options_uoa_client._scan_ticker", return_value=[{"ticker": "AAPL", "vol_oi_ratio": 2.0}]):
        out = get_unusual_options_activity(["AAPL"])
    assert out == [{"ticker": "AAPL", "vol_oi_ratio": 2.0}]
