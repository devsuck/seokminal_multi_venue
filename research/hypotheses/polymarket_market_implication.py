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
