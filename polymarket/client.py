"""Polymarket Gamma API 클라이언트 — 읽기전용·인증 불필요(공개 시장 데이터).

포트폴리오 다각화용 페이퍼 배스킷 봇(api_server/polymarket_bot.py)이 쓴다.
실거래(CLOB 주문 체결)는 지갑/서명이 필요해 여기선 다루지 않음 — 이 시스템은
아직 전부 paper 단계라 시세만 읽어 가상 포지션을 추적한다.
"""
from __future__ import annotations

import datetime as dt
import json
import time

import requests

_BASE = "https://gamma-api.polymarket.com"
_TIMEOUT = 15


def _get(path: str, params: dict, retries: int = 3) -> list | dict:
    for a in range(retries):
        try:
            r = requests.get(f"{_BASE}{path}", params=params, timeout=_TIMEOUT)
            if r.status_code == 429:
                time.sleep(2 * (a + 1))
                continue
            r.raise_for_status()
            return r.json()
        except Exception:
            if a == retries - 1:
                raise
            time.sleep(1.5 * (a + 1))
    return []


def _parse_json_list(raw) -> list[str]:
    if isinstance(raw, list):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return []


def _map_market(m: dict) -> dict | None:
    outcomes = _parse_json_list(m.get("outcomes"))
    prices = _parse_json_list(m.get("outcomePrices"))
    if len(outcomes) != 2 or len(prices) != 2:
        return None  # 다각화 배스킷은 단순 이진(YES/NO) 시장만 다룸
    try:
        yes_price = float(prices[0])
        no_price = float(prices[1])
    except (TypeError, ValueError):
        return None
    event = (m.get("events") or [{}])[0]
    clob_ids = _parse_json_list(m.get("clobTokenIds") or [])
    clob_token_ids = (clob_ids[0], clob_ids[1]) if len(clob_ids) == 2 else (None, None)
    return {
        "condition_id": m.get("conditionId"),
        "question": m.get("question", ""),
        "event_id": event.get("id", ""),
        "event_title": event.get("title", ""),
        "slug": m.get("slug") or event.get("slug") or "",
        "end_date": m.get("endDateIso") or (m.get("endDate") or "")[:10],
        "end_datetime": m.get("endDate") or m.get("endDateIso") or "",
        "volume": float(m.get("volumeNum") or m.get("volume") or 0),
        "liquidity": float(m.get("liquidityNum") or m.get("liquidity") or 0),
        "yes_price": yes_price,
        "no_price": no_price,
        "active": bool(m.get("active")),
        "closed": bool(m.get("closed")),
        "accepting_orders": bool(m.get("acceptingOrders")),
        "clob_token_ids": clob_token_ids,
        "sports_market_type": m.get("sportsMarketType"),
        "game_start_time": m.get("gameStartTime"),
    }


def get_markets(limit: int = 200, active: bool = True, closed: bool = False) -> list[dict]:
    """활성 시장 목록 (거래량 내림차순). 이진(YES/NO) 시장만, 정규화된 dict로."""
    raw = _get("/markets", {
        "limit": limit, "active": str(active).lower(), "closed": str(closed).lower(),
        "order": "volume", "ascending": "false",
    })
    if not isinstance(raw, list):
        return []
    out = []
    for m in raw:
        mapped = _map_market(m)
        if mapped:
            out.append(mapped)
    return out


def get_updown_markets(limit: int = 100) -> list[dict]:
    """마감임박순 크립토 up/down 마켓(슬러그: `{coin}-updown-{5m|15m}-{ts}`).

    up/down 마켓은 실제 5분/15분 판정 구간보다 ~24시간 먼저 개설되므로
    최신개설순(startDate desc)으로는 지금 막 열린(마감 한참 남은) 마켓만 잡힌다.
    end_date_min=now + order=endDate asc로 정렬해 마감이 임박한 마켓부터 받는다.
    슬러그 패턴/유동성 임계값 필터링은 research/polymarket_arb/updown_selector.py에서 한다.
    """
    now_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    raw = _get("/markets", {
        "limit": limit, "active": "true", "closed": "false",
        "tag_slug": "crypto", "order": "endDate", "ascending": "true",
        "end_date_min": now_iso,
    })
    if not isinstance(raw, list):
        return []
    out = []
    for m in raw:
        mapped = _map_market(m)
        if mapped:
            out.append(mapped)
    return out


def get_market(condition_id: str) -> dict | None:
    """단일 마켓 조회 — Gamma API는 condition_ids 필터 시 closed 여부가 쿼리의
    암묵적 기본값(=False)과 안 맞으면 빈 리스트를 반환한다. 정산 여부를 모르는
    채로 부르므로(포지션이 아직 열려있는지 만기됐는지) open→closed 순으로 재시도."""
    for closed in ("false", "true"):
        raw = _get("/markets", {"condition_ids": condition_id, "limit": 1, "closed": closed})
        if isinstance(raw, list) and raw:
            return _map_market(raw[0])
    return None
