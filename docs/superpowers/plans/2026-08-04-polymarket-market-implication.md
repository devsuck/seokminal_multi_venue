# Polymarket 크로스이벤트 함의관계 위반 탐지 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 서로 다른 이벤트에 걸친 두 Polymarket 마켓의 논리적 함의/상호배타 관계를 자동 판정하고, 그 관계가 가격에 강제하는 부등식을 위반비용(왕복비용 초과분) 기준으로 탐지·페이퍼 로깅한다.

**Architecture:** 일 1회 수집기가 활성마켓을 스캔해 엔티티 태깅(LLM, 캐시)→후보쌍 필터(만기근접, 순수함수)→함의판정(LLM)까지 마쳐 `pairs.jsonl`에 저장한다. 시간당 워치가 `pairs.jsonl`의 확정 쌍만 대상으로 실시간 오더북을 재조회(LLM 호출 없음)해 위반폭을 계산, `violations.jsonl`에 기록하고 resolve된 쌍은 사후 pnl을 갱신한다. 리포트 스크립트가 pattern_type(A/B)별로 탐지건수/평균pnl/승률을 낸다.

**Tech Stack:** Python 3.14, pytest, `openai.OpenAI`(Groq 호환 엔드포인트, `python-dotenv`), `requests`(기존 `polymarket/client.py`·`polymarket/clob_client.py` 재사용), jsonl 파일 저장(신규 DB 없음).

## Global Constraints

- v1은 **paper-only** — 실주문/지갑서명/실집행 코드 절대 작성 안 함(spec §7).
- 모든 위반 판정 레코드에 `pattern_type: "A" | "B"` 태그 필수, B타입만 독립적으로 끌 수 있어야 함(spec §3) — pattern_type별 분리 집계를 모든 리포트/테스트에서 지킨다.
- 기존 BH-FDR/랜덤셔플 파이프라인 사용 안 함 — 이 기능은 결정론적 부등식 위반 탐지이므로 별도 방식(QA 오탐률 + 포워드 페이퍼 로깅)으로 검증한다(spec §6).
- 최소 **N=20~30건** 포워드 데이터 쌓이기 전엔 결론 내지 않는다(spec §6-2) — report 모듈은 `MIN_FORWARD_N` 미만이면 `verdict: "insufficient_sample"`을 반환해야 한다.
- 만기 차이 큰 방향성 단일다리 쌍은 다루지 않는다 — 후보쌍은 항상 `MATURITY_WINDOW_DAYS` 이내 헤지형만(spec §7).
- LLM 클라이언트는 `ai_strategy/advisor.py`와 동일 배선(`OpenAI(base_url="https://api.groq.com/openai/v1", api_key=os.environ["GROQ_API_KEY"])`) 재사용, 신규 의존성 추가 안 함. 모델은 `llama-3.3-70b-versatile`(엔티티태깅·함의판정 공통, advisor.py의 `llama-3.1-8b-instant`보다 큼 — 오탐비용 고려, spec §5.1).
- Raw `fetch`/신규 HTTP 클라이언트 금지 — 시세는 `polymarket/client.py`(get_markets, get_market), `polymarket/clob_client.py`(get_order_book, spread_bps_from_book)만 재사용.
- 파일 I/O 테스트는 이 코드베이스 관례대로 `patch.object(module, "_DATA_DIR", tmp_path)`로 격리한다(경로는 매 호출 시 `_DATA_DIR / "파일명"`으로 동적 계산 — 모듈 상수로 미리 합쳐두지 않는다).
- pytest 실행: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/<파일> -q`.

---

## File Structure

```
research/polymarket_market_implication/
    __init__.py                              ← 신규, 빈 파일
    entity_tags.py                           ← 신규 (Task 1)
    pairing.py                                ← 신규 (Task 2)
research/hypotheses/
    polymarket_market_implication.py         ← 신규 (Task 3)
research/
    run_polymarket_market_implication_collect.py   ← 신규 (Task 4)
    run_polymarket_market_implication_watch.py     ← 신규 (Task 5)
    run_polymarket_market_implication_report.py    ← 신규 (Task 6)
tests/
    test_polymarket_market_implication_entity_tags.py   ← 신규 (Task 1)
    test_polymarket_market_implication_pairing.py       ← 신규 (Task 2)
    test_polymarket_market_implication.py               ← 신규 (Task 3)
    test_run_polymarket_market_implication_collect.py   ← 신규 (Task 4)
    test_run_polymarket_market_implication_watch.py     ← 신규 (Task 5)
    test_run_polymarket_market_implication_report.py    ← 신규 (Task 6)
```

데이터 저장 위치(신규 디렉토리, 코드가 `mkdir(parents=True, exist_ok=True)`로 생성):
`research/data/polymarket_market_implication/{entity_cache.json, YYYY-MM-DD.jsonl(마켓 스냅샷), pairs.jsonl, violations.jsonl}`

---

### Task 1: 엔티티 태깅 (`entity_tags.py`)

**Files:**
- Create: `research/polymarket_market_implication/__init__.py` (빈 파일)
- Create: `research/polymarket_market_implication/entity_tags.py`
- Test: `tests/test_polymarket_market_implication_entity_tags.py`

**Interfaces:**
- Consumes: 없음(마켓 dict는 `polymarket/client.py`의 `get_markets()` 반환 형식 — `condition_id`, `question` 필드만 사용)
- Produces:
  - `question_hash(question: str) -> str`
  - `extract_entities_llm(question: str) -> list[str]`
  - `load_cache() -> dict`, `save_cache(cache: dict) -> None`
  - `tag_markets(markets: list[dict], cache: dict, extract_fn=extract_entities_llm, max_new_calls: int | None = None) -> tuple[list[dict], dict, int]` — `(entities 필드 추가된 markets, 갱신된 cache, 이번 호출에서 실제 사용한 LLM 콜 수)`. Task 4가 `call_cap`으로 `max_new_calls`를 넘긴다.

- [ ] **Step 1: 패키지 초기화 파일 생성**

```bash
mkdir -p research/polymarket_market_implication
touch research/polymarket_market_implication/__init__.py
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_polymarket_market_implication_entity_tags.py`:

```python
import json
from unittest.mock import MagicMock, patch

from research.polymarket_market_implication import entity_tags


def _mock_openai(entities):
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(entities)
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
    return mock_client


def test_question_hash_changes_with_text():
    h1 = entity_tags.question_hash("Will X win?")
    h2 = entity_tags.question_hash("Will Y win?")
    assert h1 != h2
    assert h1 == entity_tags.question_hash("Will X win?")


def test_extract_entities_llm_parses_json_array():
    with patch("research.polymarket_market_implication.entity_tags.OpenAI",
               return_value=_mock_openai(["Trump", "Biden"])):
        result = entity_tags.extract_entities_llm("Will Trump beat Biden?")
    assert result == ["Trump", "Biden"]


def test_extract_entities_llm_handles_code_fence():
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "```json\n[\"Trump\"]\n```"
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
    with patch("research.polymarket_market_implication.entity_tags.OpenAI", return_value=mock_client):
        result = entity_tags.extract_entities_llm("Will Trump win?")
    assert result == ["Trump"]


def test_extract_entities_llm_returns_empty_on_malformed_response():
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "not json"
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
    with patch("research.polymarket_market_implication.entity_tags.OpenAI", return_value=mock_client):
        result = entity_tags.extract_entities_llm("Some question")
    assert result == []


def test_tag_markets_cache_hit_skips_llm_call():
    market = {"condition_id": "c1", "question": "Will X win?"}
    qh = entity_tags.question_hash("Will X win?")
    cache = {"c1": {"question_hash": qh, "entities": ["X"]}}
    extract_fn = MagicMock()
    tagged, updated_cache, calls_used = entity_tags.tag_markets([market], cache, extract_fn=extract_fn)
    assert tagged[0]["entities"] == ["X"]
    assert calls_used == 0
    extract_fn.assert_not_called()


def test_tag_markets_cache_miss_calls_llm_and_updates_cache():
    market = {"condition_id": "c1", "question": "Will X win?"}
    extract_fn = MagicMock(return_value=["X"])
    tagged, updated_cache, calls_used = entity_tags.tag_markets([market], {}, extract_fn=extract_fn)
    assert tagged[0]["entities"] == ["X"]
    assert calls_used == 1
    assert updated_cache["c1"]["entities"] == ["X"]
    extract_fn.assert_called_once_with("Will X win?")


def test_tag_markets_question_changed_recalls_llm():
    market = {"condition_id": "c1", "question": "Will X win in 2027?"}
    old_hash = entity_tags.question_hash("Will X win?")
    cache = {"c1": {"question_hash": old_hash, "entities": ["X"]}}
    extract_fn = MagicMock(return_value=["X", "2027"])
    tagged, updated_cache, calls_used = entity_tags.tag_markets([market], cache, extract_fn=extract_fn)
    assert tagged[0]["entities"] == ["X", "2027"]
    assert calls_used == 1
    extract_fn.assert_called_once()


def test_tag_markets_respects_max_new_calls_budget():
    markets = [
        {"condition_id": "c1", "question": "Q1"},
        {"condition_id": "c2", "question": "Q2"},
    ]
    extract_fn = MagicMock(return_value=["E"])
    tagged, updated_cache, calls_used = entity_tags.tag_markets(
        markets, {}, extract_fn=extract_fn, max_new_calls=1,
    )
    assert calls_used == 1
    assert tagged[0]["entities"] == ["E"]
    assert tagged[1]["entities"] == []
    assert "c2" not in updated_cache


def test_load_cache_missing_file_returns_empty_dict(tmp_path):
    with patch.object(entity_tags, "_CACHE_PATH", tmp_path / "entity_cache.json"):
        assert entity_tags.load_cache() == {}


def test_save_cache_then_load_cache_roundtrip(tmp_path):
    with patch.object(entity_tags, "_CACHE_PATH", tmp_path / "sub" / "entity_cache.json"):
        entity_tags.save_cache({"c1": {"question_hash": "h", "entities": ["X"]}})
        assert entity_tags.load_cache() == {"c1": {"question_hash": "h", "entities": ["X"]}}
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_market_implication_entity_tags.py -q`
Expected: FAIL(ModuleNotFoundError: No module named 'research.polymarket_market_implication.entity_tags')

- [ ] **Step 4: 구현**

`research/polymarket_market_implication/entity_tags.py`:

```python
"""Polymarket 마켓 질문에서 엔티티(고유명사) 추출 — LLM + 로컬 캐시.

`ai_strategy/advisor.py`와 동일한 Groq 배선(OpenAI 호환 엔드포인트) 재사용.
질문 텍스트가 안 바뀌는 한 재추출할 필요가 없으므로 question_hash 기준으로
캐시해 LLM 호출을 최소화한다 — pairing.py가 이 entities 필드로 후보쌍을
찾는다(설계 spec §4, §5.1)."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

_MODEL = "llama-3.3-70b-versatile"  # advisor.py의 llama-3.1-8b-instant보다 큰 모델(오탐비용 고려)
_CACHE_PATH = Path("research/data/polymarket_market_implication/entity_cache.json")


def question_hash(question: str) -> str:
    return hashlib.sha256(question.encode("utf-8")).hexdigest()


def extract_entities_llm(question: str) -> list[str]:
    """질문에서 고유명사(인물/팀/조직 등) 리스트 추출. 파싱 실패/빈 응답이면 []."""
    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=os.environ["GROQ_API_KEY"],
    )
    prompt = (
        "다음 예측시장 질문에서 핵심 개체명(인물/팀/조직 등 고유명사)만 추출해 "
        "JSON 배열로 반환해. 설명 없이 배열만 출력.\n\n"
        f"질문: {question}"
    )
    message = client.chat.completions.create(
        model=_MODEL,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    text = message.choices[0].message.content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        entities = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(entities, list):
        return []
    return [str(e).strip() for e in entities if str(e).strip()]


def load_cache() -> dict:
    if not _CACHE_PATH.exists():
        return {}
    return json.loads(_CACHE_PATH.read_text())


def save_cache(cache: dict) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2))


def tag_markets(
    markets: list[dict],
    cache: dict,
    extract_fn=extract_entities_llm,
    max_new_calls: int | None = None,
) -> tuple[list[dict], dict, int]:
    """markets 각각에 "entities" 필드 추가. 캐시 히트(question_hash 일치)면 재사용,
    아니면(신규/질문변경) extract_fn 호출 — max_new_calls 도달 후 남은 신규분은
    이번 사이클엔 스킵(캐시엔 안 씀 → 다음 실행에서 재시도).

    반환: (entities 필드 추가된 markets, 갱신된 cache, 이번 호출에서 실제 사용한 LLM 콜 수)."""
    updated_cache = dict(cache)
    tagged = []
    calls_used = 0
    for m in markets:
        cid = m["condition_id"]
        qh = question_hash(m["question"])
        entry = updated_cache.get(cid)
        if entry is not None and entry.get("question_hash") == qh:
            entities = entry["entities"]
        elif max_new_calls is not None and calls_used >= max_new_calls:
            entities = entry["entities"] if entry is not None else []
        else:
            entities = extract_fn(m["question"])
            updated_cache[cid] = {"question_hash": qh, "entities": entities}
            calls_used += 1
        tagged.append({**m, "entities": entities})
    return tagged, updated_cache, calls_used
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_market_implication_entity_tags.py -q`
Expected: PASS (11 tests)

- [ ] **Step 6: 커밋**

```bash
git add research/polymarket_market_implication/__init__.py \
        research/polymarket_market_implication/entity_tags.py \
        tests/test_polymarket_market_implication_entity_tags.py
git commit -m "feat: add LLM entity tagging for polymarket market-implication pairs"
```

---

### Task 2: 후보쌍 필터 (`pairing.py`)

**Files:**
- Create: `research/polymarket_market_implication/pairing.py`
- Test: `tests/test_polymarket_market_implication_pairing.py`

**Interfaces:**
- Consumes: Task 1의 `tag_markets()`가 붙인 `entities: list[str]` 필드, `get_markets()` 형식의 `condition_id`/`end_date`
- Produces:
  - `MATURITY_WINDOW_DAYS = 14`
  - `group_by_shared_entity(markets: list[dict]) -> dict[str, list[dict]]`
  - `candidate_pairs(markets: list[dict], maturity_window_days: int = MATURITY_WINDOW_DAYS) -> list[tuple[dict, dict]]` — Task 4가 태깅된 마켓 리스트를 그대로 넘긴다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_polymarket_market_implication_pairing.py`:

```python
from research.polymarket_market_implication import pairing


def _market(cid, question, end_date, entities):
    return {"condition_id": cid, "question": question, "end_date": end_date, "entities": entities}


def test_group_by_shared_entity_groups_and_drops_singletons():
    m1 = _market("c1", "Q1", "2026-09-01", ["X"])
    m2 = _market("c2", "Q2", "2026-09-05", ["X"])
    m3 = _market("c3", "Q3", "2026-09-10", ["Y"])
    groups = pairing.group_by_shared_entity([m1, m2, m3])
    assert list(groups.keys()) == ["X"]
    assert groups["X"] == [m1, m2]


def test_candidate_pairs_within_maturity_window_included():
    m1 = _market("c1", "Q1", "2026-09-01", ["X"])
    m2 = _market("c2", "Q2", "2026-09-14", ["X"])  # 13일 차이 (<14)
    pairs = pairing.candidate_pairs([m1, m2])
    assert pairs == [(m1, m2)]


def test_candidate_pairs_at_exact_boundary_included():
    m1 = _market("c1", "Q1", "2026-09-01", ["X"])
    m2 = _market("c2", "Q2", "2026-09-15", ["X"])  # 정확히 14일 차이 (==window, 포함)
    pairs = pairing.candidate_pairs([m1, m2], maturity_window_days=14)
    assert pairs == [(m1, m2)]


def test_candidate_pairs_outside_maturity_window_excluded():
    m1 = _market("c1", "Q1", "2026-09-01", ["X"])
    m2 = _market("c2", "Q2", "2026-09-16", ["X"])  # 15일 차이 (>window, 제외)
    pairs = pairing.candidate_pairs([m1, m2], maturity_window_days=14)
    assert pairs == []


def test_candidate_pairs_excludes_self_pair():
    m1 = _market("c1", "Q1", "2026-09-01", ["X"])
    pairs = pairing.candidate_pairs([m1, m1])
    assert pairs == []


def test_candidate_pairs_dedupes_across_multiple_shared_entities():
    m1 = _market("c1", "Q1", "2026-09-01", ["X", "Z"])
    m2 = _market("c2", "Q2", "2026-09-05", ["X", "Z"])
    pairs = pairing.candidate_pairs([m1, m2])
    assert pairs == [(m1, m2)]  # X그룹·Z그룹 양쪽에 다 걸려도 쌍은 1번만
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_market_implication_pairing.py -q`
Expected: FAIL(ModuleNotFoundError: No module named 'research.polymarket_market_implication.pairing')

- [ ] **Step 3: 구현**

`research/polymarket_market_implication/pairing.py`:

```python
"""엔티티 공유 + 만기근접 후보쌍 필터 — 순수함수, 저장/네트워크 없음.

entity_tags.tag_markets()가 붙인 "entities" 필드 기준으로 마켓을 묶고,
MATURITY_WINDOW_DAYS 안 드는(만기 비슷한) 쌍만 후보로 남긴다. 만기 차이 큰
방향성 단일다리 쌍은 자본 lock 리스크로 범위 밖 — 매칭만기 헤지형만 다루기로
한 설계 결정(spec §7)."""
from __future__ import annotations

import datetime as dt

MATURITY_WINDOW_DAYS = 14


def group_by_shared_entity(markets: list[dict]) -> dict[str, list[dict]]:
    """entities 필드 기준 엔티티별 그룹핑. 소속 마켓 1개뿐인 엔티티는 제외(비교 대상 없음)."""
    groups: dict[str, list[dict]] = {}
    for m in markets:
        for e in m.get("entities", []):
            groups.setdefault(e, []).append(m)
    return {e: ms for e, ms in groups.items() if len(ms) >= 2}


def candidate_pairs(
    markets: list[dict], maturity_window_days: int = MATURITY_WINDOW_DAYS
) -> list[tuple[dict, dict]]:
    """엔티티 공유 + 만기 차이 maturity_window_days 이내인 서로 다른 마켓 쌍(중복 제거)."""
    groups = group_by_shared_entity(markets)
    seen_keys: set[tuple[str, str]] = set()
    pairs: list[tuple[dict, dict]] = []
    for group_markets in groups.values():
        for i in range(len(group_markets)):
            for j in range(i + 1, len(group_markets)):
                a, b = group_markets[i], group_markets[j]
                if a["condition_id"] == b["condition_id"]:
                    continue
                key = tuple(sorted((a["condition_id"], b["condition_id"])))
                if key in seen_keys:
                    continue
                try:
                    end_a = dt.date.fromisoformat(a["end_date"])
                    end_b = dt.date.fromisoformat(b["end_date"])
                except (ValueError, TypeError):
                    continue
                if abs((end_a - end_b).days) > maturity_window_days:
                    continue
                seen_keys.add(key)
                pairs.append((a, b))
    return pairs
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_market_implication_pairing.py -q`
Expected: PASS (6 tests)

- [ ] **Step 5: 커밋**

```bash
git add research/polymarket_market_implication/pairing.py tests/test_polymarket_market_implication_pairing.py
git commit -m "feat: add maturity-matched candidate pair filter for market-implication pairs"
```

---

### Task 3: 함의판정 + 위반폭 계산 (`hypotheses/polymarket_market_implication.py`)

**Files:**
- Create: `research/hypotheses/polymarket_market_implication.py`
- Test: `tests/test_polymarket_market_implication.py`

**Interfaces:**
- Consumes: 없음(마켓 dict의 `question` 필드만 사용), `research.validation.cost_model.polymarket_effective_cost_bps`
- Produces:
  - `classify_implication_llm(market_a: dict, market_b: dict) -> dict | None` — `{"pattern_type": "A", "direction": "a_implies_b"|"b_implies_a"}` 또는 `{"pattern_type": "B"}` 또는 `None`(관계 없음/파싱 실패)
  - `compute_violation(pattern_type: str, direction: str | None, price_a: float, price_b: float, spread_bps_a: float = 0.0, spread_bps_b: float = 0.0) -> dict | None` — `{"pattern_type", "raw_violation", "cost_frac", "net_violation"}` 또는 `None`(비용 안 넘음). Task 4는 `direction`/`spread_bps`를 안 넘기고 판정만, Task 5(watch)는 실시간 가격+스프레드를 넘겨 위반 여부를 계산한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_polymarket_market_implication.py`:

```python
import json
from unittest.mock import MagicMock, patch

from research.hypotheses import polymarket_market_implication as impl


def _mock_openai(payload):
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(payload)
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
    return mock_client


def test_classify_implication_llm_pattern_a():
    with patch("research.hypotheses.polymarket_market_implication.OpenAI",
               return_value=_mock_openai({"pattern_type": "A", "direction": "a_implies_b"})):
        result = impl.classify_implication_llm({"question": "A"}, {"question": "B"})
    assert result == {"pattern_type": "A", "direction": "a_implies_b"}


def test_classify_implication_llm_pattern_b():
    with patch("research.hypotheses.polymarket_market_implication.OpenAI",
               return_value=_mock_openai({"pattern_type": "B"})):
        result = impl.classify_implication_llm({"question": "A"}, {"question": "B"})
    assert result == {"pattern_type": "B"}


def test_classify_implication_llm_none_relationship():
    with patch("research.hypotheses.polymarket_market_implication.OpenAI",
               return_value=_mock_openai({"pattern_type": "none"})):
        result = impl.classify_implication_llm({"question": "A"}, {"question": "B"})
    assert result is None


def test_classify_implication_llm_pattern_a_missing_direction_returns_none():
    with patch("research.hypotheses.polymarket_market_implication.OpenAI",
               return_value=_mock_openai({"pattern_type": "A"})):
        result = impl.classify_implication_llm({"question": "A"}, {"question": "B"})
    assert result is None


def test_classify_implication_llm_malformed_response():
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "not json"
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
    with patch("research.hypotheses.polymarket_market_implication.OpenAI", return_value=mock_client):
        result = impl.classify_implication_llm({"question": "A"}, {"question": "B"})
    assert result is None


def test_compute_violation_pattern_a_violated():
    result = impl.compute_violation("A", "a_implies_b", 0.60, 0.50, 0.0, 0.0)
    assert result["pattern_type"] == "A"
    assert result["raw_violation"] == 0.10
    assert result["net_violation"] == 0.10


def test_compute_violation_pattern_a_not_violated_when_cost_exceeds():
    result = impl.compute_violation("A", "a_implies_b", 0.51, 0.50, 200.0, 200.0)
    assert result is None


def test_compute_violation_pattern_a_no_violation_when_inequality_holds():
    result = impl.compute_violation("A", "a_implies_b", 0.40, 0.50, 0.0, 0.0)
    assert result is None


def test_compute_violation_pattern_a_direction_b_implies_a():
    result = impl.compute_violation("A", "b_implies_a", 0.50, 0.60, 0.0, 0.0)
    assert result["raw_violation"] == 0.10


def test_compute_violation_pattern_a_missing_direction_returns_none():
    result = impl.compute_violation("A", None, 0.60, 0.50, 0.0, 0.0)
    assert result is None


def test_compute_violation_pattern_b_violated():
    result = impl.compute_violation("B", None, 0.60, 0.55, 0.0, 0.0)
    assert result["pattern_type"] == "B"
    assert result["raw_violation"] == 0.15


def test_compute_violation_pattern_b_not_violated():
    result = impl.compute_violation("B", None, 0.40, 0.30, 0.0, 0.0)
    assert result is None


def test_compute_violation_unknown_pattern_type_returns_none():
    result = impl.compute_violation("C", None, 0.60, 0.50)
    assert result is None
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_market_implication.py -q`
Expected: FAIL(ModuleNotFoundError: No module named 'research.hypotheses.polymarket_market_implication')

- [ ] **Step 3: 구현**

`research/hypotheses/polymarket_market_implication.py`:

```python
"""Polymarket 크로스이벤트 논리적 함의관계 위반 탐지 — LLM 함의판정 + 위반폭 계산.

기존 sharp_wallet/whale류(확률적 트레이더 행동패턴 추정)와 다르게 결정론적
부등식 위반을 본다(spec §2, §6). A타입(계층형 함의)과 B타입(교차이벤트
상호배타) 2종류, pattern_type 태그로 항상 분리 집계해야 한다(spec §3 —
B타입만 언제든 독립적으로 끌 수 있어야 함)."""
from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from research.validation.cost_model import polymarket_effective_cost_bps

load_dotenv()

_MODEL = "llama-3.3-70b-versatile"  # entity_tags.py와 동일값(복제, import 금지 — 프로젝트 컨벤션)


def classify_implication_llm(market_a: dict, market_b: dict) -> dict | None:
    """두 마켓 질문의 논리적 관계 판정. 관계 없음/파싱 실패면 None.

    반환(관계 있을 시): {"pattern_type": "A", "direction": "a_implies_b"|"b_implies_a"}
    또는 {"pattern_type": "B"} (상호배타, 방향 무관)."""
    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=os.environ["GROQ_API_KEY"],
    )
    prompt = (
        "두 예측시장 질문의 논리적 관계를 판정해. 다음 중 하나로만 JSON 응답(설명 없이):\n"
        '{"pattern_type": "A", "direction": "a_implies_b"} - A가 참이면 B도 반드시 참(계층형 함의)\n'
        '{"pattern_type": "A", "direction": "b_implies_a"} - B가 참이면 A도 반드시 참\n'
        '{"pattern_type": "B"} - 두 질문이 동시에 참일 수 없음(상호배타)\n'
        '{"pattern_type": "none"} - 논리적 관계 없음\n\n'
        f"A: {market_a['question']}\nB: {market_b['question']}"
    )
    message = client.chat.completions.create(
        model=_MODEL,
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}],
    )
    text = message.choices[0].message.content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    pattern_type = parsed.get("pattern_type")
    if pattern_type == "B":
        return {"pattern_type": "B"}
    if pattern_type == "A" and parsed.get("direction") in ("a_implies_b", "b_implies_a"):
        return {"pattern_type": "A", "direction": parsed["direction"]}
    return None


def compute_violation(
    pattern_type: str,
    direction: str | None,
    price_a: float,
    price_b: float,
    spread_bps_a: float = 0.0,
    spread_bps_b: float = 0.0,
) -> dict | None:
    """부등식 위반폭 계산 - 왕복비용(양다리분) 차감 후 순위반폭. 비용 안 넘으면 None.

    A타입: P(implied) >= P(implying) 강제. raw_violation = implying가격 - implied가격.
    B타입: P(a)+P(b) <= 1 강제. raw_violation = price_a + price_b - 1."""
    if pattern_type == "A":
        if direction == "a_implies_b":
            implying, implied = price_a, price_b
        elif direction == "b_implies_a":
            implying, implied = price_b, price_a
        else:
            return None
        raw_violation = implying - implied
    elif pattern_type == "B":
        raw_violation = price_a + price_b - 1.0
    else:
        return None
    cost_frac = (
        polymarket_effective_cost_bps(spread_bps_a) + polymarket_effective_cost_bps(spread_bps_b)
    ) / 10_000.0
    net_violation = raw_violation - cost_frac
    if net_violation <= 0:
        return None
    return {
        "pattern_type": pattern_type,
        "raw_violation": round(raw_violation, 4),
        "cost_frac": round(cost_frac, 4),
        "net_violation": round(net_violation, 4),
    }
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_market_implication.py -q`
Expected: PASS (13 tests)

- [ ] **Step 5: 커밋**

```bash
git add research/hypotheses/polymarket_market_implication.py tests/test_polymarket_market_implication.py
git commit -m "feat: add implication classification and violation-width calc for polymarket pairs"
```

---

### Task 4: 수집기 (`run_polymarket_market_implication_collect.py`)

**Files:**
- Create: `research/run_polymarket_market_implication_collect.py`
- Test: `tests/test_run_polymarket_market_implication_collect.py`

**Interfaces:**
- Consumes: `polymarket.client.get_markets`, Task 1의 `entity_tags.load_cache/save_cache/tag_markets/extract_entities_llm`, Task 2의 `pairing.candidate_pairs`, Task 3의 `classify_implication_llm`
- Produces:
  - `SCAN_INTERVAL_S = 86400.0`, `MIN_VOLUME_USD = 500.0`, `LLM_DAILY_CALL_CAP = 500`
  - `pair_key(a: dict, b: dict) -> str`
  - `run_once(*, get_markets_fn=get_markets, extract_fn=..., classify_fn=..., call_cap=LLM_DAILY_CALL_CAP) -> dict` — `{"markets_scanned", "entity_calls_used", "classify_calls_used", "pairs_added"}`
  - `pairs.jsonl` 레코드 스키마(Task 5가 그대로 읽음): `{"pair_key", "condition_id_a", "condition_id_b", "token_id_a", "token_id_b", "question_a", "question_b", "end_date_a", "end_date_b", "pattern_type", "direction", "created_ts"}`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_run_polymarket_market_implication_collect.py`:

```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_polymarket_market_implication_collect.py -q`
Expected: FAIL(ModuleNotFoundError: No module named 'research.run_polymarket_market_implication_collect')

- [ ] **Step 3: 구현**

`research/run_polymarket_market_implication_collect.py`:

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_polymarket_market_implication_collect.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5: 커밋**

```bash
git add research/run_polymarket_market_implication_collect.py tests/test_run_polymarket_market_implication_collect.py
git commit -m "feat: add daily collector for polymarket market-implication candidate pairs"
```

---

### Task 5: 가격 워치 + 위반 로깅 (`run_polymarket_market_implication_watch.py`)

**Files:**
- Create: `research/run_polymarket_market_implication_watch.py`
- Test: `tests/test_run_polymarket_market_implication_watch.py`

**Interfaces:**
- Consumes: `polymarket.client.get_market`, `polymarket.clob_client.get_order_book/spread_bps_from_book`, Task 3의 `compute_violation`, `research.validation.cost_model.POLYMARKET_SPREAD_BPS`, Task 4가 쓴 `pairs.jsonl` 스키마
- Produces:
  - `WATCH_INTERVAL_S = 3600.0`
  - `load_pairs() -> list[dict]`, `load_violations() -> list[dict]`, `save_violations(violations: list[dict]) -> None`
  - `check_pair(pair: dict, get_book_fn=get_order_book) -> dict | None`
  - `resolve_pnl(violation: dict, market_a: dict, market_b: dict) -> dict | None`
  - `run_once(*, get_book_fn=..., append_new=True) -> list[dict]`, `resolve_pending(*, get_market_fn=get_market) -> int`
  - `violations.jsonl` 레코드 스키마(Task 6이 그대로 읽음): `{"pattern_type", "raw_violation", "cost_frac", "net_violation", "pair_key", "condition_id_a", "condition_id_b", "direction", "detected_ts", "price_a", "price_b", "resolved", "pnl_per_share"(resolved 시)}`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_run_polymarket_market_implication_watch.py`:

```python
import json
from unittest.mock import patch

import research.run_polymarket_market_implication_watch as watch


def _pair(pattern_type="A", direction="a_implies_b"):
    return {
        "pair_key": "c1|c2", "condition_id_a": "c1", "condition_id_b": "c2",
        "token_id_a": "tok_a", "token_id_b": "tok_b",
        "pattern_type": pattern_type, "direction": direction,
    }


def test_check_pair_returns_none_when_book_missing():
    assert watch.check_pair(_pair(), lambda tid: None) is None


def test_check_pair_returns_none_when_no_violation():
    books = {"tok_a": {"best_bid": 0.39, "best_ask": 0.41}, "tok_b": {"best_bid": 0.49, "best_ask": 0.51}}
    result = watch.check_pair(_pair(), lambda tid: books[tid])
    assert result is None  # implying(A) mid=0.40 <= implied(B) mid=0.50, 위반 아님


def test_check_pair_detects_violation_past_cost():
    books = {"tok_a": {"best_bid": 0.69, "best_ask": 0.71}, "tok_b": {"best_bid": 0.49, "best_ask": 0.51}}
    result = watch.check_pair(_pair(), lambda tid: books[tid])
    assert result is not None
    assert result["pattern_type"] == "A"
    assert result["pair_key"] == "c1|c2"
    assert result["resolved"] is False


def test_run_once_appends_detected_violations(tmp_path):
    with patch.object(watch, "_DATA_DIR", tmp_path):
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "pairs.jsonl").write_text(json.dumps(_pair()) + "\n")
        books = {"tok_a": {"best_bid": 0.69, "best_ask": 0.71}, "tok_b": {"best_bid": 0.49, "best_ask": 0.51}}
        detected = watch.run_once(get_book_fn=lambda tid: books[tid])
        saved = watch.load_violations()
    assert len(detected) == 1
    assert len(saved) == 1
    assert saved[0]["pattern_type"] == "A"


def test_resolve_pnl_returns_none_when_not_both_closed():
    violation = {"pattern_type": "A", "direction": "a_implies_b", "price_a": 0.70, "price_b": 0.50, "cost_frac": 0.0}
    market_a = {"closed": True, "yes_price": 1.0}
    market_b = {"closed": False, "yes_price": 0.0}
    assert watch.resolve_pnl(violation, market_a, market_b) is None


def test_resolve_pnl_computes_pnl_pattern_a():
    violation = {"pattern_type": "A", "direction": "a_implies_b", "price_a": 0.70, "price_b": 0.50, "cost_frac": 0.05}
    market_a = {"closed": True, "yes_price": 1.0}
    market_b = {"closed": True, "yes_price": 1.0}
    result = watch.resolve_pnl(violation, market_a, market_b)
    # (0.70-1.0) + (1.0-0.50) - 0.05 = 0.15
    assert result["pnl_per_share"] == 0.15
    assert result["resolved"] is True


def test_resolve_pnl_computes_pnl_pattern_b():
    violation = {"pattern_type": "B", "price_a": 0.60, "price_b": 0.55, "cost_frac": 0.05}
    market_a = {"closed": True, "yes_price": 1.0}
    market_b = {"closed": True, "yes_price": 0.0}
    result = watch.resolve_pnl(violation, market_a, market_b)
    # (0.60-1.0) + (0.55-0.0) - 0.05 = 0.10
    assert result["pnl_per_share"] == 0.10


def test_resolve_pending_updates_violations_file(tmp_path):
    violation = {
        "pattern_type": "A", "direction": "a_implies_b", "price_a": 0.70, "price_b": 0.50,
        "cost_frac": 0.05, "condition_id_a": "c1", "condition_id_b": "c2", "resolved": False,
    }
    with patch.object(watch, "_DATA_DIR", tmp_path):
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "violations.jsonl").write_text(json.dumps(violation) + "\n")

        def get_market_fn(cid):
            return {"closed": True, "yes_price": 1.0}

        updated_count = watch.resolve_pending(get_market_fn=get_market_fn)
        saved = watch.load_violations()
    assert updated_count == 1
    assert saved[0]["resolved"] is True
    assert saved[0]["pnl_per_share"] == 0.15
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_polymarket_market_implication_watch.py -q`
Expected: FAIL(ModuleNotFoundError: No module named 'research.run_polymarket_market_implication_watch')

- [ ] **Step 3: 구현**

`research/run_polymarket_market_implication_watch.py`:

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_polymarket_market_implication_watch.py -q`
Expected: PASS (8 tests)

- [ ] **Step 5: 커밋**

```bash
git add research/run_polymarket_market_implication_watch.py tests/test_run_polymarket_market_implication_watch.py
git commit -m "feat: add hourly price watch + violation logging for polymarket implication pairs"
```

---

### Task 6: 리포트 (`run_polymarket_market_implication_report.py`)

**Files:**
- Create: `research/run_polymarket_market_implication_report.py`
- Test: `tests/test_run_polymarket_market_implication_report.py`

**Interfaces:**
- Consumes: Task 5의 `load_violations()`와 `violations.jsonl` 스키마(`pattern_type`, `resolved`, `pnl_per_share`)
- Produces: `MIN_FORWARD_N = 20`, `compute_report(violations: list[dict] | None = None) -> dict`, `main() -> None`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_run_polymarket_market_implication_report.py`:

```python
from research.run_polymarket_market_implication_report import compute_report


def _violation(pattern_type, resolved=True, pnl=0.1):
    v = {"pattern_type": pattern_type, "resolved": resolved}
    if resolved:
        v["pnl_per_share"] = pnl
    return v


def test_compute_report_splits_by_pattern_type():
    violations = [_violation("A", pnl=0.1), _violation("B", pnl=-0.2)]
    report = compute_report(violations)
    assert report["A"]["detected"] == 1
    assert report["B"]["detected"] == 1
    assert report["A"]["mean_pnl"] == 0.1
    assert report["B"]["mean_pnl"] == -0.2


def test_compute_report_ignores_unresolved_for_pnl():
    violations = [_violation("A", resolved=False), _violation("A", pnl=0.2)]
    report = compute_report(violations)
    assert report["A"]["detected"] == 2
    assert report["A"]["resolved"] == 1
    assert report["A"]["mean_pnl"] == 0.2


def test_compute_report_win_rate():
    violations = [_violation("A", pnl=0.1), _violation("A", pnl=-0.1), _violation("A", pnl=0.05)]
    report = compute_report(violations)
    assert report["A"]["win_rate"] == round(2 / 3, 4)


def test_compute_report_verdict_insufficient_sample_below_min_n():
    violations = [_violation("A", pnl=0.1)]
    report = compute_report(violations)
    assert report["A"]["verdict"] == "insufficient_sample"


def test_compute_report_no_data_returns_none_stats():
    report = compute_report([])
    assert report["A"] == {
        "detected": 0, "resolved": 0, "mean_pnl": None, "win_rate": None,
        "verdict": "insufficient_sample",
    }
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_polymarket_market_implication_report.py -q`
Expected: FAIL(ModuleNotFoundError: No module named 'research.run_polymarket_market_implication_report')

- [ ] **Step 3: 구현**

`research/run_polymarket_market_implication_report.py`:

```python
"""Polymarket 함의관계 위반 리포트 — 기존 BH-FDR compute_report와 다른 집계.

논리위반은 통계적 유의성이 아니라 (1)정성적 QA 오탐률(사람이 직접 확인,
자동화 밖) (2)포워드 페이퍼 로깅 pnl 집계로 검증한다(spec §6). 이 스크립트는
(2)만 자동화 — violations.jsonl을 pattern_type(A/B)별로 나눠 탐지건수/
해소건수/평균pnl/승률을 낸다. 최소 N=20~30건 쌓이기 전엔 결론 내지 말 것
(spec §6-2, 사용자 명시 요구 — sharp_wallet 표본부족 보류 반복 방지)."""
from __future__ import annotations

import json

from research.run_polymarket_market_implication_watch import load_violations

MIN_FORWARD_N = 20


def compute_report(violations: list[dict] | None = None) -> dict:
    violations = violations if violations is not None else load_violations()
    report = {}
    for pattern in ("A", "B"):
        pv = [v for v in violations if v["pattern_type"] == pattern]
        resolved = [v for v in pv if v.get("resolved")]
        pnls = [v["pnl_per_share"] for v in resolved]
        n = len(pnls)
        report[pattern] = {
            "detected": len(pv),
            "resolved": n,
            "mean_pnl": round(sum(pnls) / n, 4) if n else None,
            "win_rate": round(sum(1 for p in pnls if p > 0) / n, 4) if n else None,
            "verdict": "insufficient_sample" if n < MIN_FORWARD_N else "ready_for_review",
        }
    return report


def main() -> None:
    print(json.dumps(compute_report(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_polymarket_market_implication_report.py -q`
Expected: PASS (5 tests)

- [ ] **Step 5: 커밋**

```bash
git add research/run_polymarket_market_implication_report.py tests/test_run_polymarket_market_implication_report.py
git commit -m "feat: add pattern_type-split forward pnl report for polymarket implication pairs"
```

---

## Post-Plan (실행 밖 — 사용자 확인 필요)

- 라이브 tmux 상시실행(`run_polymarket_market_implication_collect.py`, `_watch.py`)은 이 플랜 범위 밖. 전체 테스트 통과 후 사용자에게 시작 여부를 확인할 것(다른 상시 수집기들처럼 tmux 세션으로).
- Groq에서 `llama-3.3-70b-versatile` 모델명이 유효한지 구현 시점에 1회 실호출로 확인(spec §5.1 "정확한 모델명은 구현 시점 Groq 가용 모델 확인 후 확정" — 모델이 deprecated/변경됐으면 `_MODEL` 상수만 갱신).
