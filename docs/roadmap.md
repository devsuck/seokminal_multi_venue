# Seokminal Multi-Venue — Roadmap

**마지막 업데이트:** 2026-08-27 (critic 키 미스매치 수정 + Lv5 권한 축소 + 스키마 드리프트 가드)
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
| — | Polymarket 실시간 틱 수집기(데이터만) | `research/polymarket_tick/` | 07-08 |
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
| — | **critic 지표 키 미스매치 수정** — `backtest.py`가 실험원장을 `net_pnl`/`random_pct`로 읽었으나 현행 스키마 키는 `net`/`percentile`(원장에 42종 스키마 혼재). 두 필드 None → critic 검사가 전부 `is not None` 가드라 **플래그 0개인데 rejected** = 실데이터 전략 전건 오탈락. autoresearch가 6주간 찾은 유일한 후보 3건(`auto_fac_kr_size_smb`/`amihud_illiq`/`turnover_neglect`, p=0.0033·BH생존·레드팀CLEARED·WF후반≥전반)이 07-13에 폐기됐고 루프는 이후 224회 더 CANDIDATE 재생산. 별칭 조회 + `metrics_incomplete` 플래그 + 층간 불일치 감시 신규 | `jarvis/agents/backtest.py`, `critic.py`, `research/check_pipeline_consistency.py` | 08-27 |
| — | **Lv5 권한 축소 + 스키마 드리프트 가드** — `_call_claude`의 `--dangerously-skip-permissions`/`bypassPermissions` 제거→`--disallowed-tools`(프롬프트에 외부 문자열이 삽입되는 주입 경로 차단). `_call_claude` returncode 확인, `_run_review` 데몬스레드 예외를 캐시/API로 노출. `schema_guard.py` 신규 — "근거는 쌓였는데 추출 0건"을 콜드스타트와 구분해 신고, `agent_perf`·`lv5_learner` 배선(오탐 방지 위해 파서 독립적 근거 사용) | `api_server/schema_guard.py`, `lv5_agent.py`, `lv5_learner.py`, `agent_perf.py` | 08-27 |

---

## 진행 중

- **골드 데이터소스 확정** — HL `xyz:GOLD` vs IB `1OZ`/`SI`(COMEX) vs IB `XAUUSD`/`XAGUSD`(CMDTY 스팟) 3갈래 조사 중. 마켓휴장일이라 "구독권한 없음"과 "그냥 장 닫힘"이 구분 안 돼서 결론 보류 — 평일 재확인 필요. 상세: `docs/progress.md` 07-12 섹션
- **tom forward 모니터링** — `kr_turn_of_month_v1_PORTFOLIO` paper_active, 매월 말 4일 코호트 자동 누적 중. 3~12개월 관찰 후 WF 후반 16배 감쇠가 forward에서도 재현되는지가 KILL/유지 판단 기준
- **buyback v2 shadow(레짐필터) forward 대기** — in-sample 개선 확인됨(net 1.58%→2.40%, 승률 50.7%→54.7%), forward 이벤트 등록(07-03) 이후 0건(공시 희소). 신규 buyback 공시 쌓이면 `buyback_v2_forward.py` 재실행

---

## 백그라운드 상시 수집기 (tmux)

| 세션 | 내용 | 상태(07-12 22:04 확인) |
|---|---|---|
| `polymarket-tick` | Polymarket WSS 틱 수집 | 정상 — 재연결루프 작동 중(502/커넥션끊김 로그는 노이즈), 오늘자 파일 실시간 갱신 확인 |
| `hl-orderflow-tick` | HL BTC/ETH 오더플로우 틱 수집 | 정상 — 동일 패턴, 오늘자 파일 실시간 갱신 확인 |
| `seokminal-agent-*` ×4 | 스윙/단타 페이퍼 에이전트 봇 | 실행 중(개별 성과 헬스체크는 안 함 — 대시보드 `/agents`에서 확인) |
| `cross-venue-skew-tick` | 크로스벤뉴 오더북 스큐 수집(BTC/ETH × hl/binance/okx) | 07-13 01:46 신규 시작 — 6파일 실시간 갱신 확인 |

---

## 다음 세션 최우선

1. **오탈락 3건 재승격 실행** — critic 버그로 폐기된 `auto_fac_kr_size_smb`(net 4.23%)/`auto_fac_kr_amihud_illiq`(1.64%)/`auto_fac_kr_turnover_neglect`(1.20%)를 파이프라인 재실행으로 registry에 재전이. 에이전트가 원장을 임의로 밀어넣지 않고 남겨둔 항목(append-only 프로덕션 상태 + forward 자동배선 이어짐). 사후 `PYTHONPATH=. python3 research/check_pipeline_consistency.py`가 0건이어야 정상. **주의**: 셋 다 학계에 잘 알려진 팩터(SMB·Amihud·거래대금 소외)라 캐파·혼잡 리스크 별도 검토 필요
2. **`pytest tests/ -q` 전체 재확인** — 08-27 변경은 conftest 없는 격리 환경에서 jarvis 298건 + 신규 16건만 통과 확인. 컨테이너가 Python 3.11이라 unpinned `nautilus_trader`가 1.221.0으로 잡히며 `MaxDrawdown` import가 깨져 전체 스위트 실행 불가(기존 이슈, 이번 변경과 무관). Python 3.14 호스트에서 재확인 필요
3. **GENERATOR 스케줄 기동** — `jarvis/GENERATOR.md` 하단 "스케줄 설정(별도 opt-in)"이 안 켜져 있음. 신규 가설 최초등장이 07-08에서 멈췄고(19종 이후 0종) 이후 5주간 같은 18개를 224회 재검증만 함 — 자율 탐색이 아니라 고정 리스트 재검증 크론 상태
4. **골드 데이터소스 최종 결정** — 평일 마켓시간에 `probe_ib_gold4.py`(GC vs 1OZ, COMEX 선물) + `probe_ib_spotgold.py`(XAUUSD/XAGUSD, CMDTY 스팟) 재실행해서 에러이벤트로 무료구독 범위 확정. 참고: `xyz:GOLD`(HL)는 이미 07-08 세션에 데이터 파이프라인 검증 완료(parquet 캐시, PAXG 대비 유동성 10배) — IB 쪽이 막히면 바로 대체 가능한 상태
2. **오더플로우 트랙 결론 반영** — BTC/ETH(원시+컨텍스트게이트) 전부 REJECT 확정. 같은 신호군 파라미터 튜닝 재시도 금지(여러 세션째 확인된 원칙). 재시도하려면 근본적으로 다른 방향: 선물 NQ/MNQ 원시틱 이식(현재 미저장이라 별도 결정 필요), POC/value area 필터, 또는 완전히 다른 마켓구조 가설
3. IB Client Portal `CME Real-Time (NP,L2)` 구독 여전히 미완(사용자 직접 신청 필요) — NQ/MNQ/GC/ES 계열 라이브 오더플로우 전부 이 구독 없이는 tick 수신 불가(contract resolve까지만 됨)
4. **CB/BW 발행 negative-drift 리스크필터 배선** — 공시 후 하위5% 확인됨(07-초 검증)이나 아직 미배선. buyback v1은 동결이라 붙이려면 새 v3 shadow로 등록 필요(설계 미착수)
5. **US 내부자매수 UNDERPOWERED** — 27개 대형주 유니버스로는 이벤트 부족(24건/유효13건) 확정. 유니버스 확장 시 재시도 가능(미착수)
6. **논문기반 알파마이닝 파이프라인(Phase 133) 실전 검증** — `python -m research.run_paper_ingest` 1회 실행해 라이브 arXiv 논문 e2e 통과율 확인 안 됨(구현만 완료, 최종 whole-branch 리뷰도 미실행: `scripts/review-package e18921b <HEAD>`)
7. **`/edges` 프론트 페이지 브라우저 렌더 확인** — 백엔드 `/lab/edges`·`/lab/fleet`는 curl 스모크 완료(2026-07-22), 대시보드 `/edges` 페이지(포트폴리오 타일+함대칩+테이블+스파크라인) 실브라우저 확인은 아직 안 함. `mlb_specialist_consensus`는 이번 세션에 `warmable: True`로 승격됐으니 폴리마켓 2종+MLB 총 3종이 뜨는지 확인.
8. **`polymarket_sharp_wallet_bot` 처분 결정** — 08-16 비활성화만 함(누적 -$2025, 순수 비용잠식). 전략 로직 재검토해서 살릴지, 완전 폐기할지 다음 세션에서 결정.
9. **"엣지 있는 기능만 압축해서 에이전틱에 올리기" 논의 이어가기** — 사용자가 08-16에 이 방향 언급했으나 구체 실행은 안 함. `docs/agentic-roadmap.md`(07-02 작성, 검증된 엣지 0개 상태 기준이라 최신 아닐 수 있음) 갱신 필요할 수도.

---

## 알려진 블로커

- **경계 스키마 계약 부재 (같은 버그 클래스 3회)**: `actions`vs`action`(lv5_learner, 자기학습 6주 사망) · `fill`vs`fills`(agent_perf, -94.64% 오기록) · `net_pnl`vs`net`(backtest, 실데이터 전건 오탈락 5주+). 전부 타입 없는 dict를 모듈 경계로 넘기며 예외 대신 None을 반환해 **조용히** 실패한다. 테스트 4,323건이 다 놓친 건 픽스처가 버그 스키마를 그대로 흉내내서. 08-27에 세 경계(critic·lv5_learner·agent_perf)에 가드를 세웠다 — `api_server/schema_guard.py`가 "근거는 쌓였는데 추출 0건"을 드리프트로 신고한다. 다만 이건 **탐지**지 계약이 아니다. `routers/agents.py`↔사이클 페이로드, `lv5_dsl`, `lv5_context` 등 나머지 경계는 그대로고, dataclass/TypedDict + 필수 키 검증으로 구조적 차단은 아직 미착수
- ~~**`lv5_agent.py:66` 권한 과다**~~ ✅ **08-27 해소.** `--disallowed-tools`로 도구 전부 차단 (`--permission-mode`만으론 print 모드에서도 Bash가 실행되는 걸 CLI로 확인). 커밋 `895005c`
- **CME/COMEX 계열(GC/ES/NQ) 실시간 tick**: "No market data permissions" — 유료구독(`CME Real-Time (NP,L2)`, ~$12.10/월) 필요, 사용자 미신청
- ~~**Lv5 리뷰 라벨링 버그 (agent 491d9679, HL)**~~ ✅ **08-16 해소.** 실제 원인은 추정과 달랐음 — HYPE 포지션 반전 문제가 아니라 (1) `extract_trade_outcomes()`가 `actions`(존재한 적 없는 키)를 읽던 파싱버그, (2) exit 4개 venue 전부 구조화 `fill` 미기록. `fills` 리스트 스키마로 수정, `491d9679`는 `e19bf348`로 클린 리셋. 상세: `docs/progress.md` 2026-08-16.
- **IB XAUUSD(Forex 타입)**: `Forex('XAUUSD')` qualify 자체 실패(Error 200, no security definition) — CMDTY 타입(`XAUUSD`/`XAGUSD`, conId 확보완료)으로 대체 경로 발견(07-12), 평일 라이브검증 대기
- **Forex(EURUSD/USDJPY) 오더플로우**: IB FX가 quote-driven이라 기존 TradeEvent 기반 로직과 구조가 안 맞음 — 미착수, 별도 설계 필요
- **uvicorn `--reload` hang 재발 가능성**: 근본원인(`timeout_graceful_shutdown=None`)은 CLAUDE.md 커맨드에 `--timeout-graceful-shutdown 10` 고정으로 해결됨 — 이 플래그 없이 기동하면 재발

---

## 검증 철학(고정 — 매 트랙 공통)

- 랜덤 same-frequency baseline 대비 p-value, walk-forward, cost-robust, BH-FDR로 multiple-testing 보정
- **결과 보고 사후 파라미터 튜닝 금지** — REJECT 나오면 다른 가설로, 같은 가설 파라미터만 바꿔 재시도 안 함
- eligible 모집단(HOLD 포함) 기준 랜덤비교, 사전고정 규칙(데이터스누핑 방지)
- 신규 배치는 기존 가설 풀과 별도 BH-FDR 풀로 분리(사후 가설풀 오염 방지)
