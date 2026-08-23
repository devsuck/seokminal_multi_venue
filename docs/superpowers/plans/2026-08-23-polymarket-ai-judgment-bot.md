# Polymarket AI 판단 봇 (side="ai") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tavily 검색 grounding + Groq LLM 판단으로 Polymarket 마켓 YES 확률을 추정하고, 시장가와의 괴리(edge)가 임계치 넘을 때만 진입하는 신규 셋째 sibling 페이퍼 봇을 추가한다.

**Architecture:** 백엔드(`seokminal-multi-venue`)에 캐시+예산 관리 모듈(`research/polymarket_ai_judgment/judge.py`)과 sibling 봇(`api_server/polymarket_ai_bot.py`)을 신규 추가, `polymarket_bot.py`/`entity_tags.py`의 기존 검증된 패턴을 그대로 재사용한다. 프론트엔드(`seokminal-dashboard`)에 `lib/api.ts` 함수 + `/polymarket` 페이지 카드를 추가한다. 두 봇 파일 다 독립 예산/포지션 — 자본 공유 없음.

**Tech Stack:** Python(FastAPI, `openai` SDK Groq 호환 엔드포인트, 신규 `tavily-python`), Next.js/TypeScript(기존 `lib/api.ts` 컨벤션).

**Spec:** `docs/superpowers/specs/2026-08-23-polymarket-ai-judgment-bot-design.md`

## Global Constraints

- Groq 모델: `llama-3.3-70b-versatile`, `base_url="https://api.groq.com/openai/v1"`, `api_key=os.environ["GROQ_API_KEY"]`.
- Tavily: `TavilyClient(api_key=os.environ["TAVILY_API_KEY"])`, 검색당 `max_results=5`.
- `interval_sec=3600`, `max_new_calls_per_tick=5`, `max_new_calls_per_day=30`, `min_edge=0.05` — 잠정치, 조정 가능하되 초기값은 이 숫자로 고정.
- v1은 **paper 전용** — 실주문/지갑 서명 없음.
- 판단 실패(검색/LLM 호출 실패, JSON 파싱 실패, `yes_prob` 범위 밖)는 캐시에 저장하지 않고 진입 스킵 — 다음 틱에 자연 재시도.
- 프론트엔드: raw `fetch` 금지, 반드시 `lib/api.ts` 함수 통해서만 API 호출. 디자인 토큰은 `ap-` 계열만 사용.
- Python 실행: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3`. `asyncio_mode="auto"` — `@pytest.mark.asyncio` 절대 금지.
- 커밋: 각 레포 `main` 직접 커밋(브랜치/워크트리 안 씀).

---

## Task 1: `research/polymarket_ai_judgment/judge.py` — Tavily 검색 + Groq 판단 + 캐시/예산

**Repo:** `seokminal-multi-venue`

**Files:**
- Create: `research/polymarket_ai_judgment/__init__.py` (빈 파일)
- Create: `research/polymarket_ai_judgment/judge.py`
- Modify: `pyproject.toml` (dependencies 배열에 `tavily-python` 추가)
- Test: `tests/test_polymarket_ai_judgment_judge.py`

**Interfaces:**
- Consumes: 없음(신규 모듈, 외부 의존은 `openai.OpenAI`, `tavily.TavilyClient`, `python-dotenv` — 전부 기존 설치됨/신규 1개 추가).
- Produces:
  - `question_hash(question: str) -> str`
  - `search_and_judge(question: str, tavily_client=None, groq_client=None) -> dict | None` — 성공 시 `{"yes_prob": float, "reasoning": str}`, 실패 시 `None`.
  - `load_cache() -> dict`, `save_cache(cache: dict) -> None`
  - `load_daily_state() -> dict`, `save_daily_state(state: dict) -> None`
  - `judge_markets(markets, cache, daily_state, max_new_calls_per_tick, max_new_calls_per_day, judge_fn=search_and_judge) -> tuple[list[dict], dict, dict, int]` — Task 3(`polymarket_ai_bot.py`)이 그대로 호출.
  - `_CACHE_PATH`, `_DAILY_STATE_PATH` 모듈 레벨 `Path` 상수 — 테스트가 `patch.object`로 오버라이드.

- [ ] **Step 1: `tavily-python` 의존성 추가 + 설치**

`pyproject.toml`의 `dependencies` 배열에서 `"pdfplumber>=0.11",` 다음 줄에 추가:

```toml
    "pdfplumber>=0.11",
    "tavily-python>=0.5",
```

설치:

```bash
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pip install tavily-python
```

- [ ] **Step 2: 패키지 디렉토리 생성**

```bash
mkdir -p research/polymarket_ai_judgment
touch research/polymarket_ai_judgment/__init__.py
```

- [ ] **Step 3: 실패하는 테스트 작성**

`tests/test_polymarket_ai_judgment_judge.py` 전체 내용:

```python
"""Polymarket AI 판단 모듈(Tavily 검색 + Groq 판단 + 캐시/예산) 테스트."""
import json
from unittest.mock import MagicMock, patch

from research.polymarket_ai_judgment import judge


def _mock_groq(payload: dict | str):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = text
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
    return mock_client


def _mock_tavily(results: list[dict] | None = None):
    mock_client = MagicMock()
    mock_client.search.return_value = {"results": results if results is not None else [
        {"title": "T", "url": "https://x", "content": "some snippet"},
    ]}
    return mock_client


def test_question_hash_changes_with_text():
    h1 = judge.question_hash("Will X win?")
    h2 = judge.question_hash("Will Y win?")
    assert h1 != h2
    assert h1 == judge.question_hash("Will X win?")


def test_search_and_judge_parses_valid_json():
    result = judge.search_and_judge(
        "Will X win?",
        tavily_client=_mock_tavily(),
        groq_client=_mock_groq({"yes_prob": 0.72, "reasoning": "strong lead"}),
    )
    assert result == {"yes_prob": 0.72, "reasoning": "strong lead"}


def test_search_and_judge_handles_code_fence():
    result = judge.search_and_judge(
        "Will X win?",
        tavily_client=_mock_tavily(),
        groq_client=_mock_groq('```json\n{"yes_prob": 0.4, "reasoning": "close race"}\n```'),
    )
    assert result == {"yes_prob": 0.4, "reasoning": "close race"}


def test_search_and_judge_returns_none_on_malformed_json():
    result = judge.search_and_judge(
        "Will X win?", tavily_client=_mock_tavily(), groq_client=_mock_groq("not json"),
    )
    assert result is None


def test_search_and_judge_returns_none_when_yes_prob_out_of_range():
    result = judge.search_and_judge(
        "Will X win?",
        tavily_client=_mock_tavily(),
        groq_client=_mock_groq({"yes_prob": 1.5, "reasoning": "bad"}),
    )
    assert result is None


def test_search_and_judge_returns_none_on_tavily_failure():
    tavily_client = MagicMock()
    tavily_client.search.side_effect = RuntimeError("network down")
    result = judge.search_and_judge(
        "Will X win?", tavily_client=tavily_client, groq_client=_mock_groq({"yes_prob": 0.5, "reasoning": "x"}),
    )
    assert result is None


def test_search_and_judge_returns_none_on_groq_failure():
    groq_client = MagicMock()
    groq_client.chat.completions.create.side_effect = RuntimeError("api down")
    result = judge.search_and_judge(
        "Will X win?", tavily_client=_mock_tavily(), groq_client=groq_client,
    )
    assert result is None


def test_load_cache_missing_file_returns_empty_dict(tmp_path):
    with patch.object(judge, "_CACHE_PATH", tmp_path / "judge_cache.json"):
        assert judge.load_cache() == {}


def test_save_cache_then_load_cache_roundtrip(tmp_path):
    with patch.object(judge, "_CACHE_PATH", tmp_path / "sub" / "judge_cache.json"):
        judge.save_cache({"c1": {"question_hash": "h", "judgment": {"yes_prob": 0.5, "reasoning": "r"}}})
        assert judge.load_cache() == {"c1": {"question_hash": "h", "judgment": {"yes_prob": 0.5, "reasoning": "r"}}}


def test_load_daily_state_missing_file_returns_zero(tmp_path):
    with patch.object(judge, "_DAILY_STATE_PATH", tmp_path / "daily_call_state.json"):
        state = judge.load_daily_state()
    assert state["calls_used"] == 0


def test_load_daily_state_resets_on_date_rollover(tmp_path):
    path = tmp_path / "daily_call_state.json"
    path.write_text(json.dumps({"date": "2020-01-01", "calls_used": 25}))
    with patch.object(judge, "_DAILY_STATE_PATH", path):
        state = judge.load_daily_state()
    assert state["calls_used"] == 0
    assert state["date"] != "2020-01-01"


def test_load_daily_state_keeps_count_same_day(tmp_path):
    import datetime as _dt
    today = _dt.date.today().isoformat()
    path = tmp_path / "daily_call_state.json"
    path.write_text(json.dumps({"date": today, "calls_used": 12}))
    with patch.object(judge, "_DAILY_STATE_PATH", path):
        state = judge.load_daily_state()
    assert state == {"date": today, "calls_used": 12}


def test_judge_markets_cache_hit_skips_call():
    market = {"condition_id": "c1", "question": "Will X win?"}
    qh = judge.question_hash("Will X win?")
    cache = {"c1": {"question_hash": qh, "judgment": {"yes_prob": 0.6, "reasoning": "r"}}}
    judge_fn = MagicMock()
    judged, updated_cache, updated_state, calls_used = judge.judge_markets(
        [market], cache, {"date": "x", "calls_used": 0}, 5, 30, judge_fn=judge_fn,
    )
    assert judged[0]["judgment"] == {"yes_prob": 0.6, "reasoning": "r"}
    assert calls_used == 0
    judge_fn.assert_not_called()


def test_judge_markets_cache_miss_calls_and_caches_success():
    market = {"condition_id": "c1", "question": "Will X win?"}
    judge_fn = MagicMock(return_value={"yes_prob": 0.6, "reasoning": "r"})
    judged, updated_cache, updated_state, calls_used = judge.judge_markets(
        [market], {}, {"date": "x", "calls_used": 0}, 5, 30, judge_fn=judge_fn,
    )
    assert judged[0]["judgment"] == {"yes_prob": 0.6, "reasoning": "r"}
    assert calls_used == 1
    assert updated_cache["c1"]["judgment"] == {"yes_prob": 0.6, "reasoning": "r"}
    assert updated_state["calls_used"] == 1


def test_judge_markets_failure_not_cached_for_retry():
    market = {"condition_id": "c1", "question": "Will X win?"}
    judge_fn = MagicMock(return_value=None)
    judged, updated_cache, updated_state, calls_used = judge.judge_markets(
        [market], {}, {"date": "x", "calls_used": 0}, 5, 30, judge_fn=judge_fn,
    )
    assert judged[0]["judgment"] is None
    assert calls_used == 1  # 시도는 예산 소모
    assert "c1" not in updated_cache  # 캐시엔 안 남음 — 다음 틱 재시도


def test_judge_markets_respects_per_tick_budget():
    markets = [
        {"condition_id": "c1", "question": "Q1"},
        {"condition_id": "c2", "question": "Q2"},
    ]
    judge_fn = MagicMock(return_value={"yes_prob": 0.5, "reasoning": "r"})
    judged, updated_cache, updated_state, calls_used = judge.judge_markets(
        markets, {}, {"date": "x", "calls_used": 0}, 1, 30, judge_fn=judge_fn,
    )
    assert calls_used == 1
    assert judged[0]["judgment"] is not None
    assert judged[1]["judgment"] is None
    assert "c2" not in updated_cache


def test_judge_markets_respects_daily_budget_even_under_tick_cap():
    markets = [
        {"condition_id": "c1", "question": "Q1"},
        {"condition_id": "c2", "question": "Q2"},
    ]
    judge_fn = MagicMock(return_value={"yes_prob": 0.5, "reasoning": "r"})
    # 틱캡 5지만 오늘 이미 29/30 소진 — 남은 예산 1개뿐
    judged, updated_cache, updated_state, calls_used = judge.judge_markets(
        markets, {}, {"date": "x", "calls_used": 29}, 5, 30, judge_fn=judge_fn,
    )
    assert calls_used == 1
    assert updated_state["calls_used"] == 30


def test_judge_markets_daily_budget_exhausted_skips_all_new():
    markets = [{"condition_id": "c1", "question": "Q1"}]
    judge_fn = MagicMock(return_value={"yes_prob": 0.5, "reasoning": "r"})
    judged, updated_cache, updated_state, calls_used = judge.judge_markets(
        markets, {}, {"date": "x", "calls_used": 30}, 5, 30, judge_fn=judge_fn,
    )
    assert calls_used == 0
    assert judged[0]["judgment"] is None
    judge_fn.assert_not_called()
```

- [ ] **Step 4: 테스트 실행 — import 에러로 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_ai_judgment_judge.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'research.polymarket_ai_judgment'`

- [ ] **Step 5: `research/polymarket_ai_judgment/judge.py` 구현**

```python
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
```

- [ ] **Step 6: 테스트 실행 — 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_ai_judgment_judge.py -v`
Expected: PASS(전체)

- [ ] **Step 7: 커밋**

```bash
git add pyproject.toml research/polymarket_ai_judgment/__init__.py research/polymarket_ai_judgment/judge.py tests/test_polymarket_ai_judgment_judge.py
git commit -m "feat: Polymarket AI 판단 모듈 — Tavily 검색 + Groq 판단, 캐시/예산 이중캡

entity_tags.py와 동일 캐시+예산 골격 재사용. 틱당(5)/일일(30) 이중 호출캡으로
Tavily 무료티어(월 1,000크레딧) 보호. 판단 실패는 캐시에 안 남겨 자연 재시도."
```

---

## Task 2: `api_server/polymarket_ai_bot.py` — sibling 봇 (router/config/tick/start_loop)

**Repo:** `seokminal-multi-venue`

**Files:**
- Create: `api_server/polymarket_ai_bot.py`
- Test: `tests/test_polymarket_ai_bot.py`

**Interfaces:**
- Consumes: `research.polymarket_ai_judgment.judge`의 `load_cache`, `save_cache`, `load_daily_state`, `save_daily_state`, `judge_markets` (Task 1에서 정의). `polymarket.client`의 `get_market(condition_id) -> dict | None`, `get_markets(limit) -> list[dict]`(기존, `polymarket_bot.py`가 이미 씀).
- Produces: `router`(APIRouter, prefix `/polymarket-ai-bot`), `status() -> dict`, `start_loop() -> None`, `tick() -> dict` — Task 4(`main.py` 등록)이 `router`/`start_loop`/`status`를 import.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_polymarket_ai_bot.py` 전체 내용:

```python
"""Polymarket AI 판단 봇(side="ai") 테스트."""
from unittest.mock import MagicMock, patch

from api_server import polymarket_ai_bot as bot


def _cfg(**over):
    return {**bot._DEFAULT, "enabled": True, "positions": [], **over}


def _market(condition_id="c1", event_id="e1", yes=0.5, no=0.5, liquidity=10000.0,
            end_date="2099-01-01", active=True, closed=False, accepting=True,
            days_out=None, question=None):
    if days_out is not None:
        import datetime as _dt
        end_date = (_dt.date.today() + _dt.timedelta(days=days_out)).isoformat()
    return {
        "condition_id": condition_id, "question": question or f"q-{condition_id}", "event_id": event_id,
        "event_title": "", "end_date": end_date, "volume": 1000.0, "liquidity": liquidity,
        "yes_price": yes, "no_price": no, "active": active, "closed": closed,
        "accepting_orders": accepting,
    }


def _judgment(yes_prob):
    return {"yes_prob": yes_prob, "reasoning": "r"}


def test_scan_candidates_skips_low_liquidity():
    cfg = _cfg(min_liquidity=5000.0)
    with patch.object(bot, "get_markets", return_value=[_market(liquidity=100.0)]):
        candidates = bot._scan_candidates(cfg)
    assert candidates == []


def test_scan_candidates_skips_extreme_price():
    cfg = _cfg(min_price=0.10, max_price=0.90)
    with patch.object(bot, "get_markets", return_value=[_market(yes=0.98, no=0.02)]):
        candidates = bot._scan_candidates(cfg)
    assert candidates == []


def test_scan_candidates_skips_too_far_maturity():
    cfg = _cfg(max_days_to_resolution=30)
    with patch.object(bot, "get_markets", return_value=[_market(days_out=90)]):
        candidates = bot._scan_candidates(cfg)
    assert candidates == []


def test_scan_candidates_skips_already_held_event():
    cfg = _cfg()
    cfg["positions"] = [{"condition_id": "other", "event_id": "e1", "question": "x",
                          "side": "YES", "entry_price": 0.5, "usd": 10.0, "shares": 20.0,
                          "end_date": "2099-01-01", "entry_ts": "", "ai_yes_prob": 0.6, "edge": 0.1}]
    with patch.object(bot, "get_markets", return_value=[_market(condition_id="c2", event_id="e1")]):
        candidates = bot._scan_candidates(cfg)
    assert candidates == []


def test_scan_candidates_passes_valid_market():
    cfg = _cfg()
    with patch.object(bot, "get_markets", return_value=[_market(days_out=10)]):
        candidates = bot._scan_candidates(cfg)
    assert len(candidates) == 1
    assert candidates[0]["condition_id"] == "c1"


def test_judge_and_enter_enters_yes_when_ai_above_market():
    cfg = _cfg(per_market_usd=10.0, budget=100.0, min_edge=0.05)
    market = _market(yes=0.5, no=0.5, days_out=10)
    judged = [{**market, "judgment": _judgment(0.7)}]  # edge = +0.2
    with patch.object(bot, "_scan_candidates", return_value=[market]), \
         patch.object(bot._judge, "load_cache", return_value={}), \
         patch.object(bot._judge, "load_daily_state", return_value={"date": "x", "calls_used": 0}), \
         patch.object(bot._judge, "judge_markets", return_value=(judged, {}, {"date": "x", "calls_used": 1}, 1)), \
         patch.object(bot._judge, "save_cache"), patch.object(bot._judge, "save_daily_state"), \
         patch.object(bot, "_log_event"):
        entered = bot._judge_and_enter(cfg)
    assert entered == 1
    pos = cfg["positions"][0]
    assert pos["side"] == "YES"
    assert pos["entry_price"] == 0.5
    assert pos["ai_yes_prob"] == 0.7
    assert pos["edge"] == 0.2
    assert cfg["spent"] == 10.0


def test_judge_and_enter_enters_no_when_ai_below_market():
    cfg = _cfg(per_market_usd=10.0, budget=100.0, min_edge=0.05)
    market = _market(yes=0.6, no=0.4, days_out=10)
    judged = [{**market, "judgment": _judgment(0.3)}]  # edge = -0.3
    with patch.object(bot, "_scan_candidates", return_value=[market]), \
         patch.object(bot._judge, "load_cache", return_value={}), \
         patch.object(bot._judge, "load_daily_state", return_value={"date": "x", "calls_used": 0}), \
         patch.object(bot._judge, "judge_markets", return_value=(judged, {}, {"date": "x", "calls_used": 1}, 1)), \
         patch.object(bot._judge, "save_cache"), patch.object(bot._judge, "save_daily_state"), \
         patch.object(bot, "_log_event"):
        entered = bot._judge_and_enter(cfg)
    assert entered == 1
    pos = cfg["positions"][0]
    assert pos["side"] == "NO"
    assert pos["entry_price"] == 0.4
    assert pos["edge"] == -0.3


def test_judge_and_enter_skips_when_edge_below_threshold():
    cfg = _cfg(per_market_usd=10.0, budget=100.0, min_edge=0.05)
    market = _market(yes=0.5, no=0.5, days_out=10)
    judged = [{**market, "judgment": _judgment(0.52)}]  # edge = 0.02 < 0.05
    with patch.object(bot, "_scan_candidates", return_value=[market]), \
         patch.object(bot._judge, "load_cache", return_value={}), \
         patch.object(bot._judge, "load_daily_state", return_value={"date": "x", "calls_used": 0}), \
         patch.object(bot._judge, "judge_markets", return_value=(judged, {}, {"date": "x", "calls_used": 1}, 1)), \
         patch.object(bot._judge, "save_cache"), patch.object(bot._judge, "save_daily_state"):
        entered = bot._judge_and_enter(cfg)
    assert entered == 0
    assert cfg["positions"] == []


def test_judge_and_enter_skips_when_judgment_none():
    cfg = _cfg(per_market_usd=10.0, budget=100.0)
    market = _market(days_out=10)
    judged = [{**market, "judgment": None}]
    with patch.object(bot, "_scan_candidates", return_value=[market]), \
         patch.object(bot._judge, "load_cache", return_value={}), \
         patch.object(bot._judge, "load_daily_state", return_value={"date": "x", "calls_used": 0}), \
         patch.object(bot._judge, "judge_markets", return_value=(judged, {}, {"date": "x", "calls_used": 0}, 0)), \
         patch.object(bot._judge, "save_cache"), patch.object(bot._judge, "save_daily_state"):
        entered = bot._judge_and_enter(cfg)
    assert entered == 0


def test_judge_and_enter_respects_budget():
    cfg = _cfg(budget=15.0, per_market_usd=10.0, spent=10.0)
    market = _market(days_out=10)
    with patch.object(bot, "_scan_candidates", return_value=[market]):
        entered = bot._judge_and_enter(cfg)
    assert entered == 0  # remaining=5 < per_market_usd=10, _scan_candidates 호출 전에 리턴


def test_judge_and_enter_skips_duplicate_event_within_tick():
    cfg = _cfg(per_market_usd=10.0, budget=100.0, min_edge=0.05, max_positions=5)
    m1 = _market(condition_id="c1", event_id="e1", yes=0.5, no=0.5, days_out=10)
    m2 = _market(condition_id="c2", event_id="e1", yes=0.5, no=0.5, days_out=10)
    judged = [{**m1, "judgment": _judgment(0.8)}, {**m2, "judgment": _judgment(0.8)}]
    with patch.object(bot, "_scan_candidates", return_value=[m1, m2]), \
         patch.object(bot._judge, "load_cache", return_value={}), \
         patch.object(bot._judge, "load_daily_state", return_value={"date": "x", "calls_used": 0}), \
         patch.object(bot._judge, "judge_markets", return_value=(judged, {}, {"date": "x", "calls_used": 2}, 2)), \
         patch.object(bot._judge, "save_cache"), patch.object(bot._judge, "save_daily_state"), \
         patch.object(bot, "_log_event"):
        entered = bot._judge_and_enter(cfg)
    assert entered == 1  # 두번째는 같은 event_id라 스킵


def test_process_resolutions_pays_out_winner():
    cfg = _cfg()
    cfg["positions"] = [{"condition_id": "c1", "question": "q", "event_id": "e1",
                          "side": "YES", "entry_price": 0.4, "usd": 10.0, "shares": 25.0,
                          "end_date": "2020-01-01", "entry_ts": "", "ai_yes_prob": 0.7, "edge": 0.3}]
    cfg["spent"] = 10.0
    resolved_market = _market(condition_id="c1", yes=0.99, no=0.01, closed=True)
    with patch.object(bot, "get_market", return_value=resolved_market), \
         patch.object(bot, "_log_event"):
        resolved = bot._process_resolutions(cfg)
    assert resolved == 1
    assert cfg["positions"] == []
    assert cfg["spent"] == 0.0
    assert cfg["realized_pnl"] == round((1.0 - 0.4) * 25.0, 2)


def test_process_resolutions_keeps_open_positions():
    cfg = _cfg()
    cfg["positions"] = [{"condition_id": "c1", "question": "q", "event_id": "e1",
                          "side": "YES", "entry_price": 0.5, "usd": 10.0, "shares": 20.0,
                          "end_date": "2099-01-01", "entry_ts": "", "ai_yes_prob": 0.6, "edge": 0.1}]
    with patch.object(bot, "get_market", return_value=_market(condition_id="c1", closed=False)):
        resolved = bot._process_resolutions(cfg)
    assert resolved == 0
    assert len(cfg["positions"]) == 1


def test_tick_disabled_skips():
    cfg = bot._DEFAULT
    with patch.object(bot, "_load", return_value=dict(cfg)):
        result = bot.tick()
    assert result == {"skipped": "disabled"}
```

- [ ] **Step 2: 테스트 실행 — import 에러로 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_ai_bot.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api_server.polymarket_ai_bot'`

- [ ] **Step 3: `api_server/polymarket_ai_bot.py` 구현**

```python
"""Polymarket AI 판단 봇(side="ai") — Tavily 검색 grounding + Groq 판단 기반 진입, paper 전용.

polymarket_bot.py(가격구조 기반 favorite/underdog/random)와 완전히 독립된 셋째
sibling 봇. 같은 마켓 유니버스를 보되 판단 신호축이 다르다 — 후보 필터는
polymarket_bot.py의 _scan_and_enter와 동일 기준 재사용, 진입 여부/방향만
AI 판단값(research/polymarket_ai_judgment/judge.py)의 yes_prob vs 시장가
괴리(edge)로 결정한다. 예산·포지션 전부 독립 — 다른 두 봇과 자본 공유 없음.

설계: docs/superpowers/specs/2026-08-23-polymarket-ai-judgment-bot-design.md"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import os
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from polymarket.client import get_market, get_markets
from research.polymarket_ai_judgment import judge as _judge

router = APIRouter(prefix="/polymarket-ai-bot", tags=["polymarket-ai-bot"])

_DATA = Path(os.environ.get("POLYMARKET_AI_BOT_DIR", "data"))
_CFG = _DATA / "polymarket_ai_bot.json"
_LOG = _DATA / "polymarket_ai_bot_log.jsonl"

_DEFAULT = {
    "enabled": False, "interval_sec": 3600,
    "budget": 2000.0, "per_market_usd": 40.0, "max_positions": 50,
    "min_liquidity": 3000.0, "min_price": 0.10, "max_price": 0.90,
    "min_days_to_resolution": 3, "max_days_to_resolution": 21,
    "min_edge": 0.05, "max_new_calls_per_tick": 5, "max_new_calls_per_day": 30,
    "spent": 0.0, "realized_pnl": 0.0,
    "positions": [],  # [{condition_id, question, event_id, side, entry_price, usd, shares, end_date, entry_ts, ai_yes_prob, edge}]
    "last_run": None,
}


def _load() -> dict:
    try:
        return {**_DEFAULT, **json.loads(_CFG.read_text())}
    except Exception:
        return dict(_DEFAULT)


def _save(cfg: dict) -> None:
    _DATA.mkdir(parents=True, exist_ok=True)
    _CFG.write_text(json.dumps(cfg))


def _log_event(ev: dict) -> None:
    _DATA.mkdir(parents=True, exist_ok=True)
    ev["ts"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    with _LOG.open("a") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")


def _recent_log(n: int = 40) -> list[dict]:
    try:
        lines = _LOG.read_text().strip().splitlines()
        return [json.loads(x) for x in lines[-n:]][::-1]
    except Exception:
        return []


def _process_resolutions(cfg: dict) -> int:
    """만기 지난/청산된 포지션 정산. 반환: 정산 건수."""
    keep: list[dict] = []
    resolved = 0
    for pos in cfg.get("positions", []):
        m = get_market(pos["condition_id"])
        if m is None:
            keep.append(pos)
            continue
        if not m["closed"]:
            keep.append(pos)
            continue
        final_price = m["yes_price"] if pos["side"] == "YES" else m["no_price"]
        payout = round(final_price)
        pnl = round((payout - pos["entry_price"]) * pos["shares"], 2)
        cfg["spent"] = round(max(float(cfg.get("spent", 0.0)) - pos["usd"], 0.0), 2)
        cfg["realized_pnl"] = round(float(cfg.get("realized_pnl", 0.0)) + pnl, 2)
        _log_event({"kind": "resolve", "question": pos["question"], "side": pos["side"],
                    "entry_price": pos["entry_price"], "payout": payout, "pnl": pnl})
        resolved += 1
    cfg["positions"] = keep
    return resolved


def _scan_candidates(cfg: dict) -> list[dict]:
    """polymarket_bot.py의 _scan_and_enter와 동일 필터 기준(활성/유동성/가격대/
    잔여만기), 사이드 선택 없이 후보 목록만 반환 — 사이드는 AI 판단 후 결정."""
    held_conditions = {p["condition_id"] for p in cfg.get("positions", [])}
    held_events = {p["event_id"] for p in cfg.get("positions", [])}

    try:
        markets = get_markets(limit=500)
    except Exception as e:  # noqa: BLE001
        _log_event({"kind": "scan_fail", "msg": str(e)[:100]})
        return []

    today = _dt.date.today()
    candidates = []
    for m in markets:
        if not m["active"] or m["closed"] or not m["accepting_orders"]:
            continue
        if m["condition_id"] in held_conditions or m["event_id"] in held_events:
            continue
        if m["liquidity"] < cfg["min_liquidity"]:
            continue
        if not (cfg["min_price"] <= m["yes_price"] <= cfg["max_price"]):
            continue
        try:
            end = _dt.date.fromisoformat(m["end_date"])
        except ValueError:
            continue
        days_left = (end - today).days
        if days_left < cfg["min_days_to_resolution"] or days_left > cfg["max_days_to_resolution"]:
            continue
        candidates.append(m)
    return candidates


def _judge_and_enter(cfg: dict) -> int:
    remaining_slots = cfg["max_positions"] - len(cfg.get("positions", []))
    if remaining_slots <= 0:
        return 0
    remaining_budget = cfg["budget"] - cfg.get("spent", 0.0)
    if remaining_budget < cfg["per_market_usd"]:
        return 0

    candidates = _scan_candidates(cfg)
    if not candidates:
        return 0

    cache = _judge.load_cache()
    daily_state = _judge.load_daily_state()
    judged, cache, daily_state, _calls_used = _judge.judge_markets(
        candidates, cache, daily_state,
        max_new_calls_per_tick=cfg["max_new_calls_per_tick"],
        max_new_calls_per_day=cfg["max_new_calls_per_day"],
    )
    _judge.save_cache(cache)
    _judge.save_daily_state(daily_state)

    held_events = {p["event_id"] for p in cfg.get("positions", [])}
    entered = 0
    for m in judged:
        if entered >= remaining_slots or remaining_budget < cfg["per_market_usd"]:
            break
        if m["event_id"] in held_events:
            continue
        judgment = m.get("judgment")
        if judgment is None:
            continue
        edge = judgment["yes_prob"] - m["yes_price"]
        if abs(edge) < cfg["min_edge"]:
            continue
        side, price = ("YES", m["yes_price"]) if edge > 0 else ("NO", m["no_price"])
        if price <= 0:
            continue

        usd = min(cfg["per_market_usd"], remaining_budget)
        shares = round(usd / price, 4)
        pos = {
            "condition_id": m["condition_id"], "question": m["question"],
            "event_id": m["event_id"], "side": side, "entry_price": price,
            "usd": usd, "shares": shares, "end_date": m["end_date"],
            "entry_ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "ai_yes_prob": judgment["yes_prob"], "edge": round(edge, 4),
        }
        cfg.setdefault("positions", []).append(pos)
        cfg["spent"] = round(float(cfg.get("spent", 0.0)) + usd, 2)
        remaining_budget -= usd
        held_events.add(m["event_id"])
        _log_event({"kind": "entry", **pos, "reasoning": judgment.get("reasoning", "")})
        entered += 1
    return entered


def tick() -> dict:
    cfg = _load()
    if not cfg["enabled"]:
        return {"skipped": "disabled"}
    try:
        from api_server.risk_state import is_killed
        if is_killed():
            _log_event({"kind": "kill", "msg": "리스크 킬스위치 — 매매 중단"})
            return {"skipped": "kill_switch"}
    except Exception:
        pass

    resolved = _process_resolutions(cfg)
    _save(cfg)
    entered = _judge_and_enter(cfg)
    cfg["last_run"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    _save(cfg)
    return {"entered": entered, "resolved": resolved, "positions": len(cfg.get("positions", [])),
            "spent": cfg["spent"], "realized_pnl": cfg["realized_pnl"]}


async def _loop() -> None:
    while True:
        try:
            cfg = _load()
            interval = int(cfg.get("interval_sec", 3600))
            if cfg.get("enabled"):
                await asyncio.to_thread(tick)
        except Exception:  # noqa: BLE001
            interval = 3600
        await asyncio.sleep(max(interval, 300))


def start_loop() -> None:
    try:
        asyncio.get_event_loop().create_task(_loop())
    except RuntimeError:
        pass


# ── API ──────────────────────────────────────────────────────────────────────
class BotConfig(BaseModel):
    enabled: bool | None = None
    interval_sec: int | None = None
    budget: float | None = None
    per_market_usd: float | None = None
    max_positions: int | None = None
    min_liquidity: float | None = None
    min_price: float | None = None
    max_price: float | None = None
    min_days_to_resolution: int | None = None
    max_days_to_resolution: int | None = None
    min_edge: float | None = None
    max_new_calls_per_tick: int | None = None
    max_new_calls_per_day: int | None = None
    reset_spent: bool | None = None


@router.get("/status")
def status() -> dict:
    cfg = _load()
    return {
        "enabled": cfg["enabled"], "interval_sec": cfg["interval_sec"],
        "budget": cfg["budget"], "per_market_usd": cfg["per_market_usd"],
        "max_positions": cfg["max_positions"], "min_liquidity": cfg["min_liquidity"],
        "min_price": cfg["min_price"], "max_price": cfg["max_price"],
        "min_days_to_resolution": cfg["min_days_to_resolution"],
        "max_days_to_resolution": cfg["max_days_to_resolution"],
        "min_edge": cfg["min_edge"], "max_new_calls_per_tick": cfg["max_new_calls_per_tick"],
        "max_new_calls_per_day": cfg["max_new_calls_per_day"],
        "spent": cfg.get("spent", 0.0), "realized_pnl": cfg.get("realized_pnl", 0.0),
        "remaining": max(cfg["budget"] - cfg.get("spent", 0.0), 0.0),
        "positions": cfg.get("positions", []), "last_run": cfg.get("last_run"),
        "log": _recent_log(40),
        "note": "Tavily 검색 grounding + Groq 판단(yes_prob) vs 시장가 괴리(edge)가 "
                "min_edge 넘을 때만 진입 — 가격구조 기반 다각화 배스킷/sharp_wallet 봇과 "
                "완전 독립 예산·포지션. v1 paper 전용, N=20~30건 정산 전까지 결론 안 냄.",
    }


@router.post("/config")
def set_config(body: BotConfig) -> dict:
    cfg = _load()
    if body.enabled is not None:
        cfg["enabled"] = body.enabled
    if body.interval_sec is not None:
        cfg["interval_sec"] = max(int(body.interval_sec), 300)
    if body.budget is not None:
        cfg["budget"] = max(float(body.budget), 0.0)
    if body.per_market_usd is not None:
        cfg["per_market_usd"] = max(float(body.per_market_usd), 1.0)
    if body.max_positions is not None:
        cfg["max_positions"] = max(int(body.max_positions), 1)
    if body.min_liquidity is not None:
        cfg["min_liquidity"] = max(float(body.min_liquidity), 0.0)
    if body.min_price is not None:
        cfg["min_price"] = min(max(float(body.min_price), 0.01), 0.49)
    if body.max_price is not None:
        cfg["max_price"] = min(max(float(body.max_price), 0.51), 0.99)
    if body.min_days_to_resolution is not None:
        cfg["min_days_to_resolution"] = max(int(body.min_days_to_resolution), 0)
    if body.max_days_to_resolution is not None:
        cfg["max_days_to_resolution"] = max(int(body.max_days_to_resolution), 1)
    if body.min_edge is not None:
        cfg["min_edge"] = min(max(float(body.min_edge), 0.0), 0.99)
    if body.max_new_calls_per_tick is not None:
        cfg["max_new_calls_per_tick"] = max(int(body.max_new_calls_per_tick), 0)
    if body.max_new_calls_per_day is not None:
        cfg["max_new_calls_per_day"] = max(int(body.max_new_calls_per_day), 0)
    if body.reset_spent:
        cfg["spent"] = 0.0
    _save(cfg)
    _log_event({"kind": "config", "enabled": cfg["enabled"], "budget": cfg["budget"]})
    return {"ok": True, **{k: cfg[k] for k in (
        "enabled", "interval_sec", "budget", "per_market_usd", "max_positions",
        "min_liquidity", "min_price", "max_price", "min_days_to_resolution",
        "max_days_to_resolution", "min_edge", "max_new_calls_per_tick", "max_new_calls_per_day")}}


@router.post("/run-now")
def run_now() -> dict:
    return tick()
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_ai_bot.py -v`
Expected: PASS(전체)

- [ ] **Step 5: 전체 백엔드 테스트 스위트로 회귀 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/ -q`
Expected: PASS(전체, pre-existing 실패 없음 — 프로젝트 컨벤션상 2026-07-30 이후 pre-existing 실패 없음)

- [ ] **Step 6: 커밋**

```bash
git add api_server/polymarket_ai_bot.py tests/test_polymarket_ai_bot.py
git commit -m "feat: Polymarket AI 판단 봇(side=ai) sibling 봇 추가

polymarket_bot.py와 동일 골격(config/tick/start_loop/status), 후보 필터도
동일 기준 재사용. 사이드 선택만 AI 판단(yes_prob) vs 시장가 edge로 결정 —
min_edge 미만이면 패스. 예산/포지션 완전 독립, paper 전용."
```

---

## Task 3: `api_server/main.py` — 셋째 sibling 봇 등록

**Repo:** `seokminal-multi-venue`

**Files:**
- Modify: `api_server/main.py:5384-5471`

**Interfaces:**
- Consumes: Task 2가 만든 `api_server.polymarket_ai_bot.router`, `start_loop`, `status`.
- Produces: `GET /dashboard/pnl/all` 응답의 `bots` 배열에 `{"id": "polymarket_ai_bot", ...}` 신규 항목(프론트 `PortfolioTab.tsx`가 `id.startsWith("polymarket")`으로 자동 집계 — 프론트 추가 변경 불요).

- [ ] **Step 1: sibling 봇 등록 블록 추가**

`api_server/main.py`에서 아래 기존 블록(현재 5384~5390행)을 찾는다:

```python
# ── Polymarket sharp_wallet 컨버전스 신호 paper 집행 봇 (서버측) ────────────────────
from api_server.polymarket_sharp_wallet_bot import (
    router as polymarket_sharp_wallet_bot_router,
    start_loop as _polymarket_sharp_wallet_bot_start,
    _recent_log as _sw_bot_recent_log,
)
app.include_router(polymarket_sharp_wallet_bot_router)
```

바로 뒤에 추가:

```python

# ── Polymarket AI 판단 봇(side="ai") — Tavily 검색 grounding + Groq 판단, paper (서버측) ──
from api_server.polymarket_ai_bot import router as polymarket_ai_bot_router, start_loop as _polymarket_ai_bot_start
app.include_router(polymarket_ai_bot_router)
```

- [ ] **Step 2: status import 추가**

기존 블록(현재 5396~5397행):

```python
from api_server.polymarket_bot import status as _polymarket_bot_status
from api_server.polymarket_sharp_wallet_bot import status as _sharp_wallet_bot_status
```

다음 줄 추가:

```python
from api_server.polymarket_ai_bot import status as _polymarket_ai_bot_status
```

- [ ] **Step 3: 대시보드 PnL 집계 리스트에 항목 추가**

기존(현재 5410~5412행):

```python
        {"id": "polymarket_bot", "name": "Polymarket 배스킷", "realized_pnl": _polymarket_bot_status().get("realized_pnl", 0.0)},
        {"id": "polymarket_sharp_wallet_bot", "name": "Polymarket sharp_wallet",
         "realized_pnl": _sharp_wallet_bot_status().get("realized_pnl", 0.0)},
```

다음에 추가:

```python
        {"id": "polymarket_ai_bot", "name": "Polymarket AI판단",
         "realized_pnl": _polymarket_ai_bot_status().get("realized_pnl", 0.0)},
```

- [ ] **Step 4: startup 이벤트에 `start_loop()` 호출 추가**

기존(현재 5470~5471행):

```python
    _polymarket_bot_start()
    _polymarket_sharp_wallet_bot_start()
```

다음에 추가:

```python
    _polymarket_ai_bot_start()
```

- [ ] **Step 5: 서버 기동 확인**

```bash
bash scripts/restart_api.sh
sleep 2
curl -s http://localhost:8000/polymarket-ai-bot/status | python3 -m json.tool
```

Expected: `enabled: false`, `min_edge: 0.05`, `max_new_calls_per_day: 30` 등 `_DEFAULT` 값 포함한 JSON 응답. 500 에러/트레이스백 없음.

- [ ] **Step 6: `dashboard/pnl/all` 응답에 신규 봇 반영 확인**

```bash
curl -s http://localhost:8000/dashboard/pnl/all | python3 -c "import json,sys; d=json.load(sys.stdin); print([b['id'] for b in d['bots']])"
```

Expected: 출력에 `'polymarket_ai_bot'` 포함.

- [ ] **Step 7: 커밋**

```bash
git add api_server/main.py
git commit -m "feat: Polymarket AI 판단 봇 서버 등록 — router/PnL집계/startup

기존 sibling 봇(polymarket_bot/polymarket_sharp_wallet_bot) 등록 패턴 그대로.
id가 polymarket으로 시작해 대시보드 HOME 폴리마켓 타일에 자동 집계됨."
```

---

## Task 4: `lib/api.ts` — AI 봇 API 함수 (프론트)

**Repo:** `seokminal-dashboard`

**Files:**
- Modify: `lib/api.ts` (기존 `runSharpWalletBotNow` 함수 바로 뒤, `PolymarketLeaderEntry` interface 앞에 삽입)

**Interfaces:**
- Consumes: 없음(기존 `API_URL`, `handleResponse`, `ApiError` 재사용 — 파일 상단에 이미 정의됨).
- Produces: `getPolymarketAiBotStatus`, `setPolymarketAiBotConfig`, `runPolymarketAiBotNow`, `PolymarketAiBotStatus`, `PolymarketAiBotConfig`, `PolymarketAiPosition` — Task 5(`/polymarket` 페이지)가 그대로 import.

- [ ] **Step 1: `lib/api.ts`에 신규 타입/함수 추가**

`export async function runSharpWalletBotNow(): Promise<Record<string, unknown>> { ... }` 함수(현재 3519~3522행) 바로 뒤, `export interface PolymarketLeaderEntry` 앞에 삽입:

```typescript
// ── Polymarket AI 판단 봇(side="ai") — Tavily 검색 grounding + Groq 판단, paper ────────
export interface PolymarketAiPosition {
  condition_id: string; question: string; event_id: string; side: string;
  entry_price: number; usd: number; shares: number; end_date: string; entry_ts: string;
  ai_yes_prob: number; edge: number;
}
export interface PolymarketAiBotStatus {
  enabled: boolean; interval_sec: number; budget: number; per_market_usd: number;
  max_positions: number; min_liquidity: number; min_price: number; max_price: number;
  min_days_to_resolution: number; max_days_to_resolution: number;
  min_edge: number; max_new_calls_per_tick: number; max_new_calls_per_day: number;
  spent: number; realized_pnl: number; remaining: number;
  positions: PolymarketAiPosition[]; last_run: string | null;
  log: PolymarketBotLog[]; note: string;
}
export interface PolymarketAiBotConfig {
  enabled?: boolean; interval_sec?: number; budget?: number; per_market_usd?: number;
  max_positions?: number; min_liquidity?: number; min_price?: number; max_price?: number;
  min_days_to_resolution?: number; max_days_to_resolution?: number;
  min_edge?: number; max_new_calls_per_tick?: number; max_new_calls_per_day?: number;
  reset_spent?: boolean;
}

export async function getPolymarketAiBotStatus(signal?: AbortSignal): Promise<PolymarketAiBotStatus> {
  const r = await fetch(`${API_URL}/polymarket-ai-bot/status`, { signal });
  return handleResponse<PolymarketAiBotStatus>(r);
}
export async function setPolymarketAiBotConfig(cfg: PolymarketAiBotConfig): Promise<{ ok: boolean }> {
  const r = await fetch(`${API_URL}/polymarket-ai-bot/config`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cfg),
  });
  return handleResponse(r);
}
export async function runPolymarketAiBotNow(): Promise<Record<string, unknown>> {
  const r = await fetch(`${API_URL}/polymarket-ai-bot/run-now`, { method: "POST" });
  return handleResponse(r);
}
```

- [ ] **Step 2: 타입체크**

Run: `npx tsc --noEmit`
Expected: 에러 없음(신규 타입/함수만 추가, 기존 코드 미참조 상태라 unused 경고도 없음 — `export`라 tsc가 unused로 안 잡음)

- [ ] **Step 3: 커밋**

```bash
git add lib/api.ts
git commit -m "feat: Polymarket AI 판단 봇 API 함수 추가

/polymarket-ai-bot/{status,config,run-now} 래핑 — 기존 폴리마켓 봇들과 동일 패턴."
```

---

## Task 5: `/polymarket` 페이지 — AI 판단 봇 카드

**Repo:** `seokminal-dashboard`

**Files:**
- Modify: `app/polymarket/page.tsx`

**Interfaces:**
- Consumes: Task 4가 만든 `getPolymarketAiBotStatus`, `setPolymarketAiBotConfig`, `runPolymarketAiBotNow`, `PolymarketAiBotStatus` (from `@/lib/api`).
- Produces: 없음(터미널 UI 변경).

- [ ] **Step 1: import 블록에 AI 봇 함수/타입 추가**

파일 상단 import(현재 4~11행)의 기존:

```typescript
import {
  ApiError, getPolymarketBotStatus, setPolymarketBotConfig, runPolymarketBotNow,
  getPolymarketLeaderboard, getFleet, getEdges, getSharpWalletBotStatus,
  setSharpWalletBotConfig, runSharpWalletBotNow,
  type PolymarketBotStatus, type PolymarketLeaderboard,
  type FleetResponse, type FleetCollector, type EdgesResponse, type EdgeMetaRow,
  type SharpWalletBotStatus,
} from "@/lib/api";
```

다음으로 교체:

```typescript
import {
  ApiError, getPolymarketBotStatus, setPolymarketBotConfig, runPolymarketBotNow,
  getPolymarketLeaderboard, getFleet, getEdges, getSharpWalletBotStatus,
  setSharpWalletBotConfig, runSharpWalletBotNow,
  getPolymarketAiBotStatus, setPolymarketAiBotConfig, runPolymarketAiBotNow,
  type PolymarketBotStatus, type PolymarketLeaderboard,
  type FleetResponse, type FleetCollector, type EdgesResponse, type EdgeMetaRow,
  type SharpWalletBotStatus, type PolymarketAiBotStatus,
} from "@/lib/api";
```

- [ ] **Step 2: state 추가**

기존(현재 56~57행):

```typescript
  const [swBot, setSwBot] = useState<SharpWalletBotStatus | null>(null);
  const [swBusy, setSwBusy] = useState(false);
```

다음 줄 추가:

```typescript
  const [aiBot, setAiBot] = useState<PolymarketAiBotStatus | null>(null);
  const [aiBusy, setAiBusy] = useState(false);
```

- [ ] **Step 3: 폴링 useEffect에 AI 봇 로드 추가**

기존(현재 87~98행):

```typescript
  // 폴리마켓 관련 수집기 헬스 + 가설 검증 현황 — 전용 페이지 없는 것들 여기서 총괄
  useEffect(() => {
    let mounted = true;
    const ctrl = new AbortController();
    const load = () => {
      getFleet(ctrl.signal).then(d => { if (mounted) setFleet(d); }).catch(() => {});
      getEdges(ctrl.signal).then(d => { if (mounted) setEdges(d); }).catch(() => {});
      getSharpWalletBotStatus(ctrl.signal).then(d => { if (mounted) setSwBot(d); }).catch(() => {});
    };
    load();
    const iv = setInterval(load, 30_000);
    return () => { mounted = false; clearInterval(iv); ctrl.abort(); };
  }, []);
```

`getSharpWalletBotStatus` 줄 다음에 추가:

```typescript
      getPolymarketAiBotStatus(ctrl.signal).then(d => { if (mounted) setAiBot(d); }).catch(() => {});
```

- [ ] **Step 4: 토글/실행 함수 추가**

기존(현재 136~141행) `runSwNow` 함수 바로 뒤에 추가:

```typescript
  async function toggleAiBot() {
    try {
      await setPolymarketAiBotConfig({ enabled: !(aiBot?.enabled ?? false) });
      flash(aiBot?.enabled ? "AI판단 봇 OFF" : "AI판단 봇 ON");
      getPolymarketAiBotStatus().then(setAiBot).catch(() => {});
    } catch (e) { flash(`실패: ${e instanceof ApiError ? e.message : String(e)}`); }
  }

  async function runAiBotNow() {
    setAiBusy(true);
    try { await runPolymarketAiBotNow(); flash("AI판단 봇 실행 완료"); getPolymarketAiBotStatus().then(setAiBot).catch(() => {}); }
    catch (e) { flash(`실패: ${e instanceof ApiError ? e.message : String(e)}`); }
    finally { setAiBusy(false); }
  }
```

- [ ] **Step 5: 실현손익 누적 곡선 계산 추가**

기존(현재 161~175행) `swPnlSeries` 계산 블록 바로 뒤에 추가:

```typescript
  // AI 판단 봇 — 실현손익 누적 곡선(resolve 로그 기반)
  const aiPnlSeries: TSSeries[] = (() => {
    if (!aiBot) return [];
    const resolves = aiBot.log
      .filter(l => l.kind === "resolve" && typeof l.pnl === "number")
      .map(l => ({ t: Math.floor(new Date(l.ts).getTime() / 1000), pnl: l.pnl as number }))
      .filter(r => Number.isFinite(r.t))
      .sort((a, b) => a.t - b.t);
    if (resolves.length === 0) return [];
    const totalVisible = resolves.reduce((s, r) => s + r.pnl, 0);
    let running = aiBot.realized_pnl - totalVisible;
    const points = resolves.map(r => { running += r.pnl; return { time: r.t, value: Math.round(running * 100) / 100 }; });
    const last = points[points.length - 1].value;
    return [{ label: "누적 실현손익", color: last >= 0 ? TOKEN.pos : TOKEN.neg, points }];
  })();
```

- [ ] **Step 6: 총괄 현황 카드에 AI 봇 링크 행 추가**

기존(현재 201~214행) `swBot` 앵커 블록:

```tsx
          {swBot && (
            <a href="#sharp-wallet-bot" className="flex items-center justify-between gap-2 border border-ap-line rounded-lg px-2.5 py-2 text-xs hover:bg-ap-bg">
              <div className="flex items-center gap-2 min-w-0">
                <span className={`text-[10px] px-1.5 py-0.5 rounded border shrink-0 font-data ${swBot.enabled ? "border-ap-up/40 text-ap-up bg-ap-up/10" : "border-ap-line text-ap-ink-3 bg-ap-bg"}`}>
                  {swBot.enabled ? "ON" : "OFF"}
                </span>
                <span className="text-ap-ink-2 truncate">샤프월렛 컨버전스 paper 집행봇</span>
                <span className="text-ap-ink-3 hidden sm:inline shrink-0">→ 상세</span>
              </div>
              <span className="text-ap-ink-3 tabular-nums shrink-0 font-data">
                {swBot.last_run ? `${swBot.realized_pnl >= 0 ? "+" : ""}$${swBot.realized_pnl.toLocaleString()}` : "이력 없음"}
              </span>
            </a>
          )}
```

바로 뒤에 추가:

```tsx
          {aiBot && (
            <a href="#ai-judgment-bot" className="flex items-center justify-between gap-2 border border-ap-line rounded-lg px-2.5 py-2 text-xs hover:bg-ap-bg">
              <div className="flex items-center gap-2 min-w-0">
                <span className={`text-[10px] px-1.5 py-0.5 rounded border shrink-0 font-data ${aiBot.enabled ? "border-ap-up/40 text-ap-up bg-ap-up/10" : "border-ap-line text-ap-ink-3 bg-ap-bg"}`}>
                  {aiBot.enabled ? "ON" : "OFF"}
                </span>
                <span className="text-ap-ink-2 truncate">AI 판단 봇(Tavily+Groq)</span>
                <span className="text-ap-ink-3 hidden sm:inline shrink-0">→ 상세</span>
              </div>
              <span className="text-ap-ink-3 tabular-nums shrink-0 font-data">
                {aiBot.last_run ? `${aiBot.realized_pnl >= 0 ? "+" : ""}$${aiBot.realized_pnl.toLocaleString()}` : "이력 없음"}
              </span>
            </a>
          )}
```

- [ ] **Step 7: AI 판단 봇 카드 섹션 추가**

기존(현재 386~482행) 샤프월렛 섹션의 닫는 `)}`(482행, `{swBot && ( ... )}`의 끝) 바로 뒤, 고래 리더보드 `Card`(484행) 앞에 삽입:

```tsx
      {/* AI 판단 봇 — Tavily 검색 grounding + Groq 판단, 가격구조 봇들과 독립 예산/포지션 */}
      {aiBot && (
        <div id="ai-judgment-bot" className="space-y-4 scroll-mt-4">
          <Card>
            <CardHeader right={<span>{fmtTime(aiBot.last_run)} · {Math.round(aiBot.interval_sec / 60)}분 주기</span>}>
              AI 판단 봇 <span className="text-ap-ink-3 text-[10px] font-normal">(Tavily 검색 + Groq 판단, side=&quot;ai&quot;)</span>
            </CardHeader>
            <div className="p-3 space-y-3">
              <div className="flex items-center gap-2 flex-wrap">
                <button onClick={toggleAiBot}
                  className={`text-sm font-medium px-4 py-1.5 rounded-lg border ${aiBot.enabled ? "border-ap-up text-ap-up bg-ap-up/10" : "border-ap-line text-ap-ink-3 hover:text-ap-ink-2"}`}>
                  {aiBot.enabled ? "● 서버 자동봇 ON" : "서버 자동봇 OFF"}
                </button>
                <button onClick={runAiBotNow} disabled={aiBusy}
                  className="text-xs px-3 py-1.5 rounded-lg border border-ap-line text-ap-ink-3 hover:text-ap-brand disabled:opacity-40">
                  {aiBusy ? "실행중…" : "지금 실행"}
                </button>
              </div>
              <div className="flex items-center gap-2 flex-wrap text-[11px] border-t border-ap-line pt-3">
                <span className="text-ap-ink-3">지출 <span className="text-ap-ink-1 font-data">${Math.round(aiBot.spent).toLocaleString()}</span>/${Math.round(aiBot.budget).toLocaleString()}</span>
                <span className={`font-data px-1.5 py-0.5 rounded font-bold ${aiBot.remaining < 1 ? "bg-ap-down/15 text-ap-down" : "bg-ap-up/15 text-ap-up"}`}>잔여 ${Math.round(aiBot.remaining).toLocaleString()}</span>
                <span className={`font-data px-1.5 py-0.5 rounded font-bold ${aiBot.realized_pnl >= 0 ? "bg-ap-up/15 text-ap-up" : "bg-ap-down/15 text-ap-down"}`}>실현손익 {aiBot.realized_pnl >= 0 ? "+" : ""}${aiBot.realized_pnl.toLocaleString()}</span>
                <span className="text-ap-ink-3 ml-auto">엣지≥{(aiBot.min_edge * 100).toFixed(0)}% · 일일캡 {aiBot.max_new_calls_per_day}콜</span>
              </div>
            </div>
          </Card>

          {aiPnlSeries.length > 0 && (
            <Card>
              <CardHeader right={<span>최근 정산 {aiPnlSeries[0].points.length}건</span>}>
                실현손익 추이
              </CardHeader>
              <div className="p-2">
                <ChartFrame textClass={AP_TEXT} legendTextClass={AP_LEGEND} caption="AI 판단 진입 만기 정산 · 페이퍼 · 표본 작을수록 노이즈 큼">
                  <TimeSeries series={aiPnlSeries} height={200} yFormat={(v) => `$${v.toFixed(0)}`} />
                </ChartFrame>
              </div>
            </Card>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-4">
            <Card>
              <CardHeader right={<span>{aiBot.positions.length}건</span>}>보유 포지션</CardHeader>
              {aiBot.positions.length === 0 ? (
                <div className="p-3"><EmptyState message="보유 포지션 없음" hint="AI 판단 확신도(엣지) 임계치 넘는 시장에만 진입" textClass="text-ap-ink-3" /></div>
              ) : (
                <div className="divide-y divide-ap-line/60 max-h-[420px] overflow-y-auto">
                  {aiBot.positions.map((p, i) => (
                    <div key={`${p.condition_id}:${i}`} className="px-3 py-2">
                      <div className="flex items-start justify-between gap-2">
                        <span className="text-ap-ink-1 text-xs truncate" title={p.question}>{p.question}</span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded border border-ap-line text-ap-ink-2 font-data shrink-0">{p.side}</span>
                      </div>
                      <div className="flex items-center gap-1.5 text-[11px] text-ap-ink-3 font-data mt-1">
                        <span>진입 {p.entry_price.toFixed(2)}</span>
                        <span>·</span>
                        <span>AI {p.ai_yes_prob.toFixed(2)}</span>
                        <span>·</span>
                        <span className={p.edge >= 0 ? "text-ap-up" : "text-ap-down"}>엣지 {p.edge >= 0 ? "+" : ""}{(p.edge * 100).toFixed(1)}%</span>
                        <span>·</span>
                        <span className="text-ap-ink-1 font-bold">${p.usd.toLocaleString()}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Card>

            <Card>
              <CardHeader>봇 실행 로그</CardHeader>
              {aiBot.log.length === 0 ? (
                <div className="p-3"><EmptyState message="로그 없음" hint="봇이 판단/진입/정산하면 기록됨" textClass="text-ap-ink-3" /></div>
              ) : (
                <div className="divide-y divide-ap-line/60 max-h-[420px] overflow-y-auto">
                  {aiBot.log.map((l, i) => (
                    <div key={i} className="px-3 py-2 text-xs flex items-start gap-2">
                      <span className="text-ap-ink-3 font-data text-[10px] shrink-0 w-16">{fmtTime(l.ts as string)}</span>
                      <span className="min-w-0 text-ap-ink-3">
                        {l.kind === "entry" ? <span className="text-ap-up">진입 {String(l.side)} @{Number(l.entry_price ?? 0).toFixed(2)} AI{Number(l.ai_yes_prob ?? 0).toFixed(2)} ${Number(l.usd ?? 0).toLocaleString()}</span>
                          : l.kind === "resolve" ? <span className={`px-1 rounded font-bold ${Number(l.pnl ?? 0) >= 0 ? "bg-ap-up/15 text-ap-up" : "bg-ap-down/15 text-ap-down"}`}>정산 {String(l.side)} 손익 ${Number(l.pnl ?? 0).toLocaleString()}</span>
                          : l.kind === "scan_fail" ? <span className="text-ap-down">스캔 실패 — {String(l.msg ?? "")}</span>
                          : l.kind === "kill" ? <span className="text-ap-down">킬스위치 — {String(l.msg ?? "")}</span>
                          : l.kind === "config" ? "설정 변경"
                          : String(l.kind)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>

          <p className="text-ap-ink-3 text-[10px] px-1">{aiBot.note}</p>
        </div>
      )}

```

- [ ] **Step 8: 타입체크**

Run: `npx tsc --noEmit`
Expected: 에러 없음

- [ ] **Step 9: 개발서버로 렌더 확인**

```bash
npm run dev &
sleep 5
curl -s http://localhost:3000/polymarket -o /dev/null -w "%{http_code}\n"
```

Expected: `200`. (백엔드가 켜져있어야 `/polymarket-ai-bot/status`가 응답하지만, 실패해도 `catch(() => {})`라 페이지 자체는 깨지지 않음 — `aiBot`이 `null`이면 카드 섹션은 렌더 안 됨.)

- [ ] **Step 10: 커밋**

```bash
git add app/polymarket/page.tsx
git commit -m "feat: /polymarket 페이지에 AI 판단 봇 카드 추가

기존 샤프월렛 봇 섹션과 동일 레이아웃(제어+지출/손익+포지션+로그).
포지션 행에 AI 판단확률·엣지 노출 — 진입 근거 바로 확인 가능."
```

---

## Task 6: 전체 회귀 검증 + `docs/progress.md` 갱신

**Repo:** 양쪽 다

**Files:**
- Modify: `seokminal-dashboard/docs/progress.md` (Phase 항목 추가, 파일 최상단에 prepend)

- [ ] **Step 1: 백엔드 전체 테스트**

```bash
cd /Users/seokhun/seokminal/seokminal-multi-venue
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/ -q
```

Expected: 전체 PASS, pre-existing 실패 0건.

- [ ] **Step 2: 프론트엔드 전체 검증**

```bash
cd /Users/seokhun/seokminal/seokminal-dashboard
npx tsc --noEmit
npm test
```

Expected: tsc 에러 0, 테스트 전체 PASS.

- [ ] **Step 3: `docs/progress.md`에 Phase 항목 prepend**

`seokminal-dashboard/docs/progress.md` 파일 최상단(기존 최신 Phase 항목 바로 위)에 아래 섹션 삽입 — 기존 Phase 번호+1로 이어서 작성(파일이 커서 전체 Read 불필요, 최상단 몇 줄만 확인 후 그 앞에 Edit로 삽입):

```markdown
## Phase <N> — Polymarket AI 판단 봇(side="ai") 구현

**배경:** 유저가 "AI CLI 넣어서 판단하게 하거나 네이버 검색 API 붙일 수 있냐"
질문 → 브레인스토밍으로 이어져 Tavily 검색 grounding + Groq LLM 판단 기반
신규 셋째 sibling 폴리마켓 봇으로 설계 확정(스펙: seokminal-multi-venue의
`docs/superpowers/specs/2026-08-23-polymarket-ai-judgment-bot-design.md`).
유저 명시 지시로 승인게이트 생략하고 플랜~구현~검증까지 자율 진행(유저 취침중).

**완료된 작업:**
- (multi-venue) `research/polymarket_ai_judgment/judge.py` — Tavily 검색 +
  Groq 판단 + 캐시/예산(틱당5·일일30 이중캡, entity_tags.py 패턴 재사용)
- (multi-venue) `api_server/polymarket_ai_bot.py` — 셋째 sibling 봇
  (`/polymarket-ai-bot` prefix), min_edge(0.05) 기준 진입 판정, 독립 예산/포지션
- (multi-venue) `api_server/main.py` — 신규 봇 router/status/startup 등록,
  대시보드 PnL 집계에 `polymarket_ai_bot` 추가
- (multi-venue) `pyproject.toml`에 `tavily-python` 의존성 추가, `.env`에
  `TAVILY_API_KEY` 추가(유저 제공 키, gitignore 적용— 커밋 안 됨)
- (dashboard) `lib/api.ts` — `getPolymarketAiBotStatus`/`setPolymarketAiBotConfig`/
  `runPolymarketAiBotNow` + 타입 추가
- (dashboard) `app/polymarket/page.tsx` — AI 판단 봇 카드 섹션 추가(제어+지출/손익
  +포지션(AI확률·엣지 노출)+로그), 총괄 현황 카드에 링크 행 추가

**변경된 파일:**
- multi-venue: `research/polymarket_ai_judgment/{__init__.py,judge.py}`,
  `tests/test_polymarket_ai_judgment_judge.py`, `api_server/polymarket_ai_bot.py`,
  `tests/test_polymarket_ai_bot.py`, `api_server/main.py`, `pyproject.toml`, `.env`
- dashboard: `lib/api.ts`, `app/polymarket/page.tsx`

**검증:** 백엔드 pytest 전체 PASS(pre-existing 실패 없음), 프론트 `tsc --noEmit`
클린 + `npm test` PASS. `/polymarket-ai-bot/status` curl 응답 확인(서버 재기동
후). 브라우저 렌더 확인(`curl /polymarket` 200) — 실제 진입/판단 사이클은 봇이
꺼진 상태(`enabled: false`)라 미검증, 유저가 켜야 실동작 시작.

**막힌 부분/결정사항:**
- v1 paper 전용, 실집행 없음 — 스펙 §7 그대로.
- 봇은 기본 OFF 상태로 배포됨 — 유저가 `/polymarket` 페이지에서 직접 켜야
  실제 스캔/판단/진입 시작(예산 소모형 API 호출이라 자동 ON 안 함).
- min_edge(0.05) 등 임계값은 잠정치, 스펙 §6 검증(N=20~30건) 데이터 쌓이면
  조정 대상.

**다음 할 일:**
- 유저 기상 후 `/polymarket-ai-bot` 봇 ON 여부 결정.
- N=20~30건 정산 누적되면 기존 favorite/underdog 대비 성과 비교(스펙 §6).
```

- [ ] **Step 4: 양쪽 레포 커밋**

```bash
cd /Users/seokhun/seokminal/seokminal-dashboard
git add docs/progress.md
git commit -m "docs: Polymarket AI 판단 봇 구현 완료 — progress.md Phase 갱신"
```

(multi-venue 레포는 Task 1~3에서 이미 개별 커밋 완료 — 이 태스크에서 추가 커밋 없음)
