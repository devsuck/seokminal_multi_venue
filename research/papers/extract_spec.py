"""논문 텍스트 → 구조화 스펙(JSON) — LLM 호출 1건.

llm_cli.call_claude()로 Claude CLI 서브프로세스를 호출하고, 응답을 고정
스키마(asset_class/signal_description/direction/holding_period/
data_requirements)로 검증한다. asset_class는 자산군 무관하게 항상 채우되,
코드생성기(codegen_signal.py)는 equity_intraday일 때만 연결한다."""
from __future__ import annotations

import json

from research.papers.llm_cli import call_claude, strip_code_fence

_REQUIRED_KEYS = {"asset_class", "signal_description", "direction", "holding_period", "data_requirements"}
_MAX_CHARS = 40_000

_PROMPT_TEMPLATE = """다음은 계량투자 학술논문의 텍스트다. 이 논문이 제시하는 트레이딩
시그널/전략을 아래 JSON 스키마로만 응답하라 (설명 텍스트 없이 JSON만):

{{
  "asset_class": "equity_intraday" | "equity_daily" | "crypto" | "futures" | "options" | "fx" | "other",
  "signal_description": "<시그널을 계산 가능한 수준으로 한 문단 요약>",
  "direction": "long_only" | "long_short" | "unclear",
  "holding_period": "<보유기간, 예: '1일 이내' 또는 '5-20 거래일'>",
  "data_requirements": ["<필요 데이터 종류, 예: '15분봉 OHLCV', '옵션 IV 서페이스'>"]
}}

asset_class는 논문이 실제로 검증한 자산군을 반영하되, 일중(장중) 주가/거래량만으로
계산 가능한 시그널이면 "equity_intraday"로 분류하라.

논문:
---
{paper_text}
---
"""


def extract_spec(paper_text: str) -> dict:
    prompt = _PROMPT_TEMPLATE.format(paper_text=paper_text[:_MAX_CHARS])
    raw = call_claude(prompt)
    try:
        spec = json.loads(strip_code_fence(raw))
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM 응답 JSON 파싱 실패: {e}\n원본: {raw[:500]}") from e
    if not isinstance(spec, dict):
        raise ValueError(f"LLM 응답이 JSON 객체가 아님: {raw[:500]}")
    missing = _REQUIRED_KEYS - spec.keys()
    if missing:
        raise ValueError(f"LLM 응답에 필수 키 누락: {missing}")
    return spec
