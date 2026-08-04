"""Polymarket 크로스이벤트 함의관계 후보쌍 발굴 — 일 1회 스캔.

polymarket/client.py의 get_markets()로 활성마켓 전체를 받아 거래량 컷 후
스냅샷 저장, entity_tags.py로 엔티티 태깅(캐시), pairing.py로 만기근접
후보쌍 필터, 미판정 쌍만 hypotheses/polymarket_market_implication.py의
LLM 함의판정 호출해 pairs.jsonl에 append한다(spec §4, §5.1). LLM_DAILY_CALL_CAP은
엔티티태깅+함의판정 합산 — 태깅에서 다 쓰면 판정은 이번 사이클 스킵,
다음날 이어서 처리한다."""
from __future__ import annotations

import datetime as dt
import json
import logging
import time
from pathlib import Path

from polymarket.client import get_markets
from research.hypotheses.polymarket_market_implication import classify_implication_llm
from research.polymarket_market_implication import entity_tags, pairing

_DATA_DIR = Path("research/data/polymarket_market_implication")

SCAN_INTERVAL_S = 86400.0
MIN_VOLUME_USD = 500.0
LLM_DAILY_CALL_CAP = 500


def pair_key(a: dict, b: dict) -> str:
    return "|".join(sorted((a["condition_id"], b["condition_id"])))


def snapshot_markets(markets: list[dict]) -> None:
    if not markets:
        return
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _DATA_DIR / f"{dt.datetime.now(dt.timezone.utc).date().isoformat()}.jsonl"
    with path.open("a") as f:
        for m in markets:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")


def load_existing_pair_keys() -> set[str]:
    path = _DATA_DIR / "pairs.jsonl"
    if not path.exists():
        return set()
    keys = set()
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            keys.add(json.loads(line)["pair_key"])
    return keys


def append_pairs(pairs: list[dict]) -> None:
    if not pairs:
        return
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _DATA_DIR / "pairs.jsonl"
    with path.open("a") as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")


def run_once(
    *,
    get_markets_fn=get_markets,
    extract_fn=entity_tags.extract_entities_llm,
    classify_fn=classify_implication_llm,
    call_cap: int = LLM_DAILY_CALL_CAP,
) -> dict:
    markets = get_markets_fn(limit=300)
    markets = [m for m in markets if m.get("volume", 0) >= MIN_VOLUME_USD]
    snapshot_markets(markets)

    cache = entity_tags.load_cache()
    tagged, updated_cache, entity_calls = entity_tags.tag_markets(
        markets, cache, extract_fn=extract_fn, max_new_calls=call_cap,
    )
    entity_tags.save_cache(updated_cache)

    remaining = max(call_cap - entity_calls, 0)
    existing_keys = load_existing_pair_keys()
    candidates = [
        (a, b) for a, b in pairing.candidate_pairs(tagged)
        if pair_key(a, b) not in existing_keys
    ]
    attempt = candidates[:remaining]

    new_pairs = []
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    for a, b in attempt:
        classification = classify_fn(a, b)
        if classification is None:
            continue
        new_pairs.append({
            "pair_key": pair_key(a, b),
            "condition_id_a": a["condition_id"],
            "condition_id_b": b["condition_id"],
            "token_id_a": a["clob_token_ids"][0],
            "token_id_b": b["clob_token_ids"][0],
            "question_a": a["question"],
            "question_b": b["question"],
            "end_date_a": a["end_date"],
            "end_date_b": b["end_date"],
            "pattern_type": classification["pattern_type"],
            "direction": classification.get("direction"),
            "created_ts": now_iso,
        })
    append_pairs(new_pairs)

    return {
        "markets_scanned": len(markets),
        "entity_calls_used": entity_calls,
        "classify_calls_used": len(attempt),
        "pairs_added": len(new_pairs),
    }


def run_forever(*, interval_s: float = SCAN_INTERVAL_S, max_cycles: int | None = None) -> None:
    cycle = 0
    while max_cycles is None or cycle < max_cycles:
        try:
            result = run_once()
            logging.info("polymarket market-implication scan: %s", result)
        except Exception:
            logging.exception("polymarket market-implication scan failed, continuing")
        time.sleep(interval_s)
        cycle += 1


if __name__ == "__main__":
    run_forever()
