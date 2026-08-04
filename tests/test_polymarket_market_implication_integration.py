"""collect.py → watch.py → report.py 스키마 인계가 실제로 맞물리는지 검증하는
통합 테스트. 각 태스크 테스트는 자체 fixture dict를 손으로 만들어 쓰기 때문에
필드명이 한쪽에서 바뀌어도(예: token_id_a -> token_a) 아무 테스트도 못 잡는다
— 이 테스트만 collect의 실제 출력을 watch에, watch의 실제 출력을 report에
그대로 흘려보낸다."""
from unittest.mock import patch

import research.run_polymarket_market_implication_collect as collect
import research.run_polymarket_market_implication_watch as watch
from research.polymarket_market_implication import entity_tags
from research.run_polymarket_market_implication_report import compute_report


def _market(cid, question, volume, end_date, event_id, clob):
    return {
        "condition_id": cid, "question": question, "volume": volume,
        "end_date": end_date, "event_id": event_id, "clob_token_ids": clob,
    }


def test_collect_to_watch_to_report_schema_handoff(tmp_path):
    markets = [
        _market("c1", "Will X win primary?", 1000.0, "2026-09-01", "e1", ("tok_a_yes", "tok_a_no")),
        _market("c2", "Will X win general?", 1000.0, "2026-09-10", "e2", ("tok_b_yes", "tok_b_no")),
    ]
    with patch.object(collect, "_DATA_DIR", tmp_path), \
         patch.object(watch, "_DATA_DIR", tmp_path), \
         patch.object(entity_tags, "_CACHE_PATH", tmp_path / "entity_cache.json"):
        collect_result = collect.run_once(
            get_markets_fn=lambda limit: markets,
            extract_fn=lambda q: ["X"],
            classify_fn=lambda a, b: {"pattern_type": "A", "direction": "a_implies_b"},
        )
        assert collect_result["pairs_added"] == 1

        books = {
            "tok_a_yes": {"best_bid": 0.69, "best_ask": 0.71},
            "tok_b_yes": {"best_bid": 0.49, "best_ask": 0.51},
        }
        detected = watch.run_once(get_book_fn=lambda tid: books[tid])
        assert len(detected) == 1

        violations = watch.load_violations()
        report = compute_report(violations)

    assert report["A"]["detected"] == 1
    assert report["A"]["resolved"] == 0  # 아직 두 마켓 다 closed 아님
    assert report["B"]["detected"] == 0
