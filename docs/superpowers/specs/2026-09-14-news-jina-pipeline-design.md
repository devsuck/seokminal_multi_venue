# 뉴스 본문 전문 자동수집 → jarvis 연구 파이프라인 연결

**Status:** approved by user (2026-09-14, AskUserQuestion 3회 — "뉴스 Jina Reader 스크레이핑" →
"AI 리서치 파이프라인에 자동 연결(jarvis)" → "보유종목만" + "ResearchFeedPipeline.collect()").

## Background

`seokminal-dashboard/docs/roadmap.md` 125-129행 "다음 세션 최우선" 3번 — "뉴스 본문 전문(선택):
Jina Reader 스크레이핑". 스펙 한 줄뿐이라 이번 세션에서 조사·질의로 스코프 확정했다.

### 조사 결과

- **기존 뉴스 소비 흐름 없음**: `seokminal-dashboard/lib/api.ts`의 `getMarketNews`/`getCompanyNews`,
  `AlpacaContext`/`getAlpacaContext`는 어떤 `.tsx`도 호출 안 함(죽은 코드, 옛 `ai-trader` 잔재).
  `api_server/console_api.py::/news-intel`, `/market-intel-feed`는 사람이 `q` 파라미터를 수동
  입력해야만 동작 — 자동 수집 경로 0개.
- **jarvis Constitution**: `jarvis/research_workflow/providers.py` — jarvis는 credential-free로
  유지, 벤더 API 직접 호출 안 함. 모든 실API 호출은 Layer A(`api_server/*`, `backends/*`)에서
  하고 raw 데이터를 주입(`Provider.fetch(raw=None)`)받는다. 이 설계는 이번 기능도 그대로 따른다
  — Jina Reader 호출은 `api_server/`에 둔다, jarvis 안에 안 둔다.
- **기존 자동 스케줄 트리거**: 시스템 전체에서 실제로 살아있는 유일한 주기 실행은
  `research/lab/service.py::ResearchService._data_analyst_report()`(292행, 24h 스로틀,
  `_tick()`에서 호출). `jarvis/research_workflow/research_feed.py::ResearchFeedPipeline`은
  스스로 문서에 "실제 주기 실행 없음 — cron/사람이 외부에서 호출"이라 명시, 실제로 프로덕션에서
  호출하는 곳이 자체 모듈 래퍼 말곤 없음(grep 확인) — 이번에 만드는 트리거가 이 파이프라인을
  실제로 처음 가동시키게 된다.
- **`news_pipeline.run()`**: `text`/`entity`만 소비, URL·본문 필드 없음 — 본문을 넣으려면
  헤드라인 대신 `text`에 본문을 실어 보내야 한다.
- **`news_intelligence.analyze_headline()`**: 키워드 매칭 기반 결정적 분류기(LLM 아님) — `text`가
  길어져도 안전, 오히려 긴 본문이 키워드 커버리지를 높여줄 수 있다.
- **보유종목 조회**: `jarvis/broker_readonly/aggregator.py::PortfolioAggregator` — 여러 벤뉴
  포지션을 읽기전용으로 집계하는 기존 클래스, `symbol` 필드 있음. "워치리스트"는 코드베이스에
  별도 리스트로 존재하지 않음 — 이번 스코프는 보유종목만.
- **뉴스 벤더 호출**: `api_server/main.py::get_company_news(ticker, days)` — 기존 Finnhub
  클라이언트, 30분 TTL 캐시, `NewsItem.url` 필드 보유(Jina Reader 입력으로 씀).
- **리포트 저장소**: `jarvis/research_agents/engine.py::ResearchAgentEngine.submit_report()` →
  `jarvis/research_agents/ledger.py`(기존 리포트 원장, `get_report()`로 조회 가능) —
  `_data_analyst_report()`가 이미 이 경로로 저장한다. 새 DB/테이블 안 만들고 재사용.

## Non-Goals

- 워치리스트(보유 외 관심종목) 개념 신설 — 이번 스코프 밖, 필요해지면 별도 스펙.
- 일반 시장뉴스(category=general) 수집 — 종목 연계 없는 뉴스는 이번에 안 함.
- `news_intelligence.py`/`research_trigger.py`/`ResearchFeedPipeline` 내부 로직 변경 — 있는 그대로 재사용.
- 프론트엔드 UI 없음 — 이번 스코프는 백엔드 자동수집→jarvis 연결까지. 대시보드 노출은 별도 스펙.
- `AlpacaContext`/`getAlpacaContext` 죽은 코드 정리 — 이번 기능과 무관, 손 안 댐.
- Jina Reader 유료/키 발급 — 무료 `r.jina.ai` 엔드포인트만 사용, 키 없음.

## Architecture

```
api_server/jina_reader.py                    # 신규
  └─ fetch_article_text(url, timeout=10) -> str | None
       GET https://r.jina.ai/{url}, 실패시 예외 삼키고 None

research/lab/service.py (class ResearchService)
  ├─ self._last_news_collect_ts              # 신규 상태(__init__, _data_analyst_ts와 동형)
  ├─ _news_research_collect()                # 신규, 24h 스로틀
  │    1. PortfolioAggregator로 보유종목 심볼 목록
  │    2. 심볼별 api_server.main.get_company_news(symbol, days=1) 호출 (기존 캐시 재사용)
  │    3. 심볼별 최신 N=3건만, URL 중복 제거
  │    4. 건별 jina_reader.fetch_article_text(item.url) → 실패시 item.summary로 폴백
  │    5. headline_dicts = [{"text": f"{headline}\n\n{body}", "entity": symbol, "url": url}, ...]
  │    6. jarvis.research_workflow.research_feed.collect(sources={"news": headline_dicts})
  │    7. 결과를 _data_analyst_report()와 동일 패턴으로 ResearchAgentEngine.submit_report()에 기록
  └─ _tick()                                  # 기존 358행 부근에 self._news_research_collect() 한 줄 추가
```

### `_news_research_collect()` 상세

```python
def _news_research_collect(self) -> None:
    """24h 스로틀 — 보유종목 뉴스 헤드라인+본문(Jina Reader) 수집 → jarvis
    ResearchFeedPipeline.collect()에 주입. READ ONLY, 신호 아님."""
    if time.time() - self._last_news_collect_ts < 86400:
        return
    self._last_news_collect_ts = self._touch("last_news_collect_ts")
    try:
        from jarvis.broker_readonly.aggregator import PortfolioAggregator
        from api_server.main import get_company_news
        from api_server.jina_reader import fetch_article_text
        from jarvis.research_workflow.research_feed import collect as collect_feed
        from jarvis.research_agents import ResearchAgentEngine
        from jarvis.research_agents.models import AGENT_DATA_ANALYST, CAP_ANALYZE
        import datetime as _dt

        symbols = sorted({h["symbol"] for h in PortfolioAggregator().holdings()})
        headline_dicts, seen_urls = [], set()
        for symbol in symbols:
            items = get_company_news(ticker=symbol, days=1)[:3]
            for item in items:
                if item.url in seen_urls:
                    continue
                seen_urls.add(item.url)
                body = fetch_article_text(item.url) or item.summary
                headline_dicts.append({
                    "text": f"{item.headline}\n\n{body}", "entity": symbol, "url": item.url,
                })

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
                           summary=f"symbols={len(symbols)}, collected={result['collected_count']}, "
                                   f"opportunities={result['opportunity_count']}",
                           now=now, commit=True)
        eng.complete_task(t.task_id, now, commit=True)
    except Exception:  # noqa: BLE001
        pass
```

`_data_analyst_report()`와 동일하게 예외를 통째로 삼킨다 — 뉴스 벤더 장애/Jina 장애가 다른 틱
작업을 막으면 안 됨(sibling 메서드들과 동일 계약).

### `PortfolioAggregator.holdings()` 정확한 시그니처

계획 단계에서 `jarvis/broker_readonly/aggregator.py` 전체를 읽어 실제 반환 형태(메서드명,
`{"symbol": ...}` dict 리스트인지 다른 형태인지)를 확정한다 — 이번 스펙 조사에서는 58행
`holdings.append({"account": name, "symbol": pos["symbol"], ...})` 패턴만 확인했다.

## Error Handling

- Jina Reader 실패(타임아웃/4xx/paywall/네트워크): `fetch_article_text`가 `None` 반환, 호출부는
  `item.summary`로 폴백 — 전체 수집이 중단되지 않는다.
- Finnhub 호출 실패: 기존 `get_company_news` 자체 계약 그대로(빈 리스트 또는 예외) — 새 방어
  코드 추가 안 함, 바깥 `try/except`가 흡수.
- `PortfolioAggregator` 실패(벤뉴 API 다운 등): 바깥 `try/except`가 흡수, 그날 뉴스 수집 스킵,
  다음날 재시도(스로틀이 24h 후 자연 재실행).
- 심볼 0개(포지션 없음): `headline_dicts`가 빈 리스트 → `collect_feed`가 빈 결과 반환 →
  정상 진행(에러 아님).

## Testing

- `tests/test_jina_reader.py` (신규): `fetch_article_text` — 성공(mock 200 응답 본문 반환),
  실패(mock 타임아웃/4xx → None), URL 인코딩 케이스.
- `tests/test_lab_service.py` (또는 기존 서비스 테스트 파일에 추가): `_news_research_collect()` —
  `PortfolioAggregator`/`get_company_news`/`fetch_article_text`/`collect_feed`/
  `ResearchAgentEngine` mock, (1) 24h 이내 재호출시 스킵되는지, (2) 심볼별 N=3건 캡 확인,
  (3) URL 중복 제거 확인, (4) `submit_report`가 실제로 호출되는지, (5) 내부 예외 발생시
  `_tick()` 전체가 죽지 않는지(예외 흡수) 확인.

## Migration

신규 기능, 기존 동작 변경 없음(모든 신규 코드 경로, `_tick()`에 메서드 호출 한 줄 추가뿐) —
별도 배치 재현/마이그레이션 검증 불필요. 구현 완료 후 로컬에서 `_news_research_collect()` 1회
수동 호출해 `get_report()`로 리포트가 정상 기록되는지, Jina Reader 실제 호출이 rate limit 없이
성공하는지 스모크 확인 후 커밋.
