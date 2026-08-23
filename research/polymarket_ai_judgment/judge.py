"""Polymarket 마켓 질문 — Tavily 검색 grounding + Groq 판단, 캐시+예산 관리.

entity_tags.py와 동일 골격(캐시+호출예산+스테일 폴백) 재사용. 캐시 미스마다
Tavily 검색 1회 + Groq 판단 1회가 함께 발생한다는 점만 다르다. 판단 실패
(검색/LLM 호출 실패, JSON 파싱 실패, yes_prob 범위 밖)는 캐시에 저장하지
않는다 — 오판단이 곧장 paper 자본 배분으로 이어지므로 실패는 진입 스킵이
안전한 기본값이고, 캐시에 안 남아야 다음 틱에 자연 재시도된다(설계 spec §4.2, §7).

틱당 예산(max_new_calls_per_tick)과 일일 예산(max_new_calls_per_day) 이중
캡 — Tavily 무료티어(월 1,000크레딧) 보호가 목적(설계 spec §5)."""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from tavily import TavilyClient

load_dotenv()

_MODEL = "llama-3.3-70b-versatile"
_TAVILY_MAX_RESULTS = 5
_CACHE_PATH = Path("research/data/polymarket_ai_judgment/judge_cache.json")
_DAILY_STATE_PATH = Path("research/data/polymarket_ai_judgment/daily_call_state.json")


def question_hash(question: str) -> str:
    return hashlib.sha256(question.encode("utf-8")).hexdigest()


def search_and_judge(question: str, tavily_client=None, groq_client=None) -> dict | None:
    """Tavily 검색 후 Groq 판단. 실패 시 None(호출자는 진입 스킵으로 처리).
    성공 시 반환: {"yes_prob": float, "reasoning": str}."""
    tavily_client = tavily_client or TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    groq_client = groq_client or OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=os.environ["GROQ_API_KEY"],
    )
    try:
        search = tavily_client.search(query=question, max_results=_TAVILY_MAX_RESULTS)
    except Exception:  # noqa: BLE001
        return None

    snippets = "\n".join(
        f"- {r.get('title', '')}: {str(r.get('content', ''))[:300]}"
        for r in search.get("results", [])[:_TAVILY_MAX_RESULTS]
    )
    prompt = (
        "다음은 예측시장 질문과 웹검색 결과다. 검색결과를 근거로 이 질문이 YES로 "
        "정산될 확률을 0.0~1.0 사이 숫자로 추정해. 반드시 JSON 객체만 출력, "
        '형식: {"yes_prob": 0.0~1.0, "reasoning": "한줄 근거"}. 설명 없이 JSON만.\n\n'
        f"질문: {question}\n\n검색결과:\n{snippets}"
    )
    try:
        message = groq_client.chat.completions.create(
            model=_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.choices[0].message.content.strip()
    except Exception:  # noqa: BLE001
        return None

    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        result = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(result, dict) or "yes_prob" not in result:
        return None
    try:
        yes_prob = float(result["yes_prob"])
    except (TypeError, ValueError):
        return None
    if not (0.0 <= yes_prob <= 1.0):
        return None
    return {"yes_prob": yes_prob, "reasoning": str(result.get("reasoning", ""))[:300]}


def load_cache() -> dict:
    if not _CACHE_PATH.exists():
        return {}
    return json.loads(_CACHE_PATH.read_text())


def save_cache(cache: dict) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2))


def load_daily_state() -> dict:
    today = _dt.date.today().isoformat()
    if not _DAILY_STATE_PATH.exists():
        return {"date": today, "calls_used": 0}
    state = json.loads(_DAILY_STATE_PATH.read_text())
    if state.get("date") != today:
        return {"date": today, "calls_used": 0}
    return state


def save_daily_state(state: dict) -> None:
    _DAILY_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _DAILY_STATE_PATH.write_text(json.dumps(state))


def judge_markets(
    markets: list[dict],
    cache: dict,
    daily_state: dict,
    max_new_calls_per_tick: int,
    max_new_calls_per_day: int,
    judge_fn=search_and_judge,
) -> tuple[list[dict], dict, dict, int]:
    """markets 각각에 "judgment" 필드 추가(캐시 히트/신규판단 성공 시 dict, 실패 시 None).
    틱 예산 = min(max_new_calls_per_tick, max_new_calls_per_day - 오늘 이미 쓴 콜수).
    반환: (judgment 필드 추가된 markets, 갱신된 cache, 갱신된 daily_state, 이번 호출 실사용 콜 수)."""
    updated_cache = dict(cache)
    updated_state = dict(daily_state)
    already_used_today = updated_state.get("calls_used", 0)
    tick_budget = max(min(max_new_calls_per_tick, max_new_calls_per_day - already_used_today), 0)

    judged = []
    calls_used = 0
    for m in markets:
        cid = m["condition_id"]
        qh = question_hash(m["question"])
        entry = updated_cache.get(cid)
        if entry is not None and entry.get("question_hash") == qh:
            judgment = entry["judgment"]
        elif calls_used >= tick_budget:
            judgment = None
        else:
            judgment = judge_fn(m["question"])
            if judgment is not None:
                updated_cache[cid] = {"question_hash": qh, "judgment": judgment}
            calls_used += 1
        judged.append({**m, "judgment": judgment})

    updated_state["calls_used"] = already_used_today + calls_used
    return judged, updated_cache, updated_state, calls_used
