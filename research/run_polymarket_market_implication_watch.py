"""Polymarket 함의관계 후보쌍 가격 재조회 — 시간당 1회, LLM 호출 없음.

pairs.jsonl의 확정 쌍만 대상으로 clob_client.get_order_book()에서 현재
best_bid/ask를 읽어 hypotheses/polymarket_market_implication.py의
compute_violation()으로 위반 여부를 판정, violations.jsonl에 기록한다
(spec §5.2). v1은 로깅만 — 실주문 없음(spec §7). 이미 두 마켓 다 resolve된
(closed) 위반건은 polymarket/client.get_market()으로 사후 pnl을 계산해
violations.jsonl에 갱신한다(spec §6-2)."""
from __future__ import annotations

import datetime as dt
import json
import logging
import time
from pathlib import Path

from polymarket.client import get_market
from polymarket.clob_client import get_order_book, spread_bps_from_book
from research.hypotheses.polymarket_market_implication import compute_violation
from research.validation.cost_model import POLYMARKET_SPREAD_BPS

_DATA_DIR = Path("research/data/polymarket_market_implication")

WATCH_INTERVAL_S = 3600.0


def load_pairs() -> list[dict]:
    path = _DATA_DIR / "pairs.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def load_violations() -> list[dict]:
    path = _DATA_DIR / "violations.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def save_violations(violations: list[dict]) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _DATA_DIR / "violations.jsonl"
    body = "\n".join(json.dumps(v, ensure_ascii=False) for v in violations)
    path.write_text(body + "\n" if violations else "")


def check_pair(pair: dict, get_book_fn=get_order_book) -> dict | None:
    book_a = get_book_fn(pair["token_id_a"])
    book_b = get_book_fn(pair["token_id_b"])
    if book_a is None or book_b is None:
        return None
    price_a = (book_a["best_bid"] + book_a["best_ask"]) / 2.0
    price_b = (book_b["best_bid"] + book_b["best_ask"]) / 2.0
    spread_a = spread_bps_from_book(book_a) or POLYMARKET_SPREAD_BPS
    spread_b = spread_bps_from_book(book_b) or POLYMARKET_SPREAD_BPS
    violation = compute_violation(
        pair["pattern_type"], pair.get("direction"), price_a, price_b, spread_a, spread_b,
    )
    if violation is None:
        return None
    return {
        **violation,
        "pair_key": pair["pair_key"],
        "condition_id_a": pair["condition_id_a"],
        "condition_id_b": pair["condition_id_b"],
        "direction": pair.get("direction"),
        "detected_ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        "price_a": round(price_a, 4),
        "price_b": round(price_b, 4),
        "resolved": False,
    }


def resolve_pnl(violation: dict, market_a: dict, market_b: dict) -> dict | None:
    """두 마켓 다 closed면 헤지 양다리(위반 방향) 사후 pnl 계산. 아직이면 None."""
    if not (market_a.get("closed") and market_b.get("closed")):
        return None
    final_a, final_b = market_a["yes_price"], market_b["yes_price"]
    entry_a, entry_b = violation["price_a"], violation["price_b"]
    if violation["pattern_type"] == "A":
        if violation.get("direction") == "a_implies_b":
            implying_entry, implying_final = entry_a, final_a
            implied_entry, implied_final = entry_b, final_b
        else:
            implying_entry, implying_final = entry_b, final_b
            implied_entry, implied_final = entry_a, final_a
        pnl = (implying_entry - implying_final) + (implied_final - implied_entry)
    else:
        pnl = (entry_a - final_a) + (entry_b - final_b)
    pnl -= violation["cost_frac"]
    return {**violation, "resolved": True, "pnl_per_share": round(pnl, 4)}


def run_once(*, get_book_fn=get_order_book, append_new: bool = True) -> list[dict]:
    detected = []
    for pair in load_pairs():
        v = check_pair(pair, get_book_fn)
        if v is not None:
            detected.append(v)
    if detected and append_new:
        existing = load_violations()
        existing.extend(detected)
        save_violations(existing)
    return detected


def resolve_pending(*, get_market_fn=get_market) -> int:
    """미해결 violation 중 두 마켓 다 resolve된 건을 사후 pnl로 갱신. 갱신 건수 반환."""
    violations = load_violations()
    updated = 0
    for v in violations:
        if v.get("resolved"):
            continue
        market_a = get_market_fn(v["condition_id_a"])
        market_b = get_market_fn(v["condition_id_b"])
        if market_a is None or market_b is None:
            continue
        result = resolve_pnl(v, market_a, market_b)
        if result is not None:
            v.update(result)
            updated += 1
    save_violations(violations)
    return updated


def run_forever(*, interval_s: float = WATCH_INTERVAL_S, max_cycles: int | None = None) -> None:
    cycle = 0
    while max_cycles is None or cycle < max_cycles:
        try:
            new_violations = run_once()
            resolved_count = resolve_pending()
            logging.info(
                "polymarket market-implication watch: %d new, %d resolved",
                len(new_violations), resolved_count,
            )
        except Exception:
            logging.exception("polymarket market-implication watch failed, continuing")
        time.sleep(interval_s)
        cycle += 1


if __name__ == "__main__":
    run_forever()
