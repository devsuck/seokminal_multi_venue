# Progress Log

> 이 파일은 세션 간 작업 맥락을 이어주는 용도입니다.
> 새 세션 시작 시: `@docs/progress.md @CLAUDE.md 읽고 이어서 작업해줘`

## 현재 상태 (마지막 업데이트: 2026-07-11 오더플로우 멀티벤뉴 검증)

### 완료된 작업

**Phase 1 — KIS 데이터/주문 (2026-06-21 ~ 06-22)**
- KIS 일봉 데이터 수집 → `ParquetDataCatalog` 저장 (`data_ingestion.py`, `backends/kis/`)
- KIS WebSocket 실시간 체결 스트리밍 (`live_trade_stream.py`, `backends/kis/ws_client.py`)
- KIS 모의투자 주문 실행 (매수/매도/취소/조회) (`backends/kis/order_client.py`)

**Phase 2 — IB 데이터/주문 (2026-06-22 ~ 06-24)**
- IB 실시간 체결 스트리밍 (`live_trade_stream_ib.py`, `backends/ib/client.py`)
- IB 페이퍼트레이딩 주문 실행 (`backends/ib/order_client.py`)
- IB 히스토리컬 일봉 수집 → catalog (`data_ingestion_ib.py`)

**Phase 3 — 조건 엔진 / 전략 스포너 (2026-06-23)**
- JSON 조건 파서 + 평가기 (AND/OR 조합) (`condition_engine/`)
- 조건 충족 시 전략 동적 스폰 (`strategy_spawner/`)

**Phase 4 — 백테스트 / 분석 (2026-06-24)**
- NautilusTrader BacktestEngine 래퍼 (`backtest_runner/`)
- 종목 간 수익률 상관관계 행렬 (`correlation_analysis/`)

**Phase 5 — 대시보드 API + 베타 분석 (2026-06-25)**
- FastAPI 서버: `/bars`, `/backtest`, `/correlation` 엔드포인트 (`api_server/main.py`)
- KOSPI 인덱스 + SPY ETF catalog 수집 (`data_ingestion_kospi.py`)
- `beta_for_pair()` 함수 구현 (`beta_analysis/beta.py`) — beta, correlation 계산

### 완료된 작업 (continued)

**Phase 9 — 매크로 지표 + 기업 재무정보 (2026-06-25 ~ 06-26)**
- FRED API 연동 (`fred/client.py`) — 14개 미국 거시지표 (`/fred/catalog`, `/fred/series`)
- ECOS API 연동 (`ecos/client.py`) — 14개 한국 거시지표 (`/ecos/catalog`, `/ecos/series`)
- 대시보드 US-MACRO / KR-MACRO 탭 분리 (`app/quant/page.tsx`)
- KIS 토큰 캐시 (disk) 구현 (`backends/kis/auth.py`) — rate limit 우회
- 통합 수집 CLI (`ingest.py`) — domestic/ib/index/batch/crno-search 서브커맨드
- 금융위원회 기업재무정보 API (`corp_finance/client.py`, `/corp-finance/summary` 엔드포인트)
  - 검증된 crno 8개: 삼성전자/현대차/기아/LG전자/LG화학/삼성SDI/NAVER/KB금융
  - `ingest.py crno-search` — 매출액 기준 FSC DB에서 crno 자동 검색
  - Quant > FACTOR 탭에 기업재무 패널 추가 (다년도 테이블 + 바 차트)

**Phase 10 — 퀀트 지표 고도화 + 외부 데이터 소스 확장 (2026-06-26)**
- 백테스트 응답에 Sortino/Volatility/WinRate/P-L Ratio/AvgWin/AvgLoss 추가 (`backtest_runner/runner.py`)
- 몬테카를로 시뮬레이션 (`monte_carlo/simulator.py`) + `/monte-carlo` 엔드포인트
- 레짐 필터 (`regime_filter/detector.py`) + `/regime` 엔드포인트
- 금융위원회 crno 기반 기업재무 API 구현 (`corp_finance/client.py`, `/corp-finance/summary`)
- KRX OpenAPI 클라이언트 (`krx/client.py`) — 구독 신청 후 사용 가능
- SEC EDGAR 클라이언트 (`sec_edgar/client.py`) — 무료, 키 불필요
  - `/edgar/summary`: 미국 기업 연도별 재무제표
  - `/edgar/concept`: XBRL concept 시계열
- 대시보드 대규모 개편:
  - backtest 페이지: "empty state" UI (항상 표시, 빈 값 → RUN 시 채워짐)
  - quant 페이지 탭 추가: MONTE CARLO, REGIME
  - US-MACRO 탭 하단에 SEC EDGAR 재무제표 패널 추가
  - `pyproject.toml`에 `krx*`, `sec_edgar*` 추가

### 진행 중 / 다음 할 일

- [ ] SK하이닉스 crno 미확인 (FSC DB: `python ingest.py crno-search --sale-trillion 44.6 --year 2022 --tolerance 2`)
- [ ] 신한지주, POSCO홀딩스 crno 추가

### 알아둘 것 / 블로커
- `CLAUDE_CODE_DISABLE_1M_CONTEXT=1` 셸 프로필에 영구 설정됨
- API 서버는 `cd nautilus-multi-venue && uvicorn api_server.main:app --reload` 실행
- CORS: `localhost:3000`만 허용
- KRX API: `apikey` 헤더 사용, `data-dbg.krx.co.kr`은 테스트 서버(키 미승인시 401), 프로덕션은 포털 승인 후 별도 URL
- SEC EDGAR: `User-Agent: "seokminal research bot"` + `From: tjrgns97502@naver.com` 헤더 필수
- SEC EDGAR rate limit: 10 req/s → client에 0.11s throttle 내장됨
- KSD API: `DATA_GO_KR_API_KEY` 사용 (별도 키 없음). 실제 엔드포인트:
  - 배당: `1160100/GetStocDiviInfoService_V2/getDiviInfo_V2`
  - 대차순위: `1160100/GetStocLendBorrInfoService_V2/getStLendAndBorrItemRank_V2`
  - 권리일정: `1160100/GetStocRighScheService_V2/getRighExerReasSche_V2`
  - 발행정보: `1160100/GetStocIssuInfoService_V3/getStocIssuInfo_V3`
  - ⚠️ 금융위원회 KSD 서비스는 `/service/` prefix 없음 (기업재무는 `/service/` 있음)
- KSD 대차순위: `basDt`로 특정 날짜 조회. 최근 영업일 데이터만 존재 (공휴일/주말 없음)

---

## 2026-07-08: Polymarket 실시간 틱 수집기 (Phase 1 — 데이터 수집만)

### 완료된 작업
- Polymarket CLOB WSS 구독 기반 틱 수집기 신규 트랙 (`polymarket_arb` REST 폴링과 별개)
- 브레인스토밍 → 스펙(`docs/superpowers/specs/2026-07-08-polymarket-tick-collector-design.md`) → 계획(`docs/superpowers/plans/2026-07-08-polymarket-tick-collector.md`) → subagent-driven 구현, 4개 태스크 전부 태스크리뷰+최종 브랜치리뷰 통과
- 스코프: 라이브 스포츠/속보 마켓 확률 틱을 WSS로 받아 jsonl 적재만 함. 전략/판정 로직 없음. `api_server/polymarket_bot.py`(프로덕션 페이퍼봇) 손대지 않음.
- 스펙 대비 2개 의도적 이탈: (1) news 거래량 급증 기준 드롭 — 지원 필드 없음, (2) 명시적 WSS unsubscribe 대신 5분 주기 전체 재연결로 대체 — 공개 문서에 unsubscribe 포맷 없음
- 최종 브랜치리뷰에서 unattended 운영 리스크 2건 발견 후 수정: WSS clean-close 시 백오프 없이 즉시 재연결하던 핫루프 버그, `game_start_time` naive timestamp 하나가 전체 재선정 사이클을 죽이던 버그

### 변경된 파일
- `polymarket/client.py` — `_map_market()`에 `sports_market_type`, `game_start_time` 필드 추가
- `research/polymarket_tick/market_selector.py` (신규) — sports/news 분류 순수함수
- `research/polymarket_tick/ws_collector.py` (신규) — CLOB WSS 클라이언트 + 틱 파싱 (`backends/kis/ws_client.py` 패턴 재사용)
- `research/run_polymarket_tick_collect.py` (신규) — 무한루프 진입점, 5분 재선정 + WSS 스트리밍 + 지수백오프
- `pyproject.toml` — `websockets>=15.0` 의존성 추가
- 테스트 4개 신규 파일, 커밋 히스토리: `ec7d30d..eeb1cd8` (main 직접 커밋)

### 다음 할 일
- 몇 주 데이터 쌓인 뒤 모멘텀/오버리액션 가설 검증 spec→plan 별도 사이클 (그 전까진 그냥 방치, 건드릴 필요 없음)

### 막힌 부분/결정사항
- 없음 — 전 과정 클린 (task reviewer 1회 fix cycle, 최종 브랜치 reviewer 1회 fix cycle, 이후 승인)
- tmux 세션 `polymarket-tick`으로 2026-07-08 04:39 KST부터 상시 실행 시작 (`polymarket-arb`와 같은 머신, 별도 세션). 첫 SSL 인증서 에러(`CERTIFICATE_VERIFY_FAILED`, python.org 빌드가 시스템 CA 미설치) → `/Applications/Python 3.14/Install Certificates.command` 실행으로 해결 — 코드 버그 아니고 이 macOS의 환경설정 문제. 재시작 후 정상 동작 확인 (뉴스 마켓 틱 20초에 404개 적재 확인).

---

## 2026-07-08 (세션2): 리소스 조사 — 코드 변경 없음

### 완료된 작업
- "플랫폼 느리다" 리포트 → PID 85156 조사. 처음엔 autoresearch 좀비 워커로 오판(status.json 타임스탬프만 보고 성급히 결론) → 재확인 결과 **오판이었음**: 85156 부모가 `uvicorn api_server.main:app --reload`(PID 39399) — reload 모드가 spawn하는 진짜 API 서버 프로세스 그 자체. `sample`로 콜스택 찍어보니 현재 idle(kevent 대기), 누적 CPU도 10분/경과 1h24m 수준 — 좀비도 스핀도 아님. RAM 1.29GB는 nautilus_trader+pandas+numpy 로드된 정상 베이스라인. **kill 안 함, 코드 수정 불필요** — 죽이면 백엔드 API 끊김.
- 발열 원인 추가 조사: 이 프로젝트 밖 오래된 dev 서버들(`seoka`, `web3-tcg` web/server, `netlify dev`) 떠있었지만 전부 CPU 0%/RAM 미미 — 발열 무관. 크롬/VSCode/Claude.app은 정상 사용량.
- 폴리마켓 틱 데이터 현황 체크: tmux `polymarket-tick` 살아있음, 04:39~05:50 약 1h10m 누적 — `2026-07-08.jsonl` 54MB, 124,804줄 (news 125,190 / sports 266). 검증 돌리기엔 한참 부족, 계속 방치.

### 변경된 파일
- 없음 (조사만, 코드 수정 없음)

### 다음 할 일
- 없음 (기존 "몇 주 데이터 쌓인 뒤 검증" 계획 그대로 유지)

### 막힌 부분/결정사항
- PID 85156은 앞으로도 uvicorn 서버 켜져있는 한 정상적으로 계속 떠있음 — "왜 안 꺼지냐"는 질문 다시 나오면 이 항목 참고, 재조사 불필요.

---

## 2026-07-08 (세션3): KR 밸류/퀄리티 팩터 + 종합점수, autoresearch 배치 편입

### 완료된 작업
- 기존 사전등록 3팩터(size/amihud/turnover, 전부 CANDIDATE) 배치에 PER/PBR/ROIC/F-Score 4개 추가 검증 — 표본 22~27개월(DART 재무제표 PIT 공시시차 반영, `_fy_for_date`)로 전부 REJECT_BH (PBR은 pct=0.67로 오히려 반대 방향, 노이즈 아니고 실제 반대신호 — 성장주 장세 반영으로 판단)
- "개별 지표 말고 결합해서 판단보조로 써야지" 피드백 반영 → `kr_value_quality_composite`(PER·PBR·ROIC·F-Score 부호맞춘 월내 z-평균) 신규 사전등록. 개별로는 안 보이던 신호가 결합하니 pct=96.0·p=0.0432로 **BH-FDR 생존**. 단 비용 스트레스(160bps)에서 마이너스로 뒤집혀 redteam `cost_stress` 탈락 → REJECT_REDTEAM
- 중간에 "구조 CANDIDATE(size/turnover) 롱 레그 내부 2차 밸류틸트" 시도했다가 폐기: size 레그(소형주)는 DART 펀더멘털 캐시(대형주 위주)와 교집합 0으로 상시 UNDERPOWERED, turnover 레그는 22개월 확보됐지만 pct=18.67로 반대신호 — 사용자가 "소형주 안 건드려도 됨, 대형주 급락 시 가치 판단보조가 원래 목적"이라 정정, 관련 코드/테스트 전부 되돌림(커밋에 안 남음)
- 최종 결론: composite는 대형주(펀더멘털 커버리지 유니버스) 급락 시 "펀더멘털 대비 진짜 싼지" 확인하는 **판단보조 필터**로만 근거 있음. 단독 자동매매 트리거로 쓸 근거 없음(비용 못 버팀)

### 변경된 파일
- `research/autoresearch/engines_factor.py` — PER/PBR/ROIC/F-Score 4팩터 + composite 8번째 팩터, `_fy_for_date` PIT 로직, `compute_factors` 연동
- `research/autoresearch/engine.py` — `collect_candidates()`에 `load_fundamentals` 배선
- `research/data/dart_financials.py`(신규), `research/data/valuation_factors.py`(신규) — DART 재무제표 PIT 수집 + PER/PBR/ROIC/F-Score/PSR/EV-EBIT/Piotroski F-Score 계산. 전자는 corp_code 매핑에 `curl -m` 필수(requests 스트리밍은 대용량 XML에서 timeout 안 먹힘)
- `tests/test_engines_factor.py` — 합성 데이터 수학 검증 9개(각 팩터 planted-effect 탐지 + 무효과 근처 + fund 없으면 None)
- 커밋: `c5c0b19` (main 직접). 이 세션에서 건드린 것 중 무관한 변경(`api_server/graph_api.py`, `jarvis/_state/*`, `research/data/polymarket_tick/`)은 커밋에서 제외 — 다른 트랙 것이라 그대로 둠(아직 uncommitted 상태로 남아있음, 다음 세션에서 확인 필요할 수도)

### 다음 할 일
- 없음(이 트랙은 여기서 정리). 재시도하려면 DART 캐시를 소형주까지 확장해야 함 — 별도 데이터 수집 작업, 지금 계획 없음
- `git status`에 남아있는 무관 변경(`api_server/graph_api.py`, `docs 외 jarvis/_state/*`)은 이 세션에서 건드린 적 없음 — 다음 세션에서 뭔지 확인 필요하면 참고

### 막힌 부분/결정사항
- composite REJECT_REDTEAM(cost_stress) 사유는 재검토 대상 아님 — "왜 이거 안 씀" 질문 다시 나오면 이 항목 참고
- size_value_tilt/turnover_value_tilt는 시도했다가 방향 잘못 짚어서 폐기한 거라 재시도 안 함(코드에 흔적 없음, 이 로그가 유일한 기록)

---

## 2026-07-08 (세션4): ICT 조합 백테스트 페이지 + 프리셋/검색/타임프레임 확장
> ⚠️ 이 세션의 "프리셋(기각확정 재현)" 별도 탭 구조는 세션5에서 폐기됨 — 아래 내용은 히스토리 기록용, 현재 UI와 다름. 최신 상태는 세션5 참고.

### 완료된 작업
- ICT 프리미티브(킬존·sweep·FVG·OB·BOS-CHoCH) 자유조합 AND백테스트 신규 페이지 `/ict` — 매칭random 대비 net/percentile/p-value/WF1·WF2 참고통계, 전부 REJECT 확정된 표준조합(experiment_registry) 경고 배너 상시 노출
- "reject된 것도 실험" 요청 반영 — `research/ict/models_2024.MODELS` 6개 고정모델(전부 REJECT 확정)을 "프리셋(기각확정 재현)" 탭으로 노출, 모델 로직/파라미터는 원본 그대로 다른 심볼·기간에 재현만 가능(재검증 아님 명시)
- 심볼 선택 plain `<select>` → 검색형 콤보박스(타이핑 필터, 라이브 크립토 태그 표시)
- 타임프레임 1m/5m/15m/1h/4h/1d로 확장. 디스크 미보유분은 3단 폴백: ①직접저장 ②크립토(LIQUID_PERPS 25종)는 HL API 라이브조회+캐시(모든 tf) ③주식/ETF는 15m 원본→1h/4h만 pandas 리샘플 합성(1m/5m은 소스 없음, IB TWS 필요해서 미지원 — 에러 메시지로 명확히 안내)
- Nautilus 카탈로그(`/bars` 등)가 1-DAY 고정이라 킬존(시간대) 프리미티브에 못 쓴다는 걸 이전 세션에 확인 → `research/data/intraday_store.py`(별도 평범 parquet)로 라우팅, 재확인 완료

### 변경된 파일
- `research/ict/combinator.py` — `evaluate_preset()` 신규(+공통 통계 꼬리부 `_stats_vs_random()`로 `evaluate_combo()`와 중복 제거), `PRESET_IDS` 추가
- `api_server/router_ict.py` — `/ict/presets` GET 신규, `/ict/backtest`에 `preset` 필드(지정 시 `primitives` 무시), `_load_or_synthesize()`(라이브조회/리샘플 폴백), `/ict/symbols`에 `live_symbols` 추가
- `tests/test_ict_combinator.py` — preset 관련 테스트 2개 추가(알수없는 프리셋 에러, 정상 실행)
- `seokminal-dashboard/lib/api.ts` — `IctPresetsResponse`/`getIctPresets`, `IctSymbolsResponse.live_symbols`, `IctBacktestRequest.preset` 추가
- `seokminal-dashboard/app/ict/page.tsx` — 조합빌더/프리셋 탭 전환, 검색형 심볼 콤보박스, 고정 6종 타임프레임 셀렉트, 라이브 심볼 뱃지
- 브라우저로 3가지 다 라이브 검증: BTC 검색선택→4h AND콤보 실행(HL 라이브조회 성공, UNDERPOWERED 정상 렌더) / 프리셋탭 2024 Model→BTC 1m 재현 실행(라이브조회+진입 3건 UNDERPOWERED 정상 렌더) / AAPL 1h 프리셋(15m 리샘플 정상)
- `pytest tests/` 773 passed, 기존 무관 pre-existing 4실패(test_auth 3개 + test_backtest_happy_path)만 유지. `tsc --noEmit` 클린

### 다음 할 일
- 없음(이 트랙 정리 완료)
- DART 소형주 캐시 확장(세션3에서 남긴 할 일)은 백그라운드에서 계속 진행 중(PID 39906, 2026-07-08 세션4 종료 시점 기준 2022년도 처리 중, 4개 연도 중 1번째) — 다음 세션에서 완료 여부·최종 커버리지 숫자 확인 필요

### 막힌 부분/결정사항
- 없음. 프리셋 탭은 재검증 아니라는 점 페이지 문구에 상시 고정 — "왜 프리셋 켜놨는데 REJECT라고 하냐" 질문 나오면 이 항목 참고

---

## 2026-07-08 (세션5): ICT 프리셋 탭 폐기 → 전부 조합빌더로 병합 + Turtle Soup 신규

### 완료된 작업
- 사용자 피드백: "ICT는 여러 전략을 동시에 섞어서 쓰는 거지 CISD 하나로 매매하는 게 아니다. 프리셋 탭(단일모델 고정)이 구조적으로 틀렸다. 터틀 수프도 추가해서 전부 조합빌더에 섞어라." → 세션4에서 만든 별도 "프리셋(기각확정 재현)" 탭을 완전히 제거하고, 프리셋 6종의 핵심 로직(OTE/Unicorn/iFVG/CISD)을 양방향(bullish/bearish) 객관적 프리미티브로 일반화해 조합빌더에 흡수. 새 패턴 Turtle Soup(확정 swing 가짜돌파 후 반전, 기존 sweep과 달리 raw N봉 lookback이 아니라 확정 구조적 swing 포인트 사용) 신규 추가
- 결과: 프리미티브 5종 → 10종(killzone/sweep/fvg/order_block/market_structure/**ote/unicorn/ifvg/cisd/turtle_soup**), 전부 단일 빌더에서 AND 자유조합. 프리셋 모드/탭 개념 자체가 코드에서 사라짐(`evaluate_preset`, `PRESET_IDS`, `/ict/presets` 엔드포인트, `getIctPresets`, `IctBacktestRequest.preset` 전부 삭제)

### 변경된 파일
- `research/ict/primitives.py` — `ote_touches`, `unicorn_zones`, `ifvg_events`, `cisd_events`, `turtle_soup_events` 5개 함수 신규(전부 idx+type(bullish/bearish) 태그된 이벤트 리스트 반환, 기존 컨벤션 그대로)
- `research/ict/combinator.py` — 전면 재작성. `PRESET_IDS`/`evaluate_preset`/`models_2024.MODELS` 의존 제거, `PRIMITIVE_IDS` 10개로 확장, `evaluate_combo()`가 신규 5개까지 전부 dispatch
- `api_server/router_ict.py` — `/ict/presets` 삭제, `IctBacktestRequest`에서 `preset` 필드 제거하고 `window`/`near`/`min_run`/`confirm` 파라미터 추가(각각 ote·ifvg / unicorn / cisd / turtle_soup용)
- `seokminal-dashboard/lib/api.ts` — `IctPresetsResponse`/`getIctPresets`/`preset?` 제거, `IctBacktestRequest`에 `window`/`near`/`min_run`/`confirm` 추가
- `seokminal-dashboard/app/ict/page.tsx` — `mode`/`preset` state·탭 UI 전부 제거, `PRIMITIVES` 배열 10개로 확장, 선택된 프리미티브에 따라 조건부 파라미터 필드(swing_k/window/near/min_run/confirm) 노출
- `tests/test_ict_combinator.py` — 프리셋 관련 테스트 제거, `_zigzag_bars()` 픽스처(스윙·BOS·갭·연속캔들열 골고루 발생) 신규 + 신규 프리미티브 3개 테스트(크래시 없음, AND결합 부분집합 성질, 전체 10종 dispatch 가능)
- `pytest tests/test_ict_combinator.py tests/test_ict_primitives.py -q` 16 passed, `tsc --noEmit` 클린, 브라우저로 killzone+CISD+Turtle Soup 혼합조합(구/신 프리미티브 섞은 조합) 실행 확인 — SPY/15m, 진입 20건, percentile 65.6%/p=0.35(정상 렌더, 참고치 문구 유지)

### 다음 할 일
- 없음(이 트랙 정리 완료). 신규 5개 프리미티브도 표준조합 REJECT 결론과 마찬가지로 정식 CANDIDATE 파이프라인 대상 아님 — 사용자가 조합빌더에서 유의미해 보이는 조합을 찾으면 그때 BH-FDR 정식 배치로 넘기는 별도 작업 필요(지금 계획 없음)

### 막힌 부분/결정사항
- 없음. 프리셋 탭은 사용자 피드백으로 아키텍처 자체가 틀렸다고 판단해 완전 제거 — 재추가 요청 오면 이 항목 참고("ICT는 단일모델이 아니라 조합으로 쓴다"가 이유)

---

## 2026-07-08 (세션6): ICT 조합빌더 캔들차트 오버레이 신규

### 완료된 작업
- 사용자 피드백: "심볼 입력하면 차트나오고 해당 조건들 입력하면 차트에서 지표처럼 나오는 그런거 안되나? fvg,ifvg,cisd 이런것도 다 나오고 실버불렛이나 터틀수프가는 것도 다 시각적으로보이는?" → 기존엔 통계 테이블만 있었음(차트 자체가 없었음), 선택한 프리미티브를 캔들차트 위에 zone(FVG/OB/Unicorn=사각형)·point(sweep/BOS/OTE/iFVG/CISD/Turtle Soup=화살표 마커)·band(killzone=전체높이 반투명 세로띠)로 오버레이 표시하는 신규 기능
- 핵심 설계: `evaluate_combo()`의 AND결합 `entries_idx`(통계용, 전 프리미티브 교집합)와 완전히 분리된 `detect_events()`(차트용, 프리미티브별 원본 이벤트 개별 노출, AND결합 안 함) — "조합으로 뭐가 같이 터졌는지"와 "각 개념이 개별로 어디서 발생했는지"를 다른 레이어로 유지
- `lightweight-charts`에 사각형/존 렌더링 내장기능이 없어서 `ISeriesPrimitive` 플러그인 API로 직접 구현(zone renderer, fancy-canvas 비트맵 좌표 사용) — 사전 예시 없이 `node_modules` 타입정의 직접 읽고 작성, 첫 컴파일에 클린 통과
- 브라우저 검증: SPY/15m 전체 히스토리로 killzone+sweep+FVG+BOS+CISD+Turtle Soup 6종 혼합 렌더 확인(화살표 마커 정상, entries=0/UNDERPOWERED는 6종 AND교집합이 좁아서 나온 정상 결과) + FVG 단독선택으로 확대해서 파란 사각형 zone이 캔들 위 가격갭 위치에 정확히 겹치는 것 zoom 스크린샷으로 확인

### 변경된 파일
- `research/ict/combinator.py` — `detect_events()` 신규(파일 끝에 추가, 기존 `evaluate_combo()` 무변경). `POINT_PRIMITIVES`/`ZONE_PRIMITIVES`/`BAND_PRIMITIVES` 상수 + `_runs()`(연속인덱스→구간 리스트, killzone 밴드용). unicorn은 zone bounds가 없어서(`unicorn_zones()`가 `{idx,type}`만 반환) `(idx,type)` 키로 `fair_value_gaps()` 매칭 zone을 재사용
- `api_server/router_ict.py` — `_load_filtered()` 헬퍼로 로드/날짜필터/최소봉수체크 추출(backtest·events 양쪽 공유), `IctBar`/`IctEventsResponse` 모델 신규, `POST /ict/events` 엔드포인트 신규
- `seokminal-dashboard/lib/api.ts` — `IctBar`/`IctEvent`/`IctEventsResponse` 타입 + `getIctEvents()` 신규(요청 바디는 기존 `IctBacktestRequest` 재사용)
- `seokminal-dashboard/components/ict/IctChart.tsx` — 신규 파일. 캔들차트 + zone 사각형(`ZoneOverlay`/`ZonePaneView`/`ZoneRenderer`, `ISeriesPrimitive` 커스텀 플러그인) + point 화살표 마커(`createSeriesMarkers`) 렌더링. `ICT_LEGEND` export(페이지 범례용)
- `seokminal-dashboard/app/ict/page.tsx` — `/ict/events` 병렬 fetch(별도 `chartAbortRef`, 실패해도 통계 결과엔 영향 안 줌) + 통계 패널 위에 범례+`<IctChart>` 렌더 블록 추가
- `tsc --noEmit` 클린, `pytest tests/test_ict_combinator.py tests/test_ict_primitives.py -q` 16 passed(기존 그대로, `detect_events()` 자체 단위테스트는 아직 없음)

### 다음 할 일
- `detect_events()` 전용 pytest 없음(zone/point/band 3종 shape 검증하는 가벼운 테스트 1개 정도가 적당해 보임, 아직 사용자 요청은 아님 — 필요시 제안)
- 범례 스와치 색상이 `style={{ backgroundColor: ... }}` inline style 사용 중 — CLAUDE.md의 `style={{}}` 금지 규정(예외: 차트 컨테이너 height)에 엄밀히는 안 걸리는 케이스지만 프리미티브별 동적 색상이라 디자인 토큰으로 못 뺌, 필요시 재검토

### 막힌 부분/결정사항
- 없음

---

## 2026-07-08 (세션7): GC/ES/NQ/EURUSD/USDJPY 인트라데이 데이터 수집

### 완료된 작업
- 배경: ICT는 알고리즘/기관 오더플로우 개념이라 개인주식보다 유동성 큰 선물/FX가 더 맞는다는 논의 → GC(금)/ES/NQ(지수선물)/EURUSD/USDJPY/XAU 데이터 확보·매매가능성 조사부터 시작
- `research/data/futures_intraday_loader.py` 신규: IB `ContFuture`(GC/ES/NQ) 인트라데이 로더. **`ContFuture`는 `endDateTime`을 과거로 지정하는 요청 자체를 거부**(Error 10339, "continuous future" 제약) — 그래서 만기별계약처럼 커서로 과거를 걸어갈 수 없고, `endDateTime=""`(현재) 단발요청에서 `durationStr`만 실측으로 키워 상한을 찾음: 15m="6 M", 5m="1 M", 1m="1 M"(그 이상은 사이즈초과로 조용히 0봉). GC 6M 풀은 클라이언트 기본 60s 타임아웃 초과로 간헐 실패 → `timeout=120` 추가로 해결
- `research/data/fx_intraday_loader.py` 신규: IB `Forex`(EURUSD/USDJPY) 로더. Forex는 ContFuture와 달리 과거 `endDateTime` 커서가 허용돼서 15m은 주단위 청크 백필(156주≈3년), 1m/5m은 마찬가지로 사이즈상한 있어 단발요청만(실측: 1m="1 M", 5m="3 M")
- **IB 계정 이슈 2건 직접 해결**: (1) FX market data가 페이퍼계좌에 자동 상속 안 됨 → Client Portal에서 라이브↔페이퍼 계좌 마켓데이터 공유 설정+TWS 재시작 필요 (2) 그 후에도 Error 162 "Trading TWS session is connected from a different IP address" → 원인은 IBKR 웹포탈에 동시 로그인된 세션이었음, 포탈 로그아웃 후 해결
- **XAUUSD는 미해결**: `Forex('XAUUSD')` 자체가 IB에서 `qualify` 안 됨(Error 200, no security definition) — 계정에 보이는 "Physical Metals and Commodities(L1)" 구독은 다른 contract 타입(Commodity/CFD 등) 필요로 추정, 이번 세션에서 미시도
- 최종 수집 결과(모두 `data/intraday/{SYMBOL}_{TF}.parquet`, `/ict/symbols`에 자동 노출 확인):

| 심볼 | 1m | 5m | 15m |
|---|---|---|---|
| GC | 29,880봉 (06-08~07-08) | 5,976봉 (06-08~07-08) | 12,076봉 (01-04~07-08) |
| ES | 31,260봉 (06-07~07-08) | 6,252봉 (06-07~07-08) | 12,119봉 (01-04~07-08) |
| NQ | 31,260봉 (06-07~07-08) | 6,252봉 (06-07~07-08) | 12,119봉 (01-04~07-08) |
| EURUSD | 29,954봉 (06-09~07-08) | 17,961봉 (04-12~07-08) | 12,578봉 (01-02~07-08) |
| USDJPY | 29,955봉 (06-09~07-08) | 17,961봉 (04-12~07-08) | 12,578봉 (01-02~07-08) |

- 1h/4h는 별도수집 불필요 — 기존 `router_ict.py`의 `_resample_from_15m()`이 15m 원본에서 자동 합성(GC/EURUSD 1h로 브라우저·API 양쪽 확인)
- 브라우저 검증: `/ict` 페이지에서 GC 15m + FVG로 실제 백테스트 실행 확인(진입수 2140, eligible 12067≈전체봉수, percentile 93%, FVG zone 사각형 캔들차트 위 정상 렌더링), 가격 스케일도 API 원본(4097~4508)과 일치 확인

**XAUUSD 대안 — HL GOLD 트랙 추가**
- IB XAUUSD가 안 풀려서(`Forex('XAUUSD')` qualify 자체 실패) 대안으로 Hyperliquid에서 금 트래킹 상품 조사
- 1차로 HL 기본 퍼프 유니버스에서 `PAXG`(Pax Gold, 현물 1oz 담보 토큰) 발견 → `LIQUID_PERPS`(`research/data/hl_funding_loader.py`)에 추가. 근데 거래량 $440만/day로 얇음(HL 내 CRV~AAVE급, BTC의 1/500)
- 사용자가 "GOLD-USDC 퍼프 있잖아"로 재확인 요청 → HL의 빌더배포 dex(HIP-3) `"xyz"`에서 `xyz:GOLD` 발견(`{"type":"perpDexs"}` API로 조회, 기본 `{"type":"meta"}` 호출엔 안 잡힘 — dex 파라미터 필요). 가격 4079.9(GC 4097과 거의 일치), 거래량 **$4,390만/day**(PAXG의 10배) — 이쪽이 진짜 쓸만한 트랙. `xyz:SILVER`($2억/day), `xyz:CL`(원유, $4.5억/day), `xyz:EUR/JPY/GBP`(FX, 유동성은 얇음)도 같은 dex에 존재 확인만 함(미추가)
- `xyz:GOLD`도 `LIQUID_PERPS`에 추가 — `candleSnapshot` API가 `coin` 필드에 `"xyz:GOLD"` 프리픽스 그대로 받아줘서 `hl_candle_loader.py`/`router_ict.py` 코드 변경 전혀 없이 그대로 작동(콜론 포함 심볼도 `intraday_store.path_for()`가 파일명으로 문제없이 저장)
- XAUT0/USDC, XAUM 등 HL 스팟 금 페어도 확인했으나 XAUT0는 markPx가 실제 금값과 안 맞고(0.34, 페깅 깨짐) 거래량도 $6,951/day로 사실상 죽은 마켓 — 미채택
- 최종: PAXG, xyz:GOLD 둘 다 1m/5m/15m 라이브조회+parquet 캐시 확인 완료(크립토 계열은 `LIQUID_PERPS`에만 넣으면 `_load_or_synthesize`가 모든 tf 자동 라이브조회+캐시하는 기존 구조라 추가 코드 불필요)

| 심볼 | 1m | 5m | 15m | 비고 |
|---|---|---|---|---|
| PAXG | 5,056봉 (07-05~07-08) | 5,011봉 (06-21~07-08) | 5,004봉 (05-17~07-08) | 거래량 얇음($440만/day) |
| xyz:GOLD | 5,042봉 (07-05~07-08) | 5,008봉 (06-21~07-08) | 5,003봉 (05-17~07-08) | GC 대체 주력($4,390만/day) |

### 변경된 파일
- `research/data/futures_intraday_loader.py` — `--tf {1m,5m,15m}` 파라미터 추가(기존 15m 전용 → 3개 tf 지원), `BAR_SIZE`/`MAX_DURATION`을 tf별 dict로 변경
- `research/data/fx_intraday_loader.py` — 전면 재작성. `--tf` 추가, 15m은 기존 커서 백필 유지, 1m/5m은 단발요청 경로(`backfill_single_shot`) 신규. XAUUSD는 docstring에 미지원 사유 명시, 기본 `--symbols`에서 제거(EURUSD,USDJPY만)
- `research/data/hl_funding_loader.py` — `LIQUID_PERPS`에 `PAXG`, `xyz:GOLD` 추가
- `docs/progress.md` — 이 항목

### 다음 할 일
- XAUUSD(IB 정식 금현물) 데이터는 여전히 미해결 — 필요하면 `Commodity`/`CFD` contract 타입 재조사. 다만 `xyz:GOLD`로 사실상 대체 가능해서 우선순위 낮음
- `backends/ib/order_client.py`는 아직 `Stock` 주문만 지원, HL 쪽도 PAXG/xyz:GOLD 주문 실행 코드 없음 — GC/ES/NQ/EURUSD/USDJPY/GOLD로 실제 매매하려면 선물/FX/HL-빌더퍼프 주문 실행 코드 신규 필요(이번 세션은 데이터만, 집행은 범위 밖)
- 사용자가 ICT 조합빌더에서 이 심볼들로 유의미한 조합을 찾으면 BH-FDR 정식 파이프라인행 검토
- `xyz:SILVER`/`xyz:CL`(원유)도 거래량 괜찮아 보임 — 필요시 같은 방식으로 `LIQUID_PERPS` 추가만 하면 됨(코드 변경 불필요, 확인됨)

### 막힌 부분/결정사항
- XAUUSD(IB) 보류(계정 contract 매핑 미해결) — 대신 `xyz:GOLD`(HL 빌더퍼프)로 사실상 대체, GC/ES/NQ/EURUSD/USDJPY/xyz:GOLD 6개로 진행

---

**오더플로우 멀티벤뉴(바이낸스/OKX) 통합 + 라이브 검증 (2026-07-11)**

### 완료된 작업
- 대량체결/흡수 신호 백테스트로 통계적 무의미 확정 → HL 단일소스 한계로 보고 바이낸스+OKX 체결 테이프 합류 결정, `MultiVenueOrderflowClient`(HL+Binance+OKX 병합, 죽은 소스가 다른 소스 안 막음, 실패 소스 재연결) + `binance_adapter.py`/`okx_adapter.py` 구현, unit test(페이크 커넥션 기준) 통과 후 커밋 완료
- 이번 세션에서 **실서버 라이브 연결 검증** 진행(그동안 페이크 커넥션 테스트만 있었음):
  - 바이낸스 `wss://stream.binance.com:9443/ws/btcusdt@aggTrade` — 정상 연결, 파서 포맷(`e`/`p`/`q`/`m`/`T`) 그대로 일치
  - OKX `wss://ws.okx.com:8443/public` — **404, URL 버그 발견**. 정확한 엔드포인트는 `wss://ws.okx.com:8443/ws/v5/public`. `orderflow/okx_adapter.py` + `tests/test_orderflow_okx_adapter.py` 수정, 18개 orderflow venue 테스트 재통과 확인, 커밋(`baf7e33`)
- `/orderflow` 브라우저 스팟체크 중 **별개 문제 추가 발견**: uvicorn 백엔드(포트 8000)가 26시간째 PPID 1 고아 프로세스로 떠 있었고 완전 무응답 상태(curl까지 타임아웃, `/docs`도 안 뜸) — reload 워처가 죽고 워커만 남은 것으로 추정. kill 후 재기동
- 재기동 후 라이브 확인: BTC.HL 캔들 정상 렌더링(64217대, 바이낸스 실가 64218과 일치 = 멀티벤뉴 합류 작동 확인), 대량체결 버블 마커 실시간 표출, CVD 서브패널 값 정상, 콘솔 에러 없음

### 변경된 파일
- `orderflow/okx_adapter.py` — `OKX_WS_URL`을 `/ws/v5/public`로 수정
- `tests/test_orderflow_okx_adapter.py` — URL assertion 값 동일하게 수정
- `docs/progress.md` — 이 항목

### 다음 할 일
- uvicorn 고아 프로세스 재발 원인 미조사 — `--reload` 워처가 왜 죽었는지(리소스 문제/장시간 방치/다른 원인) 확인 안 함. 재발하면 원인 추적 필요
- 흡수/대량체결 신호가 백테스트로 통계적 무의미 확정났는데도 라이브 대시보드엔 여전히 마커만 뜨고 "매매판단용 아님" 경고가 UI에 없음 — 요청 범위 밖이라 안 건드렸음, 필요하면 별도 요청으로

### 막힌 부분/결정사항
- 없음(이번 라운드는 검증+버그수정만, 설계 이슈 없었음)

---

**오더플로우 ES/GC 선물 추가 + 크로스벤뉴 liquidity pool (2026-07-11)**

### 완료된 작업
- "nq,es,xau,forex 오더플로우 붙이기 어렵나" 질의에 ES/GC는 쉬움(IB `Future` contract, 기존 NQ 패턴 그대로), Forex는 어려움(IB FX는 quote-driven이라 TradeEvent 기반 로직과 안 맞음) 판단 → ES/GC만 진행, Forex는 미착수
- `orderflow/ib_adapter.py`: `_FUTURES_SYMBOLS`에 `ES: CME`, `GC: COMEX` 추가(기존 `NQ: CME` 옆에)
- `orderflow/manager.py`: `TICK_SIZE_BY_SYMBOL`에 `ES: 0.25`, `GC: 0.10` 추가, `tick_size`를 `MultiVenueOrderflowClient`에 전달하도록 변경
- **liquidity pool**(작업하면서 같이 요청받음): 오더북 뎁스도 트레이드 테이프처럼 바이낸스+OKX+HL 합류. `binance_adapter.py`에 `stream_depth`(`@depth20@100ms`) 추가, `okx_adapter.py`에 `stream_depth`(`books5` 채널) 추가, `multi_venue_adapter.py`에 `_round_to_tick`/`_pool_levels`/`_pool_books` 신규 — 벤뉴별 최신 스냅샷을 tick 단위로 반올림 후 사이즈 합산해서 하나의 풀북으로 병합해 내보냄. `aggregator.on_book_snapshot()`이 스냅샷을 통짜 교체로 처리하는 구조라 벤뉴별 스냅샷을 그대로 흘리면 깜빡였을 것 — 그래서 병합 후 emit으로 설계
- `stream()` pump 3개→5개(hl, binance-trades, binance-depth, okx-trades, okx-depth), 모두 공통 sink로 유입
- 신규 유닛테스트 15개(binance/okx depth 파서+스트림, pool 함수 3종, 통합 스트림 테스트) 작성, orderflow 전체 + 풀 스위트(869 passed, pre-existing 4 fail만 잔존) 통과 확인
- 브라우저 라이브 재검증: 백엔드 reload 두 번 걸림(아래 참고) 후 재기동, BTC.HL 정상 렌더링·콘솔 에러 없음 확인. 단 UI엔 벤뉴별 분리 표시가 없어 풀링 효과가 화면상으로는 구분 안 됨(내부 수치만 바뀜)
- 로컬 TWS 켠 뒤 ES/GC/NQ contract qualify 라이브 시도 → **API 핸드셰이크 타임아웃**(TCP는 붙음, `connectAsync` 15s 타임아웃). TWS의 "Enable ActiveX and Socket Clients" 설정 또는 incoming-connection 수락 팝업 미해결로 추정 — **미검증 상태로 남음**

### 변경된 파일
- `orderflow/ib_adapter.py` — `_FUTURES_SYMBOLS`에 ES/GC 추가
- `orderflow/manager.py` — `TICK_SIZE_BY_SYMBOL`에 ES/GC 추가, tick_size 전달
- `orderflow/binance_adapter.py` — `stream_depth`/`parse_binance_depth_message` 추가
- `orderflow/okx_adapter.py` — `stream_depth`/`parse_okx_depth_message` 추가
- `orderflow/multi_venue_adapter.py` — 5-pump 구조 + 풀링 로직(`_round_to_tick`, `_pool_levels`, `_pool_books`, `_make_pooling_sink`) 추가
- `tests/test_orderflow_binance_adapter.py`, `tests/test_orderflow_okx_adapter.py`, `tests/test_orderflow_multi_venue_adapter.py` — 신규 테스트 15개
- `docs/progress.md` — 이 항목

### 다음 할 일
- ES/GC contract qualification 라이브 미검증 — TWS API 설정(Enable ActiveX and Socket Clients, trusted IP 127.0.0.1) 확인 후 재시도 필요. IB 포트 관례상 7496/7497이 아니라 **7498**(paper) 사용 중이었음 — 다음 시도 때 포트 확인할 것
- uvicorn `--reload` 행(hang) 재발 — 이번 라운드에서도 두 번째 발생. 로그에 `api_server/lv5_agent.py:185` `ZeroDivisionError`(`wins/n:.0%`, n=0일 때) 있었으나 shutdown hang과의 인과관계 미확인, 별개 버그로 방치 중. 재발 계속되면 lv5_agent 쪽부터 볼 것
- Forex(EURUSD/USDJPY) 오더플로우는 IB FX가 quote-driven이라 별도 설계 필요 — 미착수, 요청 시 진행

### 막힌 부분/결정사항
- IB TWS API 핸드셰이크 타임아웃으로 ES/GC 실제 contract qualify 못함 — TWS 설정 점검 필요(사용자 확인 요)

---

## 작업 히스토리

### 2026-06-21
- KIS 일봉 데이터 수집 파이프라인 구축
- KIS WebSocket 실시간 스트리밍 구현

### 2026-06-22
- KIS 주문 실행 어댑터 구현
- IB 실시간 체결 스트리밍 구현

### 2026-06-23
- IB 주문 실행 어댑터 구현
- 조건 파서/평가기 엔진 구현
- 전략 스포너 구현

### 2026-06-24
- IB 히스토리컬 데이터 수집 구현
- 백테스트 자동화 구현
- 상관관계 분석 구현

### 2026-06-25
- 대시보드 백엔드 FastAPI 서버 구현
- KOSPI/SPY 인덱스 데이터 수집 구현
- beta_analysis 모듈 구현 (`/beta` 엔드포인트 제외)
- docs/progress.md 작업 루틴 세팅
- pyproject.toml 패키지 누락 수정
