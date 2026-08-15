"""_build_critic_prompt zero-trade 회귀 테스트 (division by zero 버그)."""
from api_server.lv5_agent import _build_critic_prompt


def test_build_critic_prompt_with_zero_outcomes_does_not_raise():
    prompt = _build_critic_prompt("제안 내용", [], "컨텍스트")
    assert "최근 0건" in prompt
    assert "승률 0%" in prompt
