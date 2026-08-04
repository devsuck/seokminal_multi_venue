"""sharp_wallet 컨버전스 신호 paper 집행봇 — 진입 로직 테스트."""
from unittest.mock import patch

import pandas as pd

from api_server import polymarket_sharp_wallet_bot as bot


def _cfg(**over):
    # last_anchor_ts는 콜드스타트 프라이밍(Fix 3) 센티널(0.0)을 우회하는 기본값 —
    # 콜드스타트 자체를 테스트하는 케이스는 명시적으로 0.0을 override한다.
    return {**bot._DEFAULT, "enabled": True, "positions": [], "last_anchor_ts": 1.0, **over}


def _market(condition_id="c1", yes=0.5, no=0.5, active=True, closed=False, clob_token_ids=("t-yes", "t-no")):
    return {"condition_id": condition_id, "yes_price": yes, "no_price": no,
            "active": active, "closed": closed, "clob_token_ids": clob_token_ids}


def _anchors(rows):
    cols = ["ts", "condition_id", "side", "direction", "notional_usd",
            "proxy_wallet", "convergence_count", "convergence_bucket", "outcome_index"]
    return pd.DataFrame(rows, columns=cols)


def _anchor_row(ts=100.0, cid="c1", bucket=1, direction=1.0, wallet="0xsharp", outcome_index=0):
    return {"ts": ts, "condition_id": cid, "side": "BUY", "direction": direction,
            "notional_usd": 500.0, "proxy_wallet": wallet,
            "convergence_count": bucket, "convergence_bucket": bucket,
            "outcome_index": outcome_index}


def test_spread_bps_for_market_uses_outcome_side_token():
    m = _market(clob_token_ids=("t-yes", "t-no"))
    with patch.object(bot, "get_order_book", return_value={"ob": 1}) as mock_book, \
         patch.object(bot, "spread_bps_from_book", return_value=42.0):
        result = bot._spread_bps_for_market(m, 1)
    mock_book.assert_called_once_with("t-no")
    assert result == 42.0


def test_scan_and_enter_bucket1_opens_single_300s_position():
    # bucket1의 30s/120s 호라이즌은 walk-forward 탈락으로 제거됨(2026-08-04) —
    # 이제 bucket1/bucket3 모두 300s 단일 호라이즌.
    cfg = _cfg(trade_size_shares=10.0, budget=100.0, max_concurrent_positions=20)
    anchors = _anchors([_anchor_row(ts=100.0, bucket=1)])
    with patch.object(bot, "load_sharp_wallet_trades", return_value=pd.DataFrame()), \
         patch.object(bot, "build_convergence_count", return_value=anchors), \
         patch.object(bot, "get_market", return_value=_market(yes=0.6)), \
         patch.object(bot, "_spread_bps_for_market", return_value=150.0), \
         patch.object(bot, "_wallet_snapshot_safe", return_value=[{"conditionId": "c1"}]), \
         patch.object(bot, "_log_event"):
        entered = bot._scan_and_enter(cfg)
    assert entered == 1
    p = cfg["positions"][0]
    assert p["horizon_s"] == 300
    assert p["condition_id"] == "c1"
    assert p["convergence_bucket"] == 1
    assert p["entry_price"] == 0.6
    assert p["exit_at"] == 100.0 + 300
    assert p["shares"] == 10.0  # 고정 shares(가격무관)
    assert p["usd"] == 6.0  # 10 shares * 0.6 entry price (derived, 고정 아님)
    assert p["entry_spread_bps"] == 150.0
    assert p["outcome_index"] == 0
    assert cfg["spent"] == 6.0
    assert cfg["last_anchor_ts"] == 100.0


def test_scan_and_enter_bucket3_opens_only_300s():
    cfg = _cfg(trade_size_shares=10.0, budget=100.0)
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
    # bucket1이 anchor당 300s 1개만 열므로, 캡을 두 anchor로 시험한다.
    cfg = _cfg(trade_size_shares=10.0, budget=1000.0, max_concurrent_positions=1)
    anchors = _anchors([
        _anchor_row(ts=100.0, cid="c1", bucket=1),
        _anchor_row(ts=200.0, cid="c2", bucket=1),
    ])
    with patch.object(bot, "load_sharp_wallet_trades", return_value=pd.DataFrame()), \
         patch.object(bot, "build_convergence_count", return_value=anchors), \
         patch.object(bot, "get_market", return_value=_market()), \
         patch.object(bot, "_spread_bps_for_market", return_value=None), \
         patch.object(bot, "_wallet_snapshot_safe", return_value=[]), \
         patch.object(bot, "_log_event"):
        entered = bot._scan_and_enter(cfg)
    assert entered == 1  # 캡(1)에서 멈춤 — c2는 시도되지 않음


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
    cfg = _cfg(trade_size_shares=10.0, budget=100.0, max_concurrent_positions=20)
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
    assert entered == 1  # c1 실패로 스킵, c2(bucket1)는 300s 1개만 정상 진입
    assert all(p["condition_id"] == "c2" for p in cfg["positions"])
    assert cfg["last_anchor_ts"] == 200.0  # 실패한 c1도 "처리됨"으로 카운트, 재스캔 안 함


# --- Fix 1: outcome_index (Yes/No 사이드) --------------------------------------

def test_scan_and_enter_uses_no_price_when_outcome_index_is_1():
    cfg = _cfg(trade_size_shares=10.0, budget=100.0, max_concurrent_positions=20)
    anchors = _anchors([_anchor_row(ts=100.0, bucket=3, outcome_index=1)])
    with patch.object(bot, "load_sharp_wallet_trades", return_value=pd.DataFrame()), \
         patch.object(bot, "build_convergence_count", return_value=anchors), \
         patch.object(bot, "get_market", return_value=_market(yes=0.3, no=0.7)), \
         patch.object(bot, "_spread_bps_for_market", return_value=100.0) as mock_spread, \
         patch.object(bot, "_wallet_snapshot_safe", return_value=[]), \
         patch.object(bot, "_log_event"):
        entered = bot._scan_and_enter(cfg)
    assert entered == 1
    pos = cfg["positions"][0]
    assert pos["entry_price"] == 0.7  # no_price, yes_price(0.3) 아님
    assert pos["outcome_index"] == 1
    mock_spread.assert_called_once()
    assert mock_spread.call_args.args[1] == 1  # No 사이드 token으로 스프레드 조회


def test_scan_and_enter_skips_anchor_with_unresolvable_outcome_index():
    cfg = _cfg(trade_size_shares=10.0, budget=100.0, max_concurrent_positions=20)
    anchors = _anchors([
        _anchor_row(ts=100.0, cid="c1", bucket=3, outcome_index=None),
        _anchor_row(ts=200.0, cid="c2", bucket=3, outcome_index=999),
        _anchor_row(ts=300.0, cid="c3", bucket=3, outcome_index=0),
    ])
    with patch.object(bot, "load_sharp_wallet_trades", return_value=pd.DataFrame()), \
         patch.object(bot, "build_convergence_count", return_value=anchors), \
         patch.object(bot, "get_market", return_value=_market(condition_id="c3", yes=0.5)), \
         patch.object(bot, "_spread_bps_for_market", return_value=None), \
         patch.object(bot, "_wallet_snapshot_safe", return_value=[]), \
         patch.object(bot, "_log_event") as mock_log:
        entered = bot._scan_and_enter(cfg)
    assert entered == 1  # c1(None), c2(999)는 skip, c3(0)만 진입
    assert len(cfg["positions"]) == 1
    assert cfg["positions"][0]["condition_id"] == "c3"
    assert cfg["last_anchor_ts"] == 300.0  # 스킵된 anchor도 처리완료로 카운트
    fail_events = [c.args[0] for c in mock_log.call_args_list if c.args[0]["kind"] == "entry_fail"]
    assert len(fail_events) == 2
    assert {e["condition_id"] for e in fail_events} == {"c1", "c2"}


def test_process_exits_marks_out_against_no_price_for_outcome_index_1():
    cfg = _cfg()
    cfg["positions"] = [_pos(outcome_index=1, entry_price=0.40, entry_spread_bps=100.0)]
    cfg["spent"] = 10.0
    with patch.object(bot, "_time") as mock_time, \
         patch.object(bot, "get_market", return_value=_market(yes=0.90, no=0.55)), \
         patch.object(bot, "_spread_bps_for_market", return_value=120.0) as mock_spread, \
         patch.object(bot, "_log_event"):
        mock_time.time.return_value = 200.0
        closed = bot._process_exits(cfg)
    assert closed == 1
    mock_spread.assert_called_once()
    assert mock_spread.call_args.args[1] == 1
    # cost_bps = polymarket_effective_cost_bps(spread_bps=(100+120)/2) = 0 + 110/2 = 55
    expected_cost = (0.40 + 0.55) * 20.0 * 55.0 / 10_000.0
    expected_pnl = round(1.0 * (0.55 - 0.40) * 20.0 - expected_cost, 2)
    assert cfg["realized_pnl"] == expected_pnl  # no_price(0.55) 기준, yes_price(0.90) 아님


# --- Fix 2: 고정 shares(가격무관) 사이징 -----------------------------------------

def test_scan_and_enter_fixed_shares_scales_usd_with_price():
    cfg = _cfg(trade_size_shares=30.0, budget=1000.0, max_concurrent_positions=20)
    anchors = _anchors([
        _anchor_row(ts=100.0, cid="cheap", bucket=3),
        _anchor_row(ts=200.0, cid="rich", bucket=3),
    ])

    def _get_market_side_effect(condition_id):
        if condition_id == "cheap":
            return _market(condition_id="cheap", yes=0.10)
        return _market(condition_id="rich", yes=0.80)

    with patch.object(bot, "load_sharp_wallet_trades", return_value=pd.DataFrame()), \
         patch.object(bot, "build_convergence_count", return_value=anchors), \
         patch.object(bot, "get_market", side_effect=_get_market_side_effect), \
         patch.object(bot, "_spread_bps_for_market", return_value=None), \
         patch.object(bot, "_wallet_snapshot_safe", return_value=[]), \
         patch.object(bot, "_log_event"):
        entered = bot._scan_and_enter(cfg)
    assert entered == 2
    cheap_pos = next(p for p in cfg["positions"] if p["condition_id"] == "cheap")
    rich_pos = next(p for p in cfg["positions"] if p["condition_id"] == "rich")
    assert cheap_pos["shares"] == rich_pos["shares"] == 30.0  # 같은 shares
    assert cheap_pos["usd"] == 3.0  # 30 * 0.10
    assert rich_pos["usd"] == 24.0  # 30 * 0.80 — 다른 usd(가격 비례)


def test_set_config_updates_trade_size_shares():
    with patch.object(bot, "_load", return_value=dict(bot._DEFAULT)), \
         patch.object(bot, "_save"), patch.object(bot, "_log_event"):
        result = bot.set_config(bot.BotConfig(trade_size_shares=50.0))
    assert result["trade_size_shares"] == 50.0


# --- Fix 3: 콜드스타트 프라이밍 ---------------------------------------------------

def test_scan_and_enter_cold_start_primes_without_entering():
    cfg = _cfg(last_anchor_ts=0.0, trade_size_shares=10.0, budget=100.0, max_concurrent_positions=20)
    anchors = _anchors([
        _anchor_row(ts=100.0, cid="stale1", bucket=1),
        _anchor_row(ts=500.0, cid="stale2", bucket=3),
    ])
    with patch.object(bot, "load_sharp_wallet_trades", return_value=pd.DataFrame()), \
         patch.object(bot, "build_convergence_count", return_value=anchors), \
         patch.object(bot, "get_market") as mock_market, \
         patch.object(bot, "_log_event"):
        entered = bot._scan_and_enter(cfg)
    assert entered == 0
    assert cfg["positions"] == []
    assert cfg["last_anchor_ts"] == 500.0  # 최신 anchor ts까지 당김(재진입 없이)
    mock_market.assert_not_called()


def test_scan_and_enter_second_call_after_priming_enters_normally():
    cfg = _cfg(last_anchor_ts=500.0, trade_size_shares=10.0, budget=100.0, max_concurrent_positions=20)
    anchors = _anchors([_anchor_row(ts=600.0, cid="fresh", bucket=3)])
    with patch.object(bot, "load_sharp_wallet_trades", return_value=pd.DataFrame()), \
         patch.object(bot, "build_convergence_count", return_value=anchors), \
         patch.object(bot, "get_market", return_value=_market(condition_id="fresh", yes=0.5)), \
         patch.object(bot, "_spread_bps_for_market", return_value=None), \
         patch.object(bot, "_wallet_snapshot_safe", return_value=[]), \
         patch.object(bot, "_log_event"):
        entered = bot._scan_and_enter(cfg)
    assert entered == 1
    assert cfg["positions"][0]["condition_id"] == "fresh"
    assert cfg["last_anchor_ts"] == 600.0


# --- Fix 4: wallet snapshot는 anchor당 1회만 로그 -------------------------------

def test_scan_and_enter_logs_wallet_snapshot_once_per_anchor_not_per_horizon():
    # 이 구조적 불변식(anchor당 스냅샷 1회)은 호라이즌 개수와 무관해야 하므로,
    # 현재 라이브 설정(bucket1=300s 단일)과 별개로 다중 호라이즌을 강제해 검증한다.
    cfg = _cfg(trade_size_shares=10.0, budget=1000.0, max_concurrent_positions=20)
    anchors = _anchors([_anchor_row(ts=100.0, bucket=1)])  # bucket1 = 3 horizons(패치)
    with patch.object(bot, "load_sharp_wallet_trades", return_value=pd.DataFrame()), \
         patch.object(bot, "build_convergence_count", return_value=anchors), \
         patch.object(bot, "get_market", return_value=_market(yes=0.6)), \
         patch.object(bot, "_spread_bps_for_market", return_value=None), \
         patch.object(bot, "_wallet_snapshot_safe", return_value=[{"conditionId": "c1"}]), \
         patch.dict(bot._HORIZONS_BY_BUCKET, {1: (30, 120, 300)}), \
         patch.object(bot, "_log_event") as mock_log:
        entered = bot._scan_and_enter(cfg)
    assert entered == 3
    snapshot_events = [c.args[0] for c in mock_log.call_args_list if c.args[0]["kind"] == "wallet_snapshot"]
    assert len(snapshot_events) == 1  # horizon마다(3회) 아니라 anchor당 1회
    assert snapshot_events[0]["positions"] == [{"conditionId": "c1"}]
    assert snapshot_events[0]["condition_id"] == "c1"
    entry_events = [c.args[0] for c in mock_log.call_args_list if c.args[0]["kind"] == "entry"]
    assert len(entry_events) == 3
    assert all("wallet_positions_snapshot" not in e for e in entry_events)  # pos dict에서 제거됨


def _pos(**over):
    base = {"condition_id": "c1", "convergence_bucket": 1, "horizon_s": 30,
            "direction": 1.0, "entry_price": 0.50, "entry_ts": 100.0, "exit_at": 130.0,
            "usd": 10.0, "shares": 20.0, "entry_spread_bps": 100.0,
            "outcome_index": 0}
    base.update(over)
    return base


def test_process_exits_marks_out_at_exit_at_with_real_spread():
    cfg = _cfg()
    cfg["positions"] = [_pos()]
    cfg["spent"] = 10.0
    with patch.object(bot, "_time") as mock_time, \
         patch.object(bot, "get_market", return_value=_market(yes=0.60)), \
         patch.object(bot, "_spread_bps_for_market", return_value=120.0), \
         patch.object(bot, "_log_event"):
        mock_time.time.return_value = 200.0  # exit_at(130) 지남
        closed = bot._process_exits(cfg)
    assert closed == 1
    assert cfg["positions"] == []
    assert cfg["spent"] == 0.0
    # cost_bps = polymarket_effective_cost_bps(spread_bps=(100+120)/2) = 0 + 110/2 = 55
    expected_cost = (0.50 + 0.60) * 20.0 * 55.0 / 10_000.0
    expected_pnl = round(1.0 * (0.60 - 0.50) * 20.0 - expected_cost, 2)
    assert cfg["realized_pnl"] == expected_pnl


def test_process_exits_keeps_position_before_exit_at():
    cfg = _cfg()
    cfg["positions"] = [_pos(exit_at=130.0)]
    with patch.object(bot, "_time") as mock_time:
        mock_time.time.return_value = 129.0
        closed = bot._process_exits(cfg)
    assert closed == 0
    assert len(cfg["positions"]) == 1


def test_process_exits_retries_on_market_fetch_failure():
    cfg = _cfg()
    cfg["positions"] = [_pos(exit_at=130.0)]
    with patch.object(bot, "_time") as mock_time, \
         patch.object(bot, "get_market", return_value=None):
        mock_time.time.return_value = 200.0
        closed = bot._process_exits(cfg)
    assert closed == 0
    assert len(cfg["positions"]) == 1  # 다음 tick 재시도


def test_process_exits_falls_back_to_default_cost_when_no_spread_data():
    cfg = _cfg()
    cfg["positions"] = [_pos(entry_spread_bps=None)]
    cfg["spent"] = 10.0
    with patch.object(bot, "_time") as mock_time, \
         patch.object(bot, "get_market", return_value=_market(yes=0.55)), \
         patch.object(bot, "_spread_bps_for_market", return_value=None), \
         patch.object(bot, "_log_event"):
        mock_time.time.return_value = 200.0
        closed = bot._process_exits(cfg)
    assert closed == 1
    # 실측 스프레드 전무 -> polymarket_effective_cost_bps() 기본값(200bps 절반=100)
    from research.validation.cost_model import polymarket_effective_cost_bps
    expected_cost = (0.50 + 0.55) * 20.0 * polymarket_effective_cost_bps() / 10_000.0
    expected_pnl = round(1.0 * (0.55 - 0.50) * 20.0 - expected_cost, 2)
    assert cfg["realized_pnl"] == expected_pnl


def test_process_exits_market_fetch_exception_retries_but_continues():
    # get_market()이 raise 예외를 던지는 경우(Task 3 test와 동일 패턴).
    # 포지션 2개: c1은 get_market raise, c2는 정상 청산.
    # c1 실패가 c2 청산을 막지 않는지, c1은 다음 tick 재시도되는지 검증.
    cfg = _cfg()
    cfg["positions"] = [
        _pos(condition_id="c1", exit_at=130.0),  # get_market raise
        _pos(condition_id="c2", exit_at=130.0),  # 정상 청산
    ]
    cfg["spent"] = 20.0

    def _get_market_side_effect(condition_id):
        if condition_id == "c1":
            raise RuntimeError("network error after retries")
        return _market(condition_id="c2", yes=0.60)

    with patch.object(bot, "_time") as mock_time, \
         patch.object(bot, "get_market", side_effect=_get_market_side_effect), \
         patch.object(bot, "_spread_bps_for_market", return_value=120.0), \
         patch.object(bot, "_log_event"):
        mock_time.time.return_value = 200.0
        closed = bot._process_exits(cfg)

    assert closed == 1  # c2만 청산
    assert len(cfg["positions"]) == 1  # c1만 유지
    assert cfg["positions"][0]["condition_id"] == "c1"  # 다음 tick 재시도
    assert cfg["spent"] == 10.0  # c2의 10.0만 차감
    # c2의 손익
    expected_cost_c2 = (0.50 + 0.60) * 20.0 * 55.0 / 10_000.0
    expected_pnl_c2 = round(1.0 * (0.60 - 0.50) * 20.0 - expected_cost_c2, 2)
    assert cfg["realized_pnl"] == expected_pnl_c2


def test_tick_disabled_skips():
    with patch.object(bot, "_load", return_value=dict(bot._DEFAULT)):
        result = bot.tick()
    assert result == {"skipped": "disabled"}


def test_tick_runs_exits_then_entries_and_saves():
    cfg = _cfg()
    with patch.object(bot, "_load", return_value=cfg), \
         patch.object(bot, "_save") as mock_save, \
         patch.object(bot, "_process_exits", return_value=1) as mock_exits, \
         patch.object(bot, "_scan_and_enter", return_value=2) as mock_enter:
        result = bot.tick()
    mock_exits.assert_called_once_with(cfg)
    mock_enter.assert_called_once_with(cfg)
    assert mock_save.call_count == 2  # 청산 저장 -> 진입 저장(다각화 봇과 동일 2단계 flush)
    assert result == {"entered": 2, "closed": 1, "positions": 0,
                       "spent": cfg["spent"], "realized_pnl": cfg["realized_pnl"]}


def test_status_endpoint_shape():
    with patch.object(bot, "_load", return_value=dict(bot._DEFAULT)), \
         patch.object(bot, "_recent_log", return_value=[]):
        result = bot.status()
    assert result["enabled"] is False
    assert result["interval_sec"] == 15
    assert result["positions"] == []
    assert "note" in result


def test_run_now_calls_tick():
    with patch.object(bot, "tick", return_value={"ok": True}) as mock_tick:
        result = bot.run_now()
    mock_tick.assert_called_once()
    assert result == {"ok": True}


def test_set_config_clamps_interval_sec_min_5():
    with patch.object(bot, "_load", return_value=dict(bot._DEFAULT)), \
         patch.object(bot, "_save"), patch.object(bot, "_log_event"):
        result = bot.set_config(bot.BotConfig(interval_sec=1))
    assert result["interval_sec"] == 5
