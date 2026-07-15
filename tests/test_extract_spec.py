# tests/test_extract_spec.py
import json
from unittest.mock import patch

import pytest

from research.papers.extract_spec import extract_spec

_VALID_SPEC = {
    "asset_class": "equity_intraday",
    "signal_description": "장 시작 30분 이후 VWAP 대비 0.4% 이상 이탈 시 평균회귀",
    "direction": "long_only",
    "holding_period": "1일 이내",
    "data_requirements": ["15분봉 OHLCV"],
}


def test_extract_spec_parses_valid_llm_response():
    with patch("research.papers.extract_spec.call_claude", return_value=json.dumps(_VALID_SPEC)):
        spec = extract_spec("some paper text")
    assert spec == _VALID_SPEC


def test_extract_spec_raises_on_malformed_json():
    with patch("research.papers.extract_spec.call_claude", return_value="not json{{{"):
        with pytest.raises(ValueError):
            extract_spec("some paper text")


def test_extract_spec_raises_on_missing_required_key():
    incomplete = {k: v for k, v in _VALID_SPEC.items() if k != "asset_class"}
    with patch("research.papers.extract_spec.call_claude", return_value=json.dumps(incomplete)):
        with pytest.raises(ValueError):
            extract_spec("some paper text")


def test_extract_spec_truncates_long_paper_text():
    captured = {}

    def fake_call(prompt, *a, **kw):
        captured["prompt"] = prompt
        return json.dumps(_VALID_SPEC)

    with patch("research.papers.extract_spec.call_claude", side_effect=fake_call):
        extract_spec("x" * 100_000)
    assert len(captured["prompt"]) < 100_000


def test_extract_spec_strips_json_language_tagged_fence():
    fenced = "```json\n" + json.dumps(_VALID_SPEC) + "\n```"
    with patch("research.papers.extract_spec.call_claude", return_value=fenced):
        spec = extract_spec("some paper text")
    assert spec == _VALID_SPEC


def test_extract_spec_strips_plain_fence():
    fenced = "```\n" + json.dumps(_VALID_SPEC) + "\n```"
    with patch("research.papers.extract_spec.call_claude", return_value=fenced):
        spec = extract_spec("some paper text")
    assert spec == _VALID_SPEC


def test_extract_spec_raises_on_non_dict_json():
    with patch("research.papers.extract_spec.call_claude", return_value="[1, 2, 3]"):
        with pytest.raises(ValueError):
            extract_spec("some paper text")
