import json

import research.run_polymarket_bot_diversification_validate as val


def _row(ts, entry_price, won):
    return {"kind": "resolve", "entry_price": entry_price, "payout": 1 if won else 0, "ts": ts}


def test_load_resolved_filters_kind_and_sorts(tmp_path):
    path = tmp_path / "log.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in [
        {"kind": "config", "ts": "2026-01-01"},
        _row("2026-01-03", 0.6, True),
        _row("2026-01-02", 0.6, False),
    ]))
    rows = val.load_resolved(path)
    assert [r["ts"] for r in rows] == ["2026-01-02", "2026-01-03"]


def test_load_resolved_missing_file(tmp_path):
    assert val.load_resolved(tmp_path / "nope.jsonl") == []


def test_trade_pnl_matches_bot_payout_arithmetic():
    # 진입가 0.5, 스테이크 20 → 승리시 shares=40, payout=40, gross=20(코스트 차감 전)
    net, cost = val._trade_pnl(0.5, won=True)
    assert round(net, 6) == round(20.0 - cost, 6)
    assert cost > 0
    net_loss, cost_loss = val._trade_pnl(0.5, won=False)
    assert round(net_loss, 6) == round(-20.0 - cost_loss, 6)
    assert cost_loss < cost  # 패배는 exit_price=0 → 코스트 절반만(왕복 중 진입 레그만)


def test_split_bands_median_split():
    rows = [_row("t", p, True) for p in [0.5, 0.6, 0.7, 0.8]]
    bands = val._split_bands(rows)
    assert len(bands["mid_favorite"]) == 2
    assert len(bands["heavy_favorite"]) == 2


def test_compute_report_no_data():
    rep = val.compute_report([])
    assert rep["verdict"] == "no_data"
    assert rep["n_resolved"] == 0


def test_compute_report_blocked_below_min_events():
    rows = [_row(f"t{i}", 0.6, True) for i in range(4)]  # 4 < MIN_EVENTS(10), 밴드당 더 적음
    rep = val.compute_report(rows)
    assert all(v["blocked"] for v in rep["variants"])
    assert rep["verdict"] == "no_edge"  # rows 있음(no_data 아님), 살아남은 변형 없음


def test_compute_report_null_true_calibrated_market_mostly_no_edge():
    # 귀무 그대로(entry_price=진짜 승률)로 합성 → verdict가 우연히 candidate 나올 수도
    # 있지만 최소 배선(밴드 분리/BH-FDR/walk-forward)이 안 깨지는지가 핵심.
    import random
    rng = random.Random(7)
    rows = []
    for i in range(40):
        p = 0.5 + (i % 5) * 0.08  # 0.5~0.82 분산, mid/heavy 둘 다 MIN_EVENTS 넘게
        rows.append(_row(f"t{i}", p, rng.random() < p))
    rep = val.compute_report(rows)
    assert len(rep["variants"]) == 2
    assert rep["pools"][0]["n_tested"] == 2
    assert rep["verdict"] in ("no_edge", "candidate")


def test_compute_report_obvious_edge_survives_bh_and_walk_forward():
    # entry_price=0.5인데 사실상 항상 승리(진짜 확률≈1.0) → 귀무 대비 극단적으로 유의해야 함
    rows = [_row(f"t{i}", 0.5 if i % 2 == 0 else 0.8, True) for i in range(40)]
    rep = val.compute_report(rows)
    assert rep["verdict"] == "candidate"
    assert rep["pools"][0]["n_survivors"] >= 1


def test_load_and_report_missing_file(tmp_path):
    rep = val.load_and_report(tmp_path / "nope.jsonl")
    assert rep["verdict"] == "no_data"
