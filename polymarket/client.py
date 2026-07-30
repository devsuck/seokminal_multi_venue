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

from research.net_utils import call_with_hard_timeout

_BASE = "https://gamma-api.polymarket.com"
_TIMEOUT = 15
_HARD_TIMEOUT = _TIMEOUT + 5.0  # requests timeout이 못 막는 DNS/connect 단계 방어


def _get(path: str, params: dict, retries: int = 3) -> list | dict:
    for a in range(retries):
        try:
            r = call_with_hard_timeout(
                lambda: requests.get(f"{_BASE}{path}", params=params, timeout=_TIMEOUT), _HARD_TIMEOUT
            )
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


# Gamma API가 limit>100 요청을 에러 없이 조용히 100개로 잘라버림(2026-07-30 실측:
# limit=150/300/500 전부 100개만 반환, status 200). offset 페이지네이션으로 직접 모아야
# 호출부(limit=300/500 넘기는 콜렉터 6곳)가 의도한 개수를 실제로 받는다.
_PAGE_SIZE = 100


def get_markets(limit: int = 200, active: bool = True, closed: bool = False) -> list[dict]:
    """활성 시장 목록 (거래량 내림차순). 이진(YES/NO) 시장만, 정규화된 dict로."""
    raw_all: list[dict] = []
    offset = 0
    while len(raw_all) < limit:
        page_limit = min(_PAGE_SIZE, limit - offset)
        page = _get("/markets", {
            "limit": page_limit, "offset": offset,
            "active": str(active).lower(), "closed": str(closed).lower(),
            "order": "volume", "ascending": "false",
        })
        if not isinstance(page, list) or not page:
            break
        raw_all.extend(page)
        if len(page) < page_limit:
            break
        offset += page_limit
    out = []
    for m in raw_all:
        mapped = _map_market(m)
        if mapped:
            out.append(mapped)
    return out


def get_mlb_game_markets(limit: int = 200) -> list[dict]:
    """예정/진행중인 MLB 경기 이벤트(무니라인/NRFI/props 등)의 개별 마켓.

    `get_markets`(거래량 내림차순 top-N)는 크립토 up/down·e스포츠 같은 초고빈도
    마이크로마켓이 볼륨 상위를 다 차지해서 상대적으로 거래량 작은 MLB 경기 마켓이
    top-100~500 안에 거의 안 들어옴(실라이브 확인 2026-07-24: mlb_cids 1개만 잡힘).
    `/events?tag_slug=mlb`는 거래량과 무관하게 MLB 태그가 붙은 이벤트를 다 주므로 이걸 쓴다.
    ⚠️ 이벤트의 `startDate`는 경기 시각이 아니라 마켓 개설(베팅 오픈)일이라
    `start_date_min=지금`으로 걸면 이미 개설된 이벤트가 다 잘려나가 0건이 됨(실라이브
    확인 2026-07-24) — date 필터 없이 startDate 내림차순(최근 개설=임박/당일 경기 우선)만
    쓴다. 실제 "경기가 아직 안 끝났나"는 mlb_condition_ids의 game_start_time 체크와
    무관하게 애초에 closed=false 필터로 걸러진다."""
    raw = _get("/events", {
        "limit": limit, "active": "true", "closed": "false",
        "tag_slug": "mlb", "order": "startDate", "ascending": "false",
    })
    if not isinstance(raw, list):
        return []
    out = []
    for event in raw:
        for m in event.get("markets") or []:
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
