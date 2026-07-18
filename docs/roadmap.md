# Seokminal Multi-Venue — Roadmap

**마지막 업데이트:** 2026-07-17
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

1. **골드 데이터소스 최종 결정** — 평일 마켓시간에 `probe_ib_gold4.py`(GC vs 1OZ, COMEX 선물) + `probe_ib_spotgold.py`(XAUUSD/XAGUSD, CMDTY 스팟) 재실행해서 에러이벤트로 무료구독 범위 확정. 참고: `xyz:GOLD`(HL)는 이미 07-08 세션에 데이터 파이프라인 검증 완료(parquet 캐시, PAXG 대비 유동성 10배) — IB 쪽이 막히면 바로 대체 가능한 상태
2. **오더플로우 트랙 결론 반영** — BTC/ETH(원시+컨텍스트게이트) 전부 REJECT 확정. 같은 신호군 파라미터 튜닝 재시도 금지(여러 세션째 확인된 원칙). 재시도하려면 근본적으로 다른 방향: 선물 NQ/MNQ 원시틱 이식(현재 미저장이라 별도 결정 필요), POC/value area 필터, 또는 완전히 다른 마켓구조 가설
3. IB Client Portal `CME Real-Time (NP,L2)` 구독 여전히 미완(사용자 직접 신청 필요) — NQ/MNQ/GC/ES 계열 라이브 오더플로우 전부 이 구독 없이는 tick 수신 불가(contract resolve까지만 됨)
4. **CB/BW 발행 negative-drift 리스크필터 배선** — 공시 후 하위5% 확인됨(07-초 검증)이나 아직 미배선. buyback v1은 동결이라 붙이려면 새 v3 shadow로 등록 필요(설계 미착수)
5. **US 내부자매수 UNDERPOWERED** — 27개 대형주 유니버스로는 이벤트 부족(24건/유효13건) 확정. 유니버스 확장 시 재시도 가능(미착수)
6. **논문기반 알파마이닝 파이프라인(Phase 133) 실전 검증** — `python -m research.run_paper_ingest` 1회 실행해 라이브 arXiv 논문 e2e 통과율 확인 안 됨(구현만 완료, 최종 whole-branch 리뷰도 미실행: `scripts/review-package e18921b <HEAD>`)

---

## 알려진 블로커

- **CME/COMEX 계열(GC/ES/NQ) 실시간 tick**: "No market data permissions" — 유료구독(`CME Real-Time (NP,L2)`, ~$12.10/월) 필요, 사용자 미신청
- **Lv5 리뷰 라벨링 버그 (agent 491d9679, HL)** — `api_server/lv5_learner.py:49` `extract_trade_outcomes()`가 포지션 오픈을 `fill.side=="buy"`일 때만 추적, close 매칭은 액션 문자열에 "close"/"청산" 필요. HYPE는 실제 체결 282건(15차 리뷰 기준 buy111/sell171, HYPE만 buy107/sell161) 있는데 청산 액션이 전체 1479사이클 동안 단 0건 — HYPE 포지션이 정상 청산 경로를 안 타고 매 사이클 반대방향 재진입으로 계속 뒤집히는 것으로 추정(정확한 메커니즘 미확인, `get_positions()` 추적 의심). 결과: outcome이 0으로 고정돼 기대값 계산 자체가 구조적으로 불가능. 리뷰 텍스트로 14회 연속(2026-07-15) 알렸는데 미수정이라 여기 기록으로 전환. 고칠 내용: (1) short 진입(`fill.side=="sell"`)도 open_trades에 등록, (2) HYPE가 close 경로를 안 타는 원인 규명. 수정 전까지 해당 에이전트 threshold/position_pct 동결, HYPE 신규 진입 중단 권고 유지 중.
- **IB XAUUSD(Forex 타입)**: `Forex('XAUUSD')` qualify 자체 실패(Error 200, no security definition) — CMDTY 타입(`XAUUSD`/`XAGUSD`, conId 확보완료)으로 대체 경로 발견(07-12), 평일 라이브검증 대기
- **Forex(EURUSD/USDJPY) 오더플로우**: IB FX가 quote-driven이라 기존 TradeEvent 기반 로직과 구조가 안 맞음 — 미착수, 별도 설계 필요
- **uvicorn `--reload` hang 재발 가능성**: 근본원인(`timeout_graceful_shutdown=None`)은 CLAUDE.md 커맨드에 `--timeout-graceful-shutdown 10` 고정으로 해결됨 — 이 플래그 없이 기동하면 재발

---

## 검증 철학(고정 — 매 트랙 공통)

- 랜덤 same-frequency baseline 대비 p-value, walk-forward, cost-robust, BH-FDR로 multiple-testing 보정
- **결과 보고 사후 파라미터 튜닝 금지** — REJECT 나오면 다른 가설로, 같은 가설 파라미터만 바꿔 재시도 안 함
- eligible 모집단(HOLD 포함) 기준 랜덤비교, 사전고정 규칙(데이터스누핑 방지)
- 신규 배치는 기존 가설 풀과 별도 BH-FDR 풀로 분리(사후 가설풀 오염 방지)
