import json

import research.hypotheses.polymarket_sharp_wallet as psw
import research.polymarket_tick.fill_sim as fill_sim
import research.run_sharp_wallet_maker_vs_taker as mvt


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_covered_anchor_produces_taker_and_filled_maker_pnl(tmp_path, monkeypatch):
    monkeypatch.setattr(psw, "_DATA_DIR", tmp_path / "sharp_wallet")
    monkeypatch.setattr(fill_sim, "_DATA_DIR", tmp_path / "tick")

    _write_jsonl(tmp_path / "sharp_wallet" / "2026-08-01.jsonl", [{
        "conditionId": "c1", "timestamp": 0.0, "side": "BUY", "price": 0.50, "size": 30.0,
        "proxyWallet": "0xsharp", "notional_usd": 15.0, "is_sharp_wallet": True,
        "wallet_rank": 1, "wallet_pnl": 1000.0, "outcomeIndex": 0,
    }])
    tick_rows = [
        {"ts": "1970-01-01T00:00:00+00:00", "condition_id": "c1", "outcome": "yes",
         "event_type": "price_change", "price": 0.50, "best_bid": 0.49, "best_ask": 0.51},
        {"ts": "1970-01-01T00:01:00+00:00", "condition_id": "c1", "outcome": "yes",
         "event_type": "price_change", "price": 0.48, "best_bid": 0.47, "best_ask": 0.49},
        {"ts": "1970-01-01T00:05:00+00:00", "condition_id": "c1", "outcome": "yes",
         "event_type": "price_change", "price": 0.60, "best_bid": 0.59, "best_ask": 0.61},
    ]
    _write_jsonl(tmp_path / "tick" / "1970-01-01.jsonl", tick_rows)

    result = mvt.run(dates=["2026-08-01"])
    assert result["anchors_total"] == 1
    assert result["covered"] == 1
    assert result["no_tick_coverage"] == 0
    assert result["taker_n"] == 1
    # direction=+1(BUY), entry~0.50, exit(마지막 프린트)~0.60 → 비용 차감 전 +0.10 근방
    assert result["taker_mean_pnl_per_share"] > 0
    assert result["maker_n_filled"] == 1
    assert result["maker_fill_rate"] == 1.0


def test_anchor_outside_tick_coverage_counts_as_no_coverage(tmp_path, monkeypatch):
    monkeypatch.setattr(psw, "_DATA_DIR", tmp_path / "sharp_wallet")
    monkeypatch.setattr(fill_sim, "_DATA_DIR", tmp_path / "tick")

    _write_jsonl(tmp_path / "sharp_wallet" / "2026-08-01.jsonl", [{
        "conditionId": "untracked-market", "timestamp": 0.0, "side": "BUY", "price": 0.5,
        "size": 30.0, "proxyWallet": "0xsharp", "notional_usd": 15.0, "is_sharp_wallet": True,
        "wallet_rank": 1, "wallet_pnl": 1000.0, "outcomeIndex": 0,
    }])

    result = mvt.run(dates=["2026-08-01"])
    assert result["anchors_total"] == 1
    assert result["covered"] == 0
    assert result["no_tick_coverage"] == 1
    assert result["taker_n"] == 0
