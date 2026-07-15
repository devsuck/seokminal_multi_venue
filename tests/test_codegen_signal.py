from unittest.mock import patch

from research.papers.codegen_signal import generate_signal_code

_SPEC = {
    "asset_class": "equity_intraday",
    "signal_description": "VWAP 이탈 평균회귀",
    "direction": "long_only",
    "holding_period": "1일 이내",
    "data_requirements": ["15분봉 OHLCV"],
}

_GENERATED_CODE = '''NAME = "vwap_fade"
DESCRIPTION = "VWAP 이탈 평균회귀"

def signal_fn(ohlc, feat, aux, params):
    return {"entry": [False] * len(ohlc["close"]), "eligible": []}
'''


def test_generate_signal_code_returns_llm_output_verbatim():
    with patch("research.papers.codegen_signal.call_claude", return_value=_GENERATED_CODE) as mock_call:
        code = generate_signal_code(_SPEC)
    assert code == _GENERATED_CODE
    mock_call.assert_called_once()


def test_generate_signal_code_prompt_includes_spec_fields():
    captured = {}

    def fake_call(prompt, *a, **kw):
        captured["prompt"] = prompt
        return _GENERATED_CODE

    with patch("research.papers.codegen_signal.call_claude", side_effect=fake_call):
        generate_signal_code(_SPEC)
    assert "VWAP 이탈 평균회귀" in captured["prompt"]
    assert "signal_fn" in captured["prompt"]
    assert "entry" in captured["prompt"] and "eligible" in captured["prompt"]
