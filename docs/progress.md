# Progress Log

> 이 파일은 세션 간 작업 맥락을 이어주는 용도입니다.
> 새 세션 시작 시: `@docs/progress.md @CLAUDE.md 읽고 이어서 작업해줘`

## 현재 상태 (마지막 업데이트: 2026-07-08 세션3)

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
