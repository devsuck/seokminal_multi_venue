# Seokminal Multi-Venue — Roadmap

**마지막 업데이트:** 2026-08-25 (텔레그램 알림 전체 배선 완료 + 429 retry/backoff + Polymarket 기능 전체삭제)
**스택:** Python 3.14, FastAPI, NautilusTrader, pytest(`asyncio_mode=auto`, `@pytest.mark.asyncio` 금지)

> 프론트엔드 로드맵은 별도: `seokminal-dashboard/docs/roadmap.md`
> 이 파일은 `docs/progress.md`(세션별 상세 로그)의 요약/전방위 뷰. 새 세션 시작 시 둘 다 읽을 것.

---

## 완료된 Phase

| Phase | 내용 | 주요 파일 | 날짜 |
|---|---|---|---|
| 1 | KIS 데이터/주문 | `backends/kis/` | 06-21~22 |
| 2 | IB 데이터/주문 | `backends/ib/` | 06-22~24 |
| 3 | 조건엔진/전략스포너 | `condition_engine/`, `strategy_spawner/` | 06-23 |
| 4 | 백테스트/상관분석 | `backtest_runner/`, `correlation_analysis/` | 06-24 |
| 5 | 대시보드 API + 베타분석 | `api_server/main.py` | 06-25 |
| 9 | 매크로지표 + 기업재무(FRED/ECOS/EDGAR/KSD) | `fred/`, `ecos/`, `corp_finance/`, `sec_edgar/` | 06-25~26 |
| 10 | 퀀트지표 고도화(몬테카를로/레짐필터) | `monte_carlo/`, `regime_filter/` | 06-26 |
| — | ~~Polymarket 실시간 틱 수집기(데이터만)~~ **08-25 전면삭제**(한국 IP 지오블록 HTTP 451 확인, 유저 장기 한국상주 확정 — 상세: `seokminal-dashboard/docs/progress.md` Phase 230) | `research/polymarket_tick/`(삭제됨, git 히스토리 복구가능) | 07-08 |
| — | GC/ES/NQ/EURUSD/USDJPY 인트라데이 데이터 + `xyz:GOLD` 발견 | `research/data/futures_intraday_loader.py`, `hl_funding_loader.py` | 07-08 |
| — | 오더플로우 시그널 검증 하네스(NQ/MNQ, subagent-driven 7태스크) | `orderflow/` | 07-08 |
| — | KIS 해외선물옵션 어댑터 시도 → IB 유지 결론(데이터소스 전환 검토 종료) | `orderflow/kis_adapter.py`(보류) | 07-12 |
| — | IB 마켓데이터 구독정리 + absorption 신호 이식 | `orderflow/manager.py` | 07-12 |
| — | 오더플로우 멀티벤뉴(바이낸스/OKX) 통합 + 라이브검증 + liquidity pool 뱃지UI | `orderflow/multi_venue_adapter.py`, `binance_adapter.py`, `okx_adapter.py` | 07-11 |
| — | ES/GC 선물 오더플로우 추가 + IB front-month 자동resolve 버그수정 | `orderflow/ib_adapter.py` | 07-11 |
| — | **BTC/ETH 오더플로우 원시(14신호) + 컨텍스트게이트 재검증 → 전부 REJECT** | `research/hypotheses/orderflow_context_gate.py` | 07-12 |
| — | 크로스벤뉴 오더북 스큐 가설(BTC/ETH×hl/binance/okx) — SDD 6태스크, 머지레디, 실데이터 축적 대기 | `research/hypotheses/cross_venue_skew.py` | 07-12 |
| 133 | 논문기반 알파마이닝 파이프라인(arXiv→LLM스펙추출→코드생성→스모크체크→격리 BH-FDR 검증) | `research/papers/`, `research/run_paper_ingest.py` | 07-15 |
| — | **KR turn-of-month 포트폴리오 `paper_active` 승격** — 포트레벨 재검(p=0.002) → forward 자동배선(`tom_forward:generate`, monthly) | `research/paper/tom_forward.py` | 07-16 |
| — | **Lv5 fills 스키마 버그 수정 + agent 491d9679 리셋** — `actions`(존재한 적 없는 키)→`action` 파싱버그, exit 4개 venue 전부 구조화 fill 미기록 버그 수정(단수 `fill`→복수 `fills` 리스트). 아래 "알려진 블로커" Lv5 항목 해소. `491d9679`(-94.64%) 삭제 후 `e19bf348`로 클린 리셋 | `api_server/routers/agents.py`, `agent_perf.py`, `lv5_learner.py` | 08-16 |
| — | **미커밋 백로그(08-05~08-15, 150+파일) 전수검토·분리커밋** — gz 압축데이터 무음누락 버그, options_uoa 하트비트/사후수익률 라벨링, convergence_legs 4소스 상시수집기, sharp_wallet maker/taker 체결시뮬, polymarket_bot 다각화 무엣지 사후검증, 지식그래프 스코어 이력 API, `grand_total_realized_pnl` ₩/$ 혼합 제거, 재부팅시 에이전트 자동복구, 워치독 데스크톱 알림 — 13개 논리커밋으로 분리(상세: `docs/progress.md` 2026-08-16 이어서) | 다수(커밋별 명시) | 08-16 |
| — | **디스크 위기 대응 + 데이터 수명주기 크론 배선** — 시스템 디스크 97% 도달, `research/data` 12G→6.0G 수동압축. `compress_old_data.sh` 대기기간 2일→0일 단축, `prune_old_data.py`(90일 삭제, 기존 미배선) wrapper 신규+크론 등록(05:00) | `scripts/compress_old_data.sh`, `scripts/prune_old_data.sh` | 08-16 |
| — | **전체 플랫폼 라이브 헬스체크 + 장애대응 5건** — 좀비 tmux 제거, Lv5 ZeroDivisionError 수정, agent `e19bf348` 드라이버 미기동 발견+기동, whale_tick sleep-wake 크래시(워치독이 세션존재만 보고 내부프로세스 생사는 안 봄 — 알려진 갭) 대응+지수백오프 이식, `prune_old_data` 크론/launchd 중복 정리, `polymarket_sharp_wallet_bot`(누적 -$2025, 순수비용잠식) 비활성화 | `api_server/lv5_agent.py`, `research/run_polymarket_whale_collect.py` | 08-16 |
| — | **Polymarket 트레이딩 기능 전체삭제** — 지오블록(HTTP 451) + 유저 장기 한국상주 확정으로 페이퍼봇 3개·리서치 스캐너 19개·서브패키지 7개·테스트 52개 삭제. 공유 인프라는 결합부만 수술적 제거 | (다수 삭제, 커밋 `c985dac`) | 08-25 |
| — | **텔레그램 알림 나머지 3건 배선 + 429 retry/backoff** — arm_check(watchdog 전이감지 재사용)·daily_summary(신규 launchd 22:30) 배선, strategy_pivot은 중복이라 스킵 결정, `lv6_notify._send()` 429 bounded retry(최대 3회, retry_after 준수, 30s 상한) | `api_server/lv6_notify.py`, `api_server/daily_summary.py`, `research/lab/service.py` | 08-25 |
| — | **REJECT 확정 UOA/ICT 페이퍼봇 전면삭제** — options-uoa(08-13 REJECT, 0/8 BH-FDR survive) tmux kill+watchdog목록제거, ict-orderflow-paper(08-13 REJECT, 평균R=-0.13) 죽어있던 것 파일까지 정리. `research/ict/primitives.py`는 다른 살아있는 트랙이 써서 존치 | (다수 삭제, 상세: `docs/progress.md` 08-25 이어서2) | 08-25 |
| — | **`orderflow_context_gate.py` 죽은 임포트체인 전면삭제** — 자체 REJECT(07-12) + 임포터 4개(futures_on_btc REJECT 14/14, signal_matrix REJECT 0/99·0/103, futures_bar_matrix/bar_sweep 방치스캐폴드, gex_gate 외부임포터0) 전부 죽음 확인 후 11파일 일괄삭제. 공유 프리미티브(absorption/tape_vwap/futures/ict primitives)는 다른 트랙이 써서 존치 | (11파일 삭제, 상세: `docs/progress.md` 08-25 이어서3) | 08-25 |
| — | **골드 데이터소스 최종 확정 — `xyz:GOLD`(HL) 채택, IB 경로 폐기** — 같은 날 확정된 "IB active venue scope 제외" 결정으로 IB `1OZ`/`XAUUSD` 조사 자체가 무의미해짐. `xyz:GOLD`는 이미 07-08/07-22에 실사용 검증 끝난 상태(유동성 PAXG 10배, GC와 가격 근접, 코드변경 없이 `/research/xau-session`까지 노출됨) — 코드변경 없이 기록만 확정 | (코드 변경 없음, 상세: `docs/progress.md` 08-25 이어서4) | 08-25 |

---

## 진행 중

- **tom forward 모니터링** — `kr_turn_of_month_v1_PORTFOLIO` paper_active, 매월 말 4일 코호트 자동 누적 중. 3~12개월 관찰 후 WF 후반 16배 감쇠가 forward에서도 재현되는지가 KILL/유지 판단 기준
- **buyback v2 shadow(레짐필터) forward 대기** — in-sample 개선 확인됨(net 1.58%→2.40%, 승률 50.7%→54.7%), forward 이벤트 등록(07-03) 이후 0건(공시 희소). 신규 buyback 공시 쌓이면 `buyback_v2_forward.py` 재실행

---

## 백그라운드 상시 수집기 (tmux)

> ⚠️ 아래 상태열은 07-12 스냅샷이라 오래됨 — 실제 목록/생사는 `ensure_collectors.sh`의 `ENSURE=(...)` 또는 대시보드 `/lab/status`가 최신 소스. `polymarket-tick`은 08-25 Polymarket 전체삭제로 더 이상 존재하지 않음.

| 세션 | 내용 | 상태(07-12 22:04 확인, stale) |
|---|---|---|
| `hl-orderflow-tick` | HL BTC/ETH 오더플로우 틱 수집 | 정상 — 동일 패턴, 오늘자 파일 실시간 갱신 확인 |
| `seokminal-agent-*` ×4 | 스윙/단타 페이퍼 에이전트 봇 | 실행 중(개별 성과 헬스체크는 안 함 — 대시보드 `/agents`에서 확인) |
| `cross-venue-skew-tick` | 크로스벤뉴 오더북 스큐 수집(BTC/ETH × hl/binance/okx) | 07-13 01:46 신규 시작 — 6파일 실시간 갱신 확인 |

---

## 다음 세션 최우선

1. ~~골드 데이터소스 최종 결정~~ — 08-25 `xyz:GOLD`(HL)로 확정 완료(IB는 active venue scope 제외로 후보 탈락). 상세: `docs/progress.md` 08-25 이어서4
2. **오더플로우 트랙 결론 반영** — BTC/ETH(원시+컨텍스트게이트) 전부 REJECT 확정. 같은 신호군 파라미터 튜닝 재시도 금지(여러 세션째 확인된 원칙). 재시도하려면 근본적으로 다른 방향: 선물 NQ/MNQ 원시틱 이식(현재 미저장이라 별도 결정 필요), POC/value area 필터, 또는 완전히 다른 마켓구조 가설
3. IB Client Portal `CME Real-Time (NP,L2)` 구독 여전히 미완(사용자 직접 신청 필요) — NQ/MNQ/GC/ES 계열 라이브 오더플로우 전부 이 구독 없이는 tick 수신 불가(contract resolve까지만 됨)
4. **CB/BW 발행 negative-drift 리스크필터 배선** — 공시 후 하위5% 확인됨(07-초 검증)이나 아직 미배선. buyback v1은 동결이라 붙이려면 새 v3 shadow로 등록 필요(설계 미착수)
5. **US 내부자매수 UNDERPOWERED** — 27개 대형주 유니버스로는 이벤트 부족(24건/유효13건) 확정. 유니버스 확장 시 재시도 가능(미착수)
6. **논문기반 알파마이닝 파이프라인(Phase 133) 실전 검증** — `python -m research.run_paper_ingest` 1회 실행해 라이브 arXiv 논문 e2e 통과율 확인 안 됨(구현만 완료, 최종 whole-branch 리뷰도 미실행: `scripts/review-package e18921b <HEAD>`)
7. **`/edges` 프론트 페이지 브라우저 렌더 확인** — 백엔드 `/lab/edges`·`/lab/fleet`는 curl 스모크 완료(2026-07-22), 대시보드 `/edges` 페이지(포트폴리오 타일+함대칩+테이블+스파크라인) 실브라우저 확인은 아직 안 함. `mlb_specialist_consensus`는 이번 세션에 `warmable: True`로 승격됐으니 폴리마켓 2종+MLB 총 3종이 뜨는지 확인.
8. ~~`polymarket_sharp_wallet_bot` 처분 결정~~ — **08-25 무의미해짐.** Polymarket 트레이딩 기능 전체삭제(지오블록+유저 장기 한국상주)로 봇 자체가 코드베이스에서 사라짐.
9. ~~"엣지 있는 기능만 압축해서 에이전틱에 올리기" 논의 이어가기~~ / `docs/agentic-roadmap.md` 갱신 — **08-25 dashboard 레포에서 처리.** `seokminal-dashboard/docs/agentic-roadmap.md` "현재 위치" 섹션이 07-02 스냅샷(검증엣지 0개·Lv2 현재)인 채 방치돼 있던 걸 발견 → stale 표시 + 최신 근거(KR turn-of-month p=0.002 paper_active 승격, arm_criteria GO/WAIT/KILL 파이프라인 실존)로 갱신. 옵션/IB는 제품 결정으로 액티브 스코프 아님(코드 플래그 아님) — 완전성 판단·다음작업 제안 시 카운트하지 말 것.
10. **실거래 완전자동 실행 배선(08-25/26 밤샘 + 08-26, 완료)** — jarvis/execution/broker_bridge.py(KIS+HL 라우팅, risk_guard 이중체크, 알림) + jarvis/execution/live_router.py(fusion 기반 신호결합 — ensemble.py는 08-26 대체 후 삭제, armed+arm_criteria GO 기여자 없으면 Tier B 단독 절대 트리거 안 함) + jarvis/execution/edge_providers.py(전략별 arm_criteria 호환 edge 명시 레지스트리) 신규. live_engine/risk_guard.py venue별 리밋 + 파일기반 kill switch 배선(08-25/26). broker_bridge.route_order()가 AUTONOMY_LEVEL 게이트를 체크 안 하던 구멍(08-26 발견) 수정. research/lab/service.py가 6h 스로틀로 live_router.route_all() 자동 호출 — 실행루프 완성. 테스트 전부 통과. 남은 건: 사람 3게이트(arm/AUTONOMY_LEVEL/arm_criteria GO) 전부 잠긴 채 유지(의도적) + fusion v1_risk_adjusted가 track record 없는 전략엔 0표를 주므로 buyback이 closed 트레이드 2개 이상 쌓이기 전까진 그마저도 무의미(구조적, 코드 결함 아님). 상세: docs/superpowers/specs/2026-08-26-live-execution-router-design.md, docs/superpowers/plans/2026-08-26-live-execution-router.md.

---

## 알려진 블로커

- **CME/COMEX 계열(GC/ES/NQ) 실시간 tick**: "No market data permissions" — 유료구독(`CME Real-Time (NP,L2)`, ~$12.10/월) 필요, 사용자 미신청
- ~~**Lv5 리뷰 라벨링 버그 (agent 491d9679, HL)**~~ ✅ **08-16 해소.** 실제 원인은 추정과 달랐음 — HYPE 포지션 반전 문제가 아니라 (1) `extract_trade_outcomes()`가 `actions`(존재한 적 없는 키)를 읽던 파싱버그, (2) exit 4개 venue 전부 구조화 `fill` 미기록. `fills` 리스트 스키마로 수정, `491d9679`는 `e19bf348`로 클린 리셋. 상세: `docs/progress.md` 2026-08-16.
- **IB XAUUSD(Forex 타입)**: `Forex('XAUUSD')` qualify 자체 실패(Error 200, no security definition) — CMDTY 타입(`XAUUSD`/`XAGUSD`, conId 확보완료)으로 대체 경로 발견(07-12), 평일 라이브검증 대기
- **Forex(EURUSD/USDJPY) 오더플로우**: IB FX가 quote-driven이라 기존 TradeEvent 기반 로직과 구조가 안 맞음 — 미착수, 별도 설계 필요
- **uvicorn `--reload` hang 재발 가능성**: 근본원인(`timeout_graceful_shutdown=None`)은 CLAUDE.md 커맨드에 `--timeout-graceful-shutdown 10` 고정으로 해결됨 — 이 플래그 없이 기동하면 재발
- **실거래 arm 불가(구조적, 08-25 확인)**: `jarvis/execution/arm_criteria.py`(동결, 수정금지) GO 조건 `oos≥3개월 AND envelope_ratio≥2/3 AND paper_months≥6`. 현재 KIS paper_active 최고참 전략도 ~40일(요구 180일 대비 부족) — 몇 주~몇 달간 어떤 전략도 실자본 arm 불가능. 배선(broker_bridge/ensemble/risk_guard)은 완료됐으나 arm() 자체가 인간-ADMIN 전용이라 이 프로젝트에서 완화할 수 없는 게이트.
- **`jarvis/` 전역 pre-existing 테스트 실패 94건(08-25 발견)**: `4783145`(07-31, "remove autonomous research dead cluster")가 13개 모듈/95개 파일 삭제하며 golden-snapshot/module-count 테스트(`jarvis/architecture_docs`, `integration_audit`, `local_runtime`, `production_review`, `release_candidate`, `research_navigation`, `research_workflow`, `system_integration`)를 안 고쳐서 발생. **CLAUDE.md의 "pre-existing failures: 없음(07-30 전부 수정)" 클레임은 stale함** — 그 다음날 커밋이 깨뜨림, CLAUDE.md 갱신 필요(사용자 확인 후).

---

## 검증 철학(고정 — 매 트랙 공통)

- 랜덤 same-frequency baseline 대비 p-value, walk-forward, cost-robust, BH-FDR로 multiple-testing 보정
- **결과 보고 사후 파라미터 튜닝 금지** — REJECT 나오면 다른 가설로, 같은 가설 파라미터만 바꿔 재시도 안 함
- eligible 모집단(HOLD 포함) 기준 랜덤비교, 사전고정 규칙(데이터스누핑 방지)
- 신규 배치는 기존 가설 풀과 별도 BH-FDR 풀로 분리(사후 가설풀 오염 방지)
