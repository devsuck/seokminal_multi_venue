"""sharp_wallet 컨버전스 신호 paper 집행봇 — 진입 로직 테스트."""
from unittest.mock import patch

import pandas as pd

from api_server import polymarket_sharp_wallet_bot as bot


def _cfg(**over):
    return {**bot._DEFAULT, "enabled": True, "positions": [], **over}


def _market(condition_id="c1", yes=0.5, no=0.5, active=True, closed=False, clob_token_ids=("t-yes", "t-no")):
    return {"condition_id": condition_id, "yes_price": yes, "no_price": no,
            "active": active, "closed": closed, "clob_token_ids": clob_token_ids}


def _anchors(rows):
    cols = ["ts", "condition_id", "side", "direction", "notional_usd",
            "proxy_wallet", "convergence_count", "convergence_bucket"]
    return pd.DataFrame(rows, columns=cols)


def _anchor_row(ts=100.0, cid="c1", bucket=1, direction=1.0, wallet="0xsharp"):
    return {"ts": ts, "condition_id": cid, "side": "BUY", "direction": direction,
            "notional_usd": 500.0, "proxy_wallet": wallet,
            "convergence_count": bucket, "convergence_bucket": bucket}


def test_scan_and_enter_bucket1_opens_three_parallel_positions():
    cfg = _cfg(trade_size_usd=10.0, budget=100.0, max_concurrent_positions=20)
    anchors = _anchors([_anchor_row(ts=100.0, bucket=1)])
    with patch.object(bot, "load_sharp_wallet_trades", return_value=pd.DataFrame()), \
         patch.object(bot, "build_convergence_count", return_value=anchors), \
         patch.object(bot, "get_market", return_value=_market(yes=0.6)), \
         patch.object(bot, "_spread_bps_for_market", return_value=150.0), \
         patch.object(bot, "_wallet_snapshot_safe", return_value=[{"conditionId": "c1"}]), \
         patch.object(bot, "_log_event"):
        entered = bot._scan_and_enter(cfg)
    assert entered == 3
    horizons = sorted(p["horizon_s"] for p in cfg["positions"])
    assert horizons == [30, 120, 300]
    for p in cfg["positions"]:
        assert p["condition_id"] == "c1"
        assert p["convergence_bucket"] == 1
        assert p["entry_price"] == 0.6
        assert p["exit_at"] == 100.0 + p["horizon_s"]
        assert p["usd"] == 10.0
        assert p["entry_spread_bps"] == 150.0
        assert p["wallet_positions_snapshot"] == [{"conditionId": "c1"}]
    assert cfg["spent"] == 30.0
    assert cfg["last_anchor_ts"] == 100.0


def test_scan_and_enter_bucket3_opens_only_300s():
    cfg = _cfg(trade_size_usd=10.0, budget=100.0)
    anchors = _anchors([_anchor_row(ts=100.0, bucket=3)])
    with patch.object(bot, "load_sharp_wallet_trades", return_value=pd.DataFrame()), \
         patch.object(bot, "build_convergence_count", return_value=anchors), \
         patch.object(bot, "get_market", return_value=_market()), \
         patch.object(bot, "_spread_bps_for_market", return_value=None), \
         patch.object(bot, "_wallet_snapshot_safe", return_value=[]), \
         patch.object(bot, "_log_event"):
        entered = bot._scan_and_enter(cfg)
    assert entered == 1
    assert cfg["positions"][0]["horizon_s"] == 300


def test_scan_and_enter_bucket2_skips_entirely():
    cfg = _cfg()
    anchors = _anchors([_anchor_row(ts=100.0, bucket=2)])
    with patch.object(bot, "load_sharp_wallet_trades", return_value=pd.DataFrame()), \
         patch.object(bot, "build_convergence_count", return_value=anchors), \
         patch.object(bot, "get_market") as mock_market:
        entered = bot._scan_and_enter(cfg)
    assert entered == 0
    assert cfg["positions"] == []
    mock_market.assert_not_called()  # bucket2는 시장조회까지 갈 필요 없이 걸러짐
    assert cfg["last_anchor_ts"] == 100.0  # 그래도 재처리 방지용으로 진행은 시킴


def test_scan_and_enter_dedups_already_processed_anchors():
    cfg = _cfg(last_anchor_ts=100.0)
    anchors = _anchors([_anchor_row(ts=100.0, bucket=1), _anchor_row(ts=50.0, bucket=1)])
    with patch.object(bot, "load_sharp_wallet_trades", return_value=pd.DataFrame()), \
         patch.object(bot, "build_convergence_count", return_value=anchors), \
         patch.object(bot, "get_market") as mock_market:
        entered = bot._scan_and_enter(cfg)
    assert entered == 0
    mock_market.assert_not_called()


def test_scan_and_enter_respects_max_concurrent_positions():
    cfg = _cfg(trade_size_usd=10.0, budget=1000.0, max_concurrent_positions=2)
    anchors = _anchors([_anchor_row(ts=100.0, bucket=1)])  # bucket1 = 3개 시도
    with patch.object(bot, "load_sharp_wallet_trades", return_value=pd.DataFrame()), \
         patch.object(bot, "build_convergence_count", return_value=anchors), \
         patch.object(bot, "get_market", return_value=_market()), \
         patch.object(bot, "_spread_bps_for_market", return_value=None), \
         patch.object(bot, "_wallet_snapshot_safe", return_value=[]), \
         patch.object(bot, "_log_event"):
        entered = bot._scan_and_enter(cfg)
    assert entered == 2  # 캡에서 멈춤


def test_scan_and_enter_no_slots_returns_zero_without_loading_trades():
    cfg = _cfg(max_concurrent_positions=1, positions=[{"condition_id": "x"}])
    with patch.object(bot, "load_sharp_wallet_trades") as mock_load:
        entered = bot._scan_and_enter(cfg)
    assert entered == 0
    mock_load.assert_not_called()


def test_scan_and_enter_market_fetch_failure_skips_anchor_but_continues():
    # get_market()은 재시도 실패시 None이 아니라 예외를 raise한다(polymarket/client.py).
    # 앞선 anchor(c1) 조회가 raise해도 스캔 전체가 abort되면 안 되고,
    # 뒤의 anchor(c2)는 정상 진입되며 last_anchor_ts도 c2까지 갱신돼야 한다.
    cfg = _cfg(trade_size_usd=10.0, budget=100.0, max_concurrent_positions=20)
    anchors = _anchors([
        _anchor_row(ts=100.0, cid="c1", bucket=1),
        _anchor_row(ts=200.0, cid="c2", bucket=1),
    ])

    def _get_market_side_effect(condition_id):
        if condition_id == "c1":
            raise RuntimeError("network fail after 3 retries")
        return _market(condition_id="c2", yes=0.6)

    with patch.object(bot, "load_sharp_wallet_trades", return_value=pd.DataFrame()), \
         patch.object(bot, "build_convergence_count", return_value=anchors), \
         patch.object(bot, "get_market", side_effect=_get_market_side_effect), \
         patch.object(bot, "_spread_bps_for_market", return_value=None), \
         patch.object(bot, "_wallet_snapshot_safe", return_value=[]), \
         patch.object(bot, "_log_event"):
        entered = bot._scan_and_enter(cfg)
    assert entered == 3  # c1 실패로 스킵, c2(bucket1)는 30/120/300s 3개 정상 진입
    assert all(p["condition_id"] == "c2" for p in cfg["positions"])
    assert cfg["last_anchor_ts"] == 200.0  # 실패한 c1도 "처리됨"으로 카운트, 재스캔 안 함
