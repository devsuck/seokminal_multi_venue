# 뉴스 Jina Reader → jarvis 자동 연결 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 보유종목(live+paper) Finnhub 뉴스 헤드라인을 Jina Reader로 본문까지 스크레이핑해 24h
스로틀 자동 트리거로 jarvis `ResearchFeedPipeline.collect()`에 주입, 기존 리포트 원장에 기록한다.

**Architecture:** `api_server/jina_reader.py`(신규, URL→본문 텍스트 fetcher)와
`research/lab/service.py::ResearchService._news_research_collect()`(신규, 24h 스로틀 메서드,
`_data_analyst_report()`와 동형 패턴)를 만들고 `_tick()`에 한 줄 연결한다. 벤더 API 호출은
전부 `api_server`에 머물고(jarvis credential-free 원칙), jarvis 쪽은 이미 있는
`ResearchFeedPipeline.collect(sources={"news": [...]})`와 `ResearchAgentEngine.submit_report()`를
그대로 재사용한다 — jarvis 내부 로직은 한 줄도 안 바뀐다.

**Tech Stack:** Python 3.14, FastAPI(`api_server`), `requests`(HTTP), `pytest`(`asyncio_mode="auto"`
— `@pytest.mark.asyncio` 절대 금지), `unittest.mock`(monkeypatch/patch).

**Spec:** `docs/superpowers/specs/2026-09-14-news-jina-pipeline-design.md`

## Global Constraints

- jarvis는 credential-free 유지 — 벤더 HTTP 호출(Finnhub, Jina Reader)은 전부 `api_server/`에
  둔다, `jarvis/` 패키지 안에 새 벤더 호출 코드를 넣지 않는다.
- `jarvis/research_workflow/news_pipeline.py`, `news_intelligence.py`, `research_feed.py`,
  `research_trigger.py` 내부 로직 변경 없음 — 있는 그대로 재사용.
- 새 DB/테이블/저장소 생성 금지 — 리포트는 기존 `jarvis/research_agents/ledger.py` 경로로만 기록.
- 워치리스트(보유 외 관심종목) 개념 신설 없음 — 대상은 `PortfolioAggregator`가 돌려주는
  live+paper 보유종목 심볼뿐.
- 종목당 뉴스 최대 3건(N=3), URL 중복 제거 — Jina Reader 호출량 제한.
- 예외는 전부 흡수(`except Exception: pass`) — 다른 `_tick()` 작업을 막지 않는다. 기존
  `_data_analyst_report()`/`_disk_alert()`와 동일 계약.
- Python 실행 경로: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3`. 테스트:
  `python3 -m pytest tests/ -q`.
- `asyncio_mode="auto"` — 비동기 테스트 함수에 `@pytest.mark.asyncio` 데코레이터 달지 않는다.

---

## Task 1: `api_server/jina_reader.py` — Jina Reader 본문 fetcher

**Files:**
- Create: `api_server/jina_reader.py`
- Test: `tests/test_jina_reader.py`

**Interfaces:**
- Produces: `fetch_article_text(url: str, timeout: int = 10) -> str | None` — 성공시 기사 본문
  텍스트(Jina Reader가 마크다운으로 변환), 실패(타임아웃/HTTP 에러/빈 본문)시 `None`. 이 시그니처를
  Task 2가 그대로 가져다 쓴다.

`api_server/main.py`의 기존 Finnhub 호출부(`/news/*` 라우트, 5010행 부근)가 `requests.get(...,
timeout=N)` + `resp.raise_for_status()` 패턴을 쓴다 — 이 패턴을 그대로 따른다(새 HTTP 라이브러리
안 씀). Jina Reader는 `https://r.jina.ai/{원본URL}`에 GET 한 번 보내면 본문을 텍스트로 반환한다
(무료, API 키 불필요, URL은 퍼센트 인코딩 없이 그대로 이어붙인다 — Jina의 실제 계약).

- [ ] **Step 1: Write the failing tests**

`tests/test_jina_reader.py`:

```python
"""fetch_article_text — Jina Reader(r.jina.ai) 무료 URL→본문텍스트 변환. 실패시 None,
호출부가 summary로 폴백."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests

from api_server.jina_reader import fetch_article_text


def test_fetch_article_text_returns_body_on_success():
    mock_resp = MagicMock()
    mock_resp.text = "# Headline\n\nArticle body text."
    mock_resp.raise_for_status = MagicMock()
    with patch("api_server.jina_reader.requests.get", return_value=mock_resp) as mock_get:
        result = fetch_article_text("https://example.com/article")

    assert result == "# Headline\n\nArticle body text."
    mock_get.assert_called_once_with(
        "https://r.jina.ai/https://example.com/article", timeout=10
    )


def test_fetch_article_text_returns_none_on_http_error():
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = Exception("404 Client Error")
    with patch("api_server.jina_reader.requests.get", return_value=mock_resp):
        assert fetch_article_text("https://example.com/missing") is None


def test_fetch_article_text_returns_none_on_timeout():
    with patch("api_server.jina_reader.requests.get", side_effect=requests.Timeout("timed out")):
        assert fetch_article_text("https://example.com/slow") is None


def test_fetch_article_text_returns_none_on_empty_body():
    mock_resp = MagicMock()
    mock_resp.text = "   "
    mock_resp.raise_for_status = MagicMock()
    with patch("api_server.jina_reader.requests.get", return_value=mock_resp):
        assert fetch_article_text("https://example.com/empty") is None


def test_fetch_article_text_respects_custom_timeout():
    mock_resp = MagicMock()
    mock_resp.text = "body"
    mock_resp.raise_for_status = MagicMock()
    with patch("api_server.jina_reader.requests.get", return_value=mock_resp) as mock_get:
        fetch_article_text("https://example.com/article", timeout=3)

    mock_get.assert_called_once_with("https://r.jina.ai/https://example.com/article", timeout=3)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_jina_reader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api_server.jina_reader'`

- [ ] **Step 3: Write minimal implementation**

`api_server/jina_reader.py`:

```python
"""Jina Reader(r.jina.ai) 무료 URL→본문텍스트 fetcher — Layer A 벤더 호출.
jarvis는 credential-free라 여기(api_server)에만 존재, jarvis 안에 안 둔다."""
from __future__ import annotations

import requests

_JINA_BASE = "https://r.jina.ai/"


def fetch_article_text(url: str, timeout: int = 10) -> str | None:
    """URL 기사 본문을 Jina Reader로 마크다운 텍스트로 가져온다. 키 불필요.
    실패(타임아웃/HTTP 에러/네트워크 오류/빈 본문)시 None — 호출부가 summary로 폴백."""
    try:
        resp = requests.get(f"{_JINA_BASE}{url}", timeout=timeout)
        resp.raise_for_status()
        text = resp.text.strip()
        return text or None
    except Exception:  # noqa: BLE001
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_jina_reader.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add api_server/jina_reader.py tests/test_jina_reader.py
git commit -m "feat: add Jina Reader article-text fetcher (api_server layer)"
```

---

## Task 2: `ResearchService._news_research_collect()` — 24h 스로틀 수집+주입

**Files:**
- Modify: `research/lab/service.py:29-70` (`__init__` 상태 추가), 새 메서드 추가(292행
  `_data_analyst_report()` 바로 아래 권장), `_tick()`(352-361행)에 호출 한 줄 추가
- Test: `tests/test_lab_service_news_research_collect.py`

**Interfaces:**
- Consumes: Task 1의 `api_server.jina_reader.fetch_article_text(url: str, timeout: int = 10) ->
  str | None`. 기존 `jarvis.broker_readonly.aggregator.PortfolioAggregator(mode: str)` —
  `mode`는 `"live"` 또는 `"paper"`, `await PortfolioAggregator(mode).summary()` →
  `{"holdings": [{"account": str, "symbol": str, "value_usd": float}, ...], ...}`. 기존
  `api_server.main.get_company_news(ticker: str, days: int) -> list[NewsItem]`(`NewsItem`은
  `.url`/`.headline`/`.summary` 속성). 기존
  `jarvis.research_workflow.research_feed.collect(sources: dict | None = None, *,
  interval_seconds=900, max_retries=2, seen=None, assistant=None) -> dict` — 반환 dict에
  `"collected_count"`/`"opportunity_count"` 키 있음. 기존
  `jarvis.research_agents.ResearchAgentEngine` — `register_agent`, `create_profile`,
  `create_task`, `assign_task`, `start_task`, `submit_report`, `complete_task`(전부
  `research/lab/service.py:301-327`의 `_data_analyst_report()`가 쓰는 것과 동일 시그니처).
- Produces: `ResearchService._news_research_collect() -> None`(공개 상태:
  `self.last_news_collect: str | None`). `_tick()`이 이 메서드를 호출.

`PortfolioAggregator.summary()`는 `async def`다(`jarvis/broker_readonly/aggregator.py:43`).
`ResearchService`는 별도 `threading.Thread`(`_loop`, 이 파일 100-115행)에서 동기로 돌기 때문에
실행 중인 이벤트루프가 없다 — `asyncio.run(...)`으로 안전하게 호출할 수 있다(이미
`jarvis/broker_readonly/snapshot_job.py`가 별도 루프에서 이 클래스를 이렇게 쓴다, 참고만).

- [ ] **Step 1: Write the failing tests**

`tests/test_lab_service_news_research_collect.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_lab_service_news_research_collect.py -v`
Expected: FAIL with `AttributeError: 'ResearchService' object has no attribute '_news_research_collect'`

- [ ] **Step 3: Write minimal implementation**

`research/lab/service.py` — `__init__`(69행 부근, `self._last_disk_alert_ts = ...` 바로 위/아래
아무 데나) 에 상태 2줄 추가:

```python
        self._last_news_collect_ts = _persisted.get("last_news_collect_ts", 0.0)
        self.last_news_collect: str | None = None
```

`_data_analyst_report()`(292-330행) 바로 아래에 새 메서드 추가:

```python
    def _news_research_collect(self) -> None:
        """24h 스로틀 — 보유종목(live+paper) 뉴스 헤드라인+본문(Jina Reader)을 수집해
        jarvis ResearchFeedPipeline.collect()에 주입 후 리포트 제출. READ ONLY, 신호 아님.
        벤더 호출(Finnhub·Jina)은 전부 api_server 쪽 — jarvis는 credential-free 유지."""
        if time.time() - self._last_news_collect_ts < 86400:
            return
        self._last_news_collect_ts = self._touch("last_news_collect_ts")
        try:
            import asyncio
            import datetime as _dt

            from api_server.jina_reader import fetch_article_text
            from api_server.main import get_company_news
            from jarvis.broker_readonly.aggregator import PortfolioAggregator
            from jarvis.research_agents import ResearchAgentEngine
            from jarvis.research_agents.models import AGENT_DATA_ANALYST, CAP_ANALYZE
            from jarvis.research_workflow.research_feed import collect as collect_feed

            symbols: set[str] = set()
            for mode in ("live", "paper"):
                summary = asyncio.run(PortfolioAggregator(mode).summary())
                symbols.update(h["symbol"] for h in summary.get("holdings", []))

            headline_dicts: list[dict] = []
            seen_urls: set[str] = set()
            for symbol in sorted(symbols):
                for item in get_company_news(ticker=symbol, days=1)[:3]:
                    if item.url in seen_urls:
                        continue
                    seen_urls.add(item.url)
                    body = fetch_article_text(item.url) or item.summary
                    headline_dicts.append({"text": f"{item.headline}\n\n{body}",
                                            "entity": symbol, "url": item.url})

            result = collect_feed(sources={"news": headline_dicts})

            today = _dt.date.today().isoformat()
            now = _now()
            agent = "news_research_daily"
            eng = ResearchAgentEngine()
            eng.register_agent(agent, AGENT_DATA_ANALYST, "일일 보유종목 뉴스 수집", now, commit=True)
            eng.create_profile(agent, ["READ", "ANALYZE", "REPORT"], now=now, commit=True)
            target = f"news:{today}"
            t = eng.create_task(agent, CAP_ANALYZE, target, "일일 뉴스 수집+분석", now, commit=True)
            eng.assign_task(t.task_id, now, commit=True)
            eng.start_task(t.task_id, now, commit=True)
            eng.submit_report(agent, t.task_id, f"daily:{today}", [result],
                               summary=f"symbols={len(symbols)}, "
                                       f"collected={result['collected_count']}, "
                                       f"opportunities={result['opportunity_count']}",
                               now=now, commit=True)
            eng.complete_task(t.task_id, now, commit=True)
            self.last_news_collect = now
        except Exception:  # noqa: BLE001
            pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_lab_service_news_research_collect.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add research/lab/service.py tests/test_lab_service_news_research_collect.py
git commit -m "feat: add 24h-throttled news research collect (holdings -> Jina Reader -> jarvis feed)"
```

---

## Task 3: `_tick()` 연결

**Files:**
- Modify: `research/lab/service.py:352-361`

**Interfaces:**
- Consumes: Task 2의 `ResearchService._news_research_collect() -> None`.
- Produces: 없음(배선만).

`_data_analyst_report()`/`_disk_alert()`가 이미 `_tick()`에 한 줄씩 등록돼 있는 것과 동일한
방식 — 이 두 메서드는 각자 자체 스로틀(24h/6h)을 갖고 있어 `_tick()`(180초 간격 루프) 쪽엔
아무 조건 없이 매번 호출만 한다. 이 저장소 관례상 `_tick()` 배선 자체에 대한 별도 단위테스트는
없다(`_data_analyst_report`/`_disk_alert`도 마찬가지) — 메서드 자체 스로틀 테스트(Task 2)가
실질적 커버리지고, `_tick()` 호출은 코드 리뷰로 확인한다.

- [ ] **Step 1: Modify `_tick()`**

`research/lab/service.py`의 `_tick()`(352-361행)을:

```python
    def _tick(self) -> None:
        self.ticks += 1
        self._pull_krx_daily()
        self._refresh_buyback()
        self._autoresearch_batch()
        self._warm_edge()
        self._execution_check()
        self._warm_tsmom()
        self._data_analyst_report()
        self._disk_alert()
```

다음으로 바꾼다(마지막 줄 `self._disk_alert()` 뒤에 한 줄 추가):

```python
    def _tick(self) -> None:
        self.ticks += 1
        self._pull_krx_daily()
        self._refresh_buyback()
        self._autoresearch_batch()
        self._warm_edge()
        self._execution_check()
        self._warm_tsmom()
        self._data_analyst_report()
        self._disk_alert()
        self._news_research_collect()
```

- [ ] **Step 2: Run full test suite**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/ -q`
Expected: 전건 PASS, 회귀 없음(직전 베이스라인 기준 +12건: Task 1의 5건 + Task 2의 7건).

- [ ] **Step 3: Commit**

```bash
git add research/lab/service.py
git commit -m "feat: wire _news_research_collect into ResearchService tick loop"
```

---

## Final Manual Smoke Test (자동화 테스트 아님, 커밋 전 마지막 확인)

전 태스크 커밋 후, 로컬에서 1회 수동 확인:

```bash
cd /Users/seokhun/seokminal/seokminal-multi-venue
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -c "
from research.lab.service import ResearchService
svc = ResearchService()
svc._last_news_collect_ts = 0.0  # 스로틀 무시하고 강제 1회 실행
svc._news_research_collect()
print('last_news_collect:', svc.last_news_collect)
"
```

- `last_news_collect`가 `None`이 아니면: 보유종목 조회 → Finnhub 뉴스 → Jina Reader 본문 →
  jarvis 파이프라인 → 리포트 제출까지 실제 네트워크로 성공했다는 뜻. `FINNHUB_API_KEY` 환경변수가
  세팅돼 있어야 한다(안 되어 있으면 `_finnhub_key()`가 503을 던지고 바깥 `except`가 삼켜서
  `last_news_collect`가 `None`으로 남는다 — 이 경우도 "예외 안 죽음" 자체는 정상, 실환경
  검증만 안 된 것).
- 보유종목이 0건(live/paper 둘 다 빈 계좌)이면 `headline_dicts`가 빈 리스트라 정상적으로
  `last_news_collect`가 채워진다 — 이 자체는 실패가 아니다, 포지션 있는 계좌로 재확인 권장.
- `jarvis.research_agents.ledger.get_report(...)` 또는
  `ResearchAgentEngine().agent_activity("news_research_daily")`로 실제 리포트가 기록됐는지
  확인 후에만 이 기능을 "완료"로 progress.md에 기록한다.
