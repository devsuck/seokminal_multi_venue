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
