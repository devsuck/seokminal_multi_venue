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
