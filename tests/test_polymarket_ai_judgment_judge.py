"""Polymarket AI 판단 모듈(Tavily 검색 + Groq 판단 + 캐시/예산) 테스트."""
import json
from unittest.mock import MagicMock, patch

from research.polymarket_ai_judgment import judge


def _mock_groq(payload: dict | str):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = text
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
    return mock_client


def _mock_tavily(results: list[dict] | None = None):
    mock_client = MagicMock()
    mock_client.search.return_value = {"results": results if results is not None else [
        {"title": "T", "url": "https://x", "content": "some snippet"},
    ]}
    return mock_client


def test_question_hash_changes_with_text():
    h1 = judge.question_hash("Will X win?")
    h2 = judge.question_hash("Will Y win?")
    assert h1 != h2
    assert h1 == judge.question_hash("Will X win?")


def test_search_and_judge_parses_valid_json():
    result = judge.search_and_judge(
        "Will X win?",
        tavily_client=_mock_tavily(),
        groq_client=_mock_groq({"yes_prob": 0.72, "reasoning": "strong lead"}),
    )
    assert result == {"yes_prob": 0.72, "reasoning": "strong lead"}


def test_search_and_judge_handles_code_fence():
    result = judge.search_and_judge(
        "Will X win?",
        tavily_client=_mock_tavily(),
        groq_client=_mock_groq('```json\n{"yes_prob": 0.4, "reasoning": "close race"}\n```'),
    )
    assert result == {"yes_prob": 0.4, "reasoning": "close race"}


def test_search_and_judge_returns_none_on_malformed_json():
    result = judge.search_and_judge(
        "Will X win?", tavily_client=_mock_tavily(), groq_client=_mock_groq("not json"),
    )
    assert result is None


def test_search_and_judge_returns_none_when_yes_prob_out_of_range():
    result = judge.search_and_judge(
        "Will X win?",
        tavily_client=_mock_tavily(),
        groq_client=_mock_groq({"yes_prob": 1.5, "reasoning": "bad"}),
    )
    assert result is None


def test_search_and_judge_returns_none_on_tavily_failure():
    tavily_client = MagicMock()
    tavily_client.search.side_effect = RuntimeError("network down")
    result = judge.search_and_judge(
        "Will X win?", tavily_client=tavily_client, groq_client=_mock_groq({"yes_prob": 0.5, "reasoning": "x"}),
    )
    assert result is None


def test_search_and_judge_returns_none_on_groq_failure():
    groq_client = MagicMock()
    groq_client.chat.completions.create.side_effect = RuntimeError("api down")
    result = judge.search_and_judge(
        "Will X win?", tavily_client=_mock_tavily(), groq_client=groq_client,
    )
    assert result is None


def test_load_cache_missing_file_returns_empty_dict(tmp_path):
    with patch.object(judge, "_CACHE_PATH", tmp_path / "judge_cache.json"):
        assert judge.load_cache() == {}


def test_save_cache_then_load_cache_roundtrip(tmp_path):
    with patch.object(judge, "_CACHE_PATH", tmp_path / "sub" / "judge_cache.json"):
        judge.save_cache({"c1": {"question_hash": "h", "judgment": {"yes_prob": 0.5, "reasoning": "r"}}})
        assert judge.load_cache() == {"c1": {"question_hash": "h", "judgment": {"yes_prob": 0.5, "reasoning": "r"}}}


def test_load_daily_state_missing_file_returns_zero(tmp_path):
    with patch.object(judge, "_DAILY_STATE_PATH", tmp_path / "daily_call_state.json"):
        state = judge.load_daily_state()
    assert state["calls_used"] == 0


def test_load_daily_state_resets_on_date_rollover(tmp_path):
    path = tmp_path / "daily_call_state.json"
    path.write_text(json.dumps({"date": "2020-01-01", "calls_used": 25}))
    with patch.object(judge, "_DAILY_STATE_PATH", path):
        state = judge.load_daily_state()
    assert state["calls_used"] == 0
    assert state["date"] != "2020-01-01"


def test_load_daily_state_keeps_count_same_day(tmp_path):
    import datetime as _dt
    today = _dt.date.today().isoformat()
    path = tmp_path / "daily_call_state.json"
    path.write_text(json.dumps({"date": today, "calls_used": 12}))
    with patch.object(judge, "_DAILY_STATE_PATH", path):
        state = judge.load_daily_state()
    assert state == {"date": today, "calls_used": 12}


def test_judge_markets_cache_hit_skips_call():
    market = {"condition_id": "c1", "question": "Will X win?"}
    qh = judge.question_hash("Will X win?")
    cache = {"c1": {"question_hash": qh, "judgment": {"yes_prob": 0.6, "reasoning": "r"}}}
    judge_fn = MagicMock()
    judged, updated_cache, updated_state, calls_used = judge.judge_markets(
        [market], cache, {"date": "x", "calls_used": 0}, 5, 30, judge_fn=judge_fn,
    )
    assert judged[0]["judgment"] == {"yes_prob": 0.6, "reasoning": "r"}
    assert calls_used == 0
    judge_fn.assert_not_called()


def test_judge_markets_cache_miss_calls_and_caches_success():
    market = {"condition_id": "c1", "question": "Will X win?"}
    judge_fn = MagicMock(return_value={"yes_prob": 0.6, "reasoning": "r"})
    judged, updated_cache, updated_state, calls_used = judge.judge_markets(
        [market], {}, {"date": "x", "calls_used": 0}, 5, 30, judge_fn=judge_fn,
    )
    assert judged[0]["judgment"] == {"yes_prob": 0.6, "reasoning": "r"}
    assert calls_used == 1
    assert updated_cache["c1"]["judgment"] == {"yes_prob": 0.6, "reasoning": "r"}
    assert updated_state["calls_used"] == 1


def test_judge_markets_failure_not_cached_for_retry():
    market = {"condition_id": "c1", "question": "Will X win?"}
    judge_fn = MagicMock(return_value=None)
    judged, updated_cache, updated_state, calls_used = judge.judge_markets(
        [market], {}, {"date": "x", "calls_used": 0}, 5, 30, judge_fn=judge_fn,
    )
    assert judged[0]["judgment"] is None
    assert calls_used == 1  # 시도는 예산 소모
    assert "c1" not in updated_cache  # 캐시엔 안 남음 — 다음 틱 재시도


def test_judge_markets_respects_per_tick_budget():
    markets = [
        {"condition_id": "c1", "question": "Q1"},
        {"condition_id": "c2", "question": "Q2"},
    ]
    judge_fn = MagicMock(return_value={"yes_prob": 0.5, "reasoning": "r"})
    judged, updated_cache, updated_state, calls_used = judge.judge_markets(
        markets, {}, {"date": "x", "calls_used": 0}, 1, 30, judge_fn=judge_fn,
    )
    assert calls_used == 1
    assert judged[0]["judgment"] is not None
    assert judged[1]["judgment"] is None
    assert "c2" not in updated_cache


def test_judge_markets_respects_daily_budget_even_under_tick_cap():
    markets = [
        {"condition_id": "c1", "question": "Q1"},
        {"condition_id": "c2", "question": "Q2"},
    ]
    judge_fn = MagicMock(return_value={"yes_prob": 0.5, "reasoning": "r"})
    judged, updated_cache, updated_state, calls_used = judge.judge_markets(
        markets, {}, {"date": "x", "calls_used": 29}, 5, 30, judge_fn=judge_fn,
    )
    assert calls_used == 1
    assert updated_state["calls_used"] == 30


def test_judge_markets_daily_budget_exhausted_skips_all_new():
    markets = [{"condition_id": "c1", "question": "Q1"}]
    judge_fn = MagicMock(return_value={"yes_prob": 0.5, "reasoning": "r"})
    judged, updated_cache, updated_state, calls_used = judge.judge_markets(
        markets, {}, {"date": "x", "calls_used": 30}, 5, 30, judge_fn=judge_fn,
    )
    assert calls_used == 0
    assert judged[0]["judgment"] is None
    judge_fn.assert_not_called()
