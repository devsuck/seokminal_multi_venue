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
