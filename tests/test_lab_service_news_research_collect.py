"""_news_research_collect — 24h 스로틀로 보유종목(live+paper) 뉴스 헤드라인+본문(Jina Reader)을
수집해 jarvis ResearchFeedPipeline.collect()에 주입, 리포트 제출. READ ONLY, 신호 아님."""
from __future__ import annotations

import os

import pytest

from research.lab.service import ResearchService


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    import importlib
    for mod in ("jarvis.audit.log", "jarvis.registry.lifecycle", "jarvis.watchdog",
                "jarvis.research_agents.ledger", "research.lab.service"):
        monkeypatch.setattr(importlib.import_module(mod), "state_path", sp)
    return tmp_path


class _FakeAggregator:
    """live -> 005930(kis) 1건, paper -> AAPL(hl) 1건. 실제 PortfolioAggregator(mode).summary()
    반환 형태({"holdings": [{"symbol": ...}, ...]})만 흉내낸다."""

    def __init__(self, mode):
        self._mode = mode

    async def summary(self):
        if self._mode == "live":
            return {"holdings": [{"account": "kis", "symbol": "005930", "value_usd": 100.0}]}
        return {"holdings": [{"account": "hl", "symbol": "AAPL", "value_usd": 50.0}]}


class _FakeNewsItem:
    def __init__(self, url, headline, summary):
        self.url = url
        self.headline = headline
        self.summary = summary


def _default_collect_result():
    return {"collected": [], "collected_count": 0, "opportunity_queue": [], "opportunity_count": 0}


def _stub_dependencies(monkeypatch, *, news_by_symbol=None, collect_fn=None, fetch_text=None):
    monkeypatch.setattr("jarvis.broker_readonly.aggregator.PortfolioAggregator", _FakeAggregator)
    news_by_symbol = news_by_symbol or {}
    monkeypatch.setattr("api_server.main.get_company_news",
                         lambda ticker, days: news_by_symbol.get(ticker, []))
    monkeypatch.setattr("api_server.jina_reader.fetch_article_text",
                         fetch_text or (lambda url, timeout=10: None))
    monkeypatch.setattr("jarvis.research_workflow.research_feed.collect",
                         collect_fn or (lambda sources=None, **kw: _default_collect_result()))


def test_first_call_registers_agent_and_submits_report(monkeypatch):
    _stub_dependencies(monkeypatch)
    svc = ResearchService()
    svc._news_research_collect()

    from jarvis.research_agents import ResearchAgentEngine
    eng = ResearchAgentEngine()
    assert svc.last_news_collect is not None
    reports = eng.agent_activity("news_research_daily")
    assert reports


def test_throttled_within_24h_window(monkeypatch):
    _stub_dependencies(monkeypatch)
    svc = ResearchService()
    svc._news_research_collect()
    first = svc.last_news_collect
    svc._news_research_collect()
    assert svc.last_news_collect == first


def test_caps_at_three_articles_per_symbol(monkeypatch):
    def items_for(prefix):
        return [_FakeNewsItem(f"https://x.com/{prefix}/{i}", f"h{i}", f"s{i}") for i in range(5)]

    calls = {}

    def fake_collect(sources=None, **kw):
        calls["sources"] = sources
        return _default_collect_result()

    _stub_dependencies(monkeypatch,
                        news_by_symbol={"005930": items_for("kr"), "AAPL": items_for("us")},
                        collect_fn=fake_collect)
    svc = ResearchService()
    svc._news_research_collect()

    assert len(calls["sources"]["news"]) == 6  # 2 symbols x 3 capped, 전부 서로 다른 url


def test_dedups_by_url_across_symbols(monkeypatch):
    shared = _FakeNewsItem("https://x.com/shared", "headline", "summary")
    calls = {}

    def fake_collect(sources=None, **kw):
        calls["sources"] = sources
        return _default_collect_result()

    _stub_dependencies(monkeypatch, news_by_symbol={"005930": [shared], "AAPL": [shared]},
                        collect_fn=fake_collect)
    svc = ResearchService()
    svc._news_research_collect()

    assert len(calls["sources"]["news"]) == 1


def test_falls_back_to_summary_when_jina_fails(monkeypatch):
    item = _FakeNewsItem("https://x.com/a", "headline", "fallback summary")
    calls = {}

    def fake_collect(sources=None, **kw):
        calls["sources"] = sources
        return _default_collect_result()

    _stub_dependencies(monkeypatch, news_by_symbol={"005930": [item]}, collect_fn=fake_collect,
                        fetch_text=lambda url, timeout=10: None)
    svc = ResearchService()
    svc._news_research_collect()

    assert "fallback summary" in calls["sources"]["news"][0]["text"]


def test_uses_jina_body_when_available(monkeypatch):
    item = _FakeNewsItem("https://x.com/a", "headline", "short summary")
    calls = {}

    def fake_collect(sources=None, **kw):
        calls["sources"] = sources
        return _default_collect_result()

    _stub_dependencies(monkeypatch, news_by_symbol={"005930": [item]}, collect_fn=fake_collect,
                        fetch_text=lambda url, timeout=10: "full scraped article body")
    svc = ResearchService()
    svc._news_research_collect()

    assert "full scraped article body" in calls["sources"]["news"][0]["text"]
    assert "short summary" not in calls["sources"]["news"][0]["text"]


def test_exception_is_swallowed(monkeypatch):
    def _boom(mode):
        raise RuntimeError("aggregator boom")
    monkeypatch.setattr("jarvis.broker_readonly.aggregator.PortfolioAggregator", _boom)
    svc = ResearchService()
    svc._news_research_collect()  # 예외로 죽지 않음
    assert svc.last_news_collect is None


def test_body_truncated_to_2000_chars(monkeypatch):
    """Jina body longer than 2000 chars gets truncated."""
    long_body = "x" * 3000
    item = _FakeNewsItem("https://x.com/a", "headline", "summary")
    calls = {}

    def fake_collect(sources=None, **kw):
        calls["sources"] = sources
        return _default_collect_result()

    _stub_dependencies(
        monkeypatch,
        news_by_symbol={"005930": [item]},
        collect_fn=fake_collect,
        fetch_text=lambda url, timeout=10: long_body
    )
    svc = ResearchService()
    svc._news_research_collect()

    text = calls["sources"]["news"][0]["text"]
    body_part = text.split("\n\n")[1]  # Extract body from "headline\n\nbody"
    assert len(body_part) == 2000
    assert body_part == "x" * 2000


def test_one_symbol_exception_does_not_abort_batch(monkeypatch):
    """When get_company_news raises for one symbol, other symbols still get collected."""
    item_good = _FakeNewsItem("https://x.com/good", "headline", "summary")
    calls = {}

    def fake_collect(sources=None, **kw):
        calls["sources"] = sources
        return _default_collect_result()

    def fake_get_company_news(ticker, days):
        if ticker == "005930":
            raise Exception("502 Bad Gateway")
        return [item_good]

    monkeypatch.setattr("jarvis.broker_readonly.aggregator.PortfolioAggregator", _FakeAggregator)
    monkeypatch.setattr("api_server.main.get_company_news", fake_get_company_news)
    monkeypatch.setattr("api_server.jina_reader.fetch_article_text",
                         lambda url, timeout=10: None)
    monkeypatch.setattr("jarvis.research_workflow.research_feed.collect",
                         fake_collect)

    svc = ResearchService()
    svc._news_research_collect()

    # Should have collected from AAPL despite 005930 failing
    assert len(calls["sources"]["news"]) == 1
    assert calls["sources"]["news"][0]["entity"] == "AAPL"


def test_status_includes_last_news_collect(monkeypatch):
    """status() includes last_news_collect field matching last_news_collect attribute."""
    _stub_dependencies(monkeypatch)
    svc = ResearchService()
    svc._news_research_collect()

    status = svc.status()
    assert "last_news_collect" in status
    assert status["last_news_collect"] == svc.last_news_collect
