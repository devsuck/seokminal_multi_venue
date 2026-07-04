# Lv2 — Scheduled Claude Code Hypothesis Generator

스케줄된 Claude Code(구독, **API키 0**)가 주기적으로 실행하며 가설을 제안한다.
결정적 파이프라인(datagate→backtest→critic→BH-FDR→registry)이 검증한다.

## 실행 절차 (스케줄 Claude Code가 매 실행마다)

1. **Market Memory 조회** — `python -m jarvis.registry show` + `jarvis/memory` 교훈 확인.
   거부된 family(모멘텀·인트라데이·펀딩·유동성웨이브 등) 반복 금지.
2. **가설 3~5개 제안** — 각 가설을 아래 스펙 JSON으로. 거부 family와 유사하면 `differentiation` 필수.
3. **큐 제출** — `python -m jarvis.research_queue submit --spec <file.json>`.
   - dedup·memory 가드가 부적격 제안을 거부(로그로 이유 반환).
4. **검증 실행** — `python -m jarvis.research_queue run --alpha 0.1`.
   - run_batch가 BH-FDR 다중검정 예산 적용. paper_candidate = critic 통과 AND BH 생존.
   - 승격분은 자동 forward 배선(paper_active).
5. **결과 기록** — registry/audit에 남음. 사람은 paper_active만 검토.

## 리서치 매트릭스 (편향 금지 — 전 시장 × 전 스타일)

하네스는 시장·스타일 중립. 매 실행 서로 다른 셀 탐색. BH-FDR이 남발 방지.

| 시장 | 데이터키(required_data) |
|---|---|
| KR | daily_ohlcv, market_cap, delisting_history, disclosure_event_dates, cb_bw_issuance |
| US | us_daily_ohlcv, us_intraday_15m, sec_filings_events (delisting/fundamentals_pit=SANITY) |
| CRYPTO | crypto_daily_ohlcv, crypto_intraday, crypto_funding |

**스타일:** event/catalyst · trend/momentum · mean-reversion · factor · microstructure/ICT · carry/basis · seasonality.

**이미 REJECT(재탕 금지, 변형은 differentiation):** US 인트라데이 패턴 6종, 크립토 funding, KR 순수모멘텀.
**ICT/기술패턴:** 공정 테스트하되 기계적 고정규칙으로 정의 + curve-fit 위험 명시.
**정직:** 실데이터 미배선 = 합성 null(edge_bps=0) → 대부분 REJECT/BLOCKED 정상. 가짜 승격 금지. 산출 = 아이디어 + 데이터 위시리스트.

## 스펙 JSON 스키마

```json
{
  "id": "kr_index_forced_flow_v1",
  "name": "KR 지수 강제편입 플로우",
  "family": "event",
  "market": "KR",
  "thesis": "패시브 지수 편입 전 강제매수 압력",
  "required_data": ["daily_ohlcv", "market_cap", "disclosure_event_dates"],
  "cost_bps": 40.0,
  "edge_bps": 0.0, "n_trades": 40, "hold": 20, "seed": 1,
  "keywords": ["index", "forced_flow"],
  "differentiation": "유동성웨이브와 달리 지수편입일 확정 이벤트 기반(생존편향 무관)"
}
```

- `edge_bps/n_trades/hold/seed` = 현재 합성 데모 백테스트용(실데이터 배선 전까지). 실데이터 붙으면 제거.
- `differentiation` = Market Memory에 유사 거부사례 있을 때만 필수.

## 가드레일 (자동 강제)
- **id 중복** → 거부(재검은 새 버전 id).
- **거부 family 유사 + differentiation 없음** → 거부.
- **한 배치 최대 25개**(스프레이 방지).
- **BH-FDR 예산** → 우연한 p<0.05 승격 차단.
- **live 실행 없음** — paper_active까지만. paper→live는 사람.

## 스케줄 설정 (별도 opt-in)
반복 Claude Code 잡 = 표준 시간 소모. 사람이 승인 후 설정:
- Claude Code 스케줄/cron으로 이 절차를 일/주 단위 실행.
- 각 실행은 위 5단계를 수행하고 종료. 상태는 registry/audit에 영속.
