import datetime as dt
import json
from unittest.mock import patch

import research.run_polymarket_market_implication_collect as runner


def _market(cid, question, volume, end_date, clob=("tok_yes", "tok_no")):
    return {
        "condition_id": cid, "question": question, "volume": volume,
        "end_date": end_date, "clob_token_ids": clob,
    }


def test_run_once_filters_by_volume_and_snapshots(tmp_path):
    markets = [
        _market("c1", "Will X win primary?", 1000.0, "2026-09-01"),
        _market("c2", "Will X win general?", 100.0, "2026-09-10"),  # MIN_VOLUME_USD 미만
    ]
    with patch.object(runner, "_DATA_DIR", tmp_path):
        result = runner.run_once(
            get_markets_fn=lambda limit: markets,
            extract_fn=lambda q: ["X"],
            classify_fn=lambda a, b: None,
        )
        snap_path = tmp_path / f"{dt.datetime.now(dt.timezone.utc).date().isoformat()}.jsonl"
        lines = snap_path.read_text().strip().splitlines()
    assert result["markets_scanned"] == 1
    assert len(lines) == 1
    assert json.loads(lines[0])["condition_id"] == "c1"


def test_run_once_llm_call_cap_reached_during_tagging_skips_classify(tmp_path):
    markets = [
        _market("c1", "Q1 about X", 1000.0, "2026-09-01"),
        _market("c2", "Q2 about X", 1000.0, "2026-09-05"),
    ]
    with patch.object(runner, "_DATA_DIR", tmp_path):
        result = runner.run_once(
            get_markets_fn=lambda limit: markets,
            extract_fn=lambda q: ["X"],
            classify_fn=lambda a, b: {"pattern_type": "B"},
            call_cap=1,
        )
    assert result["entity_calls_used"] == 1
    assert result["classify_calls_used"] == 0
    assert result["pairs_added"] == 0


def test_run_once_classifies_new_candidate_pair_and_appends(tmp_path):
    markets = [
        _market("c1", "Will X win primary?", 1000.0, "2026-09-01"),
        _market("c2", "Will X win general?", 1000.0, "2026-09-10"),
    ]
    with patch.object(runner, "_DATA_DIR", tmp_path):
        result = runner.run_once(
            get_markets_fn=lambda limit: markets,
            extract_fn=lambda q: ["X"],
            classify_fn=lambda a, b: {"pattern_type": "A", "direction": "a_implies_b"},
        )
        pairs_path = tmp_path / "pairs.jsonl"
        lines = pairs_path.read_text().strip().splitlines()
    assert result["pairs_added"] == 1
    saved = json.loads(lines[0])
    assert saved["pattern_type"] == "A"
    assert saved["token_id_a"] == "tok_yes"
    assert saved["condition_id_a"] == "c1"


def test_run_once_skips_already_judged_pair(tmp_path):
    markets = [
        _market("c1", "Will X win primary?", 1000.0, "2026-09-01"),
        _market("c2", "Will X win general?", 1000.0, "2026-09-10"),
    ]
    with patch.object(runner, "_DATA_DIR", tmp_path):
        tmp_path.mkdir(parents=True, exist_ok=True)
        existing_key = runner.pair_key(markets[0], markets[1])
        (tmp_path / "pairs.jsonl").write_text(json.dumps({"pair_key": existing_key}) + "\n")

        classify_calls = []

        def classify_fn(a, b):
            classify_calls.append((a, b))
            return {"pattern_type": "B"}

        result = runner.run_once(
            get_markets_fn=lambda limit: markets,
            extract_fn=lambda q: ["X"],
            classify_fn=classify_fn,
        )
    assert classify_calls == []
    assert result["pairs_added"] == 0
