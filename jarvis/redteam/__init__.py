"""Red-Team 층 — LLM(MD)이 필요한 통제를 요구, 결정적 코드가 실행+판정.

원칙: LLM은 "이 전략엔 이 통제 돌려" 요구까지. 판정은 결정적(random·BH-FDR·confound·survivorship).
오늘 배운 교훈(SMT confound·무상증자 ex-date·swings lookahead)을 통제 카탈로그로 encode.
승격은 필요 통제 전부 통과해야. LLM 합의 = verdict 아님.
"""
from jarvis.redteam.controls import CONTROLS, required_controls  # noqa: F401
from jarvis.redteam.review import audit_registry, review_strategy  # noqa: F401
