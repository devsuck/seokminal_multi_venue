import datetime as dt
import json

import pandas as pd

import research.run_mlb_specialist_validate as val

_UTC = dt.timezone.utc


def _ts(y, m, d, h=12):
    return dt.datetime(y, m, d, h, tzinfo=_UTC).timestamp()


def _labels(n, win=True):
    ex = 1.0 if win else 0.0
    return pd.DataFrame([
        {"condition_id": f"m{i}", "side": "YES", "entry_price": 0.5,
         "exit_price": ex, "direction": 1.0, "forward_return": (ex - 0.5) / 0.5}
        for i in range(n)
    ])


def test_enumerate_variants_grid():
    # 3 지표 × 2 임계 × 2 N = 12
    variants = val.enumerate_variants()
    assert len(variants) == 12
    assert "pnl:majority:N5" in variants
    assert "roi:unanimous:N4" in variants


def test_compute_report_no_data():
    rep = val.compute_report({})
    assert rep["hypothesis"] == "mlb_specialist_consensus"
    assert rep["verdict"] == "no_data"
    assert rep["pools"][0]["n_tested"] == 0


def test_compute_report_blocked_below_min_events():
    rep = val.compute_report({"pnl:majority:N5": _labels(3)})
    assert rep["variants"][0]["blocked"] is True
    assert rep["verdict"] == "no_data"  # 돌아간 변형 없음


def test_compute_report_single_pool_and_pvalue():
    rep = val.compute_report({
        "pnl:majority:N5": _labels(15, win=True),
        "roi:unanimous:N4": _labels(4),  # 미달 → blocked
    })
    assert len(rep["pools"]) == 1
    assert rep["pools"][0]["name"] == "mlb_specialist_consensus"
    done = [v for v in rep["variants"] if not v["blocked"]]
    assert len(done) == 1 and done[0]["n_events"] == 15
    assert done[0]["p_value"] is not None
    assert rep["pools"][0]["n_tested"] == 1
    assert rep["verdict"] in ("no_edge", "candidate")


def test_outcome_side_uses_outcome_index_not_label():
    # MLB 마켓 outcome 라벨은 팀명/"Over"/"Under" 등 제각각이라 index로만 판별
    assert val._outcome_side(0) == "YES"
    assert val._outcome_side(1) == "NO"
    assert val._outcome_side(999) is None  # 센티널/멀티아웃컴 제외
    assert val._outcome_side(None) is None


def test_build_resolutions_only_closed_with_prices():
    rows = [
        {"condition_id": "m1", "ts": 1.0, "closed": False, "yes_price": 0.5, "no_price": 0.5},
        {"condition_id": "m1", "ts": 2.0, "closed": True, "yes_price": 1.0, "no_price": 0.0},
        {"condition_id": "m2", "ts": 1.0, "closed": True, "yes_price": 0.0, "no_price": 1.0},
        {"condition_id": "m3", "ts": 1.0, "closed": False, "yes_price": 0.4, "no_price": 0.6},
    ]
    res = val._build_resolutions(rows)
    assert res == {
        "m1": {"winning_side": "YES", "resolved_ts": 2.0},
        "m2": {"winning_side": "NO", "resolved_ts": 1.0},
    }


def test_daily_positions_groups_by_utc_date_and_drops_non_binary():
    rows = [
        {"proxy_wallet": "w1", "condition_id": "m1", "outcome_index": 0, "ts": _ts(2026, 7, 19)},
        {"proxy_wallet": "w2", "condition_id": "m1", "outcome_index": 1, "ts": _ts(2026, 7, 19, 23)},
        {"proxy_wallet": "w1", "condition_id": "m2", "outcome_index": 999, "ts": _ts(2026, 7, 19)},  # 센티널 무시
        {"proxy_wallet": "w1", "condition_id": "m3", "outcome_index": 0, "ts": _ts(2026, 7, 20)},
    ]
    by_day = val._daily_positions(rows)
    assert set(by_day) == {"2026-07-19", "2026-07-20"}
    assert len(by_day["2026-07-19"]) == 2
    assert by_day["2026-07-20"] == [{"proxy_wallet": "w1", "condition_id": "m3", "side": "YES"}]


def test_load_and_report_no_data_dir(tmp_path):
    rep = val.load_and_report(str(tmp_path / "nope"))
    assert rep["verdict"] == "no_data"


def test_load_and_report_smoke(tmp_path, monkeypatch):
    # 게이트를 낮춰 소량 합성 데이터로 파이프라인 배선(walk-forward 조립→compute_report)만 검증.
    monkeypatch.setattr(val, "MIN_BETS", 2)
    monkeypatch.setattr(val, "MIN_SPEC", 0.0)
    monkeypatch.setattr(val, "MIN_PRESENT", 1)
    monkeypatch.setattr(val, "MIN_EVENTS", 1)

    base = tmp_path
    (base / "markets").mkdir(parents=True)

    # day19: specialist "w1"이 ma1/ma2 각 YES 진입, 같은 날 정산(둘 다 승) → 다음날 랭킹에 반영.
    trades_19 = [
        {"proxy_wallet": "w1", "condition_id": "ma1", "outcome_index": 0, "price": 0.5,
         "size": 10.0, "notional_usd": 5.0, "ts": _ts(2026, 7, 19, 10)},
        {"proxy_wallet": "w1", "condition_id": "ma2", "outcome_index": 0, "price": 0.5,
         "size": 10.0, "notional_usd": 5.0, "ts": _ts(2026, 7, 19, 10)},
    ]
    # day20: 같은 스페셜리스트가 mb1에 신규 포지션 → 그날 컨센서스 신호 후보.
    trades_20 = [
        {"proxy_wallet": "w1", "condition_id": "mb1", "outcome_index": 0, "price": 0.5,
         "size": 10.0, "notional_usd": 5.0, "ts": _ts(2026, 7, 20, 10)},
    ]
    (base / "2026-07-19.jsonl").write_text("\n".join(json.dumps(r) for r in trades_19))
    (base / "2026-07-20.jsonl").write_text("\n".join(json.dumps(r) for r in trades_20))

    markets = [
        # ma1/ma2: day19 정산(YES 승) — as_of(day20 00:00) 이전이라 day20 랭킹에 반영됨.
        {"condition_id": "ma1", "ts": _ts(2026, 7, 19, 20), "closed": True, "yes_price": 1.0, "no_price": 0.0},
        {"condition_id": "ma2", "ts": _ts(2026, 7, 19, 20), "closed": True, "yes_price": 1.0, "no_price": 0.0},
        # mb1: day20 진입가 스냅샷(오픈) + day21 정산(YES 승) → 라벨 승.
        {"condition_id": "mb1", "ts": _ts(2026, 7, 20, 9), "closed": False, "yes_price": 0.5, "no_price": 0.5},
        {"condition_id": "mb1", "ts": _ts(2026, 7, 21, 20), "closed": True, "yes_price": 1.0, "no_price": 0.0},
    ]
    (base / "markets" / "2026-07-21.jsonl").write_text("\n".join(json.dumps(r) for r in markets))

    rep = val.load_and_report(str(base))
    assert len(rep["variants"]) == 12
    assert all(not v["blocked"] for v in rep["variants"])
    assert all(v["n_events"] == 1 for v in rep["variants"])
    assert rep["pools"][0]["n_tested"] == 12
