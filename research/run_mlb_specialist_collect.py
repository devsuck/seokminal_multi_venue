"""Polymarket MLB 스페셜리스트 트랙 — MLB 마켓 체결 수집기. REST 폴링, tmux 상시.

샤프월렛/whale 수집기 골격 재사용(글로벌 `/trades` 폴링, transactionHash dedup,
try/except 사이클스킵, 지수백오프). 필터 기준 = "이 체결의 마켓이 MLB인가"
(`research.mlb_specialist.market_filter.is_mlb_market`). MLB 마켓 세트는 주기 재조회.
스페셜리스트 성적 계산(정산결과)·신호 진입가용으로 MLB 마켓 상태 스냅샷도 별도 축적.

⚠️ 맥에서 마무리할 것(원격 컨테이너는 Polymarket 차단 → 라이브 미검증):
  1. `market_filter` MLB 식별 휴리스틱을 실제 폴리마켓 태그/슬러그로 튜닝.
  2. 체결의 outcome(YES/NO) 필드명이 data-api 실제 응답과 맞는지 확인(_map_trade).
  3. `run_polymarket_sharp_wallet_validate` 패턴의 walk-forward 조립(load_and_report)을
     이 수집 데이터(trades/{date}.jsonl + markets/{date}.jsonl)로 완성(스펙 §7).
순수 필터/파싱(filter_mlb_trades/_map_trade)은 유닛테스트 완료.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import time
from pathlib import Path

import requests

from research.mlb_specialist.market_filter import mlb_condition_ids

_DATA_DIR = Path("research/data/mlb_specialist")
_TRADES_URL = "https://data-api.polymarket.com/trades"
_TIMEOUT = 15

POLL_INTERVAL_S = 5.0
MARKET_REFRESH_INTERVAL_S = 600.0   # MLB 마켓 세트 + 상태 스냅샷 재조회 주기
DEDUP_HASH_RING_SIZE = 5000


def _map_trade(t: dict) -> dict:
    """raw /trades 항목 → 정규화. outcome/side는 데이터 그대로 통과(맥에서 실검증)."""
    price = float(t.get("price", 0) or 0)
    size = float(t.get("size", 0) or 0)
    return {
        "ts": float(t.get("timestamp", 0) or 0),
        "condition_id": t.get("conditionId"),
        "side": t.get("side"),
        "outcome": t.get("outcome"),
        "outcome_index": t.get("outcomeIndex"),
        "price": price,
        "size": size,
        "notional_usd": price * size,
        "proxy_wallet": t.get("proxyWallet"),
        "transactionHash": t.get("transactionHash"),
    }


def filter_mlb_trades(
    trades: list[dict],
    mlb_cids: set[str],
    seen_hashes: list[str],
) -> tuple[list[dict], list[str]]:
    """MLB 마켓(conditionId ∈ mlb_cids) 체결만 남기고 transactionHash로 dedup.
    반환: (정규화된 신규 체결, 갱신된 seen_hashes 링버퍼)."""
    seen = set(seen_hashes)
    hashes = list(seen_hashes)
    out = []
    for t in trades:
        cid = t.get("conditionId")
        h = t.get("transactionHash")
        if cid not in mlb_cids or h in seen:
            continue
        seen.add(h)
        hashes.append(h)
        out.append(_map_trade(t))
    return out, hashes[-DEDUP_HASH_RING_SIZE:]


def fetch_trades(limit: int = 500) -> list[dict]:
    r = requests.get(_TRADES_URL, params={"limit": limit}, timeout=_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


def refresh_mlb_markets() -> set[str]:
    """활성 MLB 마켓 condition_id 세트(체결 필터용).

    get_markets(거래량 top-N)가 아니라 get_mlb_game_markets(tag_slug=mlb 이벤트 직접 조회) —
    실라이브 확인(2026-07-24): top-500조차 MLB 경기 마켓을 1개밖에 못 잡았음(크립토
    up/down·e스포츠 마이크로마켓에 거래량 밀림). is_mlb_market 필터는 그대로 통과시켜
    시즌 선물(월드시리즈 우승 등, game_start_time 없음)은 mlb_condition_ids가 걸러낸다."""
    from polymarket.client import get_mlb_game_markets
    return mlb_condition_ids(get_mlb_game_markets())


def snapshot_mlb_markets(mlb_cids: set[str]) -> None:
    """MLB 마켓 상태(closed/가격) 스냅샷 append — 정산결과·진입가 시계열용.
    markets/{date}.jsonl 에 append."""
    from polymarket.client import get_market
    rows = []
    now = time.time()
    for cid in mlb_cids:
        try:
            m = get_market(cid)
        except Exception:  # noqa: BLE001
            continue
        if m is None:
            continue
        rows.append({"ts": now, "condition_id": cid, "closed": m.get("closed"),
                     "yes_price": m.get("yes_price"), "no_price": m.get("no_price")})
    if not rows:
        return
    d = _DATA_DIR / "markets"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{dt.datetime.now(dt.timezone.utc).date().isoformat()}.jsonl"
    with path.open("a") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def append_trades(trades: list[dict]) -> None:
    if not trades:
        return
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _DATA_DIR / f"{dt.datetime.now(dt.timezone.utc).date().isoformat()}.jsonl"
    with path.open("a") as f:
        for t in trades:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")


def run_forever(
    fetch_fn=fetch_trades,
    refresh_fn=refresh_mlb_markets,
    snapshot_fn=snapshot_mlb_markets,
    append_fn=append_trades,
    poll_interval_s: float = POLL_INTERVAL_S,
    market_refresh_interval_s: float = MARKET_REFRESH_INTERVAL_S,
) -> None:
    logging.basicConfig(level=logging.INFO)
    mlb_cids = refresh_fn()
    last_refresh = time.time()
    seen_hashes: list[str] = []
    backoff = poll_interval_s
    while True:
        try:
            now = time.time()
            if now - last_refresh >= market_refresh_interval_s:
                mlb_cids = refresh_fn()
                snapshot_fn(mlb_cids)
                last_refresh = now
            trades = fetch_fn()
            new, seen_hashes = filter_mlb_trades(trades, mlb_cids, seen_hashes)
            append_fn(new)
            backoff = poll_interval_s  # 성공 시 백오프 리셋
        except Exception:  # noqa: BLE001
            logging.exception("mlb collect poll failed, backing off")
            time.sleep(min(backoff, 60.0))
            backoff = min(backoff * 2, 60.0)
            continue
        time.sleep(poll_interval_s)


if __name__ == "__main__":
    run_forever()
