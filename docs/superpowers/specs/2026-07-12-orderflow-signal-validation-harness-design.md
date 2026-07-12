# 오더플로우 시그널 검증 하네스 설계

**날짜**: 2026-07-12
**목적**: NQ/MNQ 자동매매 봇 이전 단계 — footprint 불균형, heatmap 유동성벽, CVD 다이버전스, iceberg refill, stop-run 패턴 5개 시그널이 통계적으로 유의미한 엣지 있는지 검증. 실집행 없음.

## 배경

기존 검증 철학(Phase 94/102 TSMOM) 그대로 따름: 랜덤 베이스라인 대비 empirical p-value, walk-forward, cost-robust, BH-FDR 다중검정 보정. `research/validation/*` 인프라(engine/baselines/metrics/multiple_testing/walk_forward/cost_model) 그대로 재사용 — 신규 코드 없음.

직접 선례: `research/strategies/orderflow_absorption.py` + `research/run_hl_orderflow_tick_collect.py` (Hyperliquid BTC/ETH, absorption/large-trade 가설, 둘 다 REJECT). 패턴 그대로 계승하되 두 가지 차이:
1. 벤더가 IB(TWS/Gateway)로 바뀜 — futures 커미션 기반 비용모델 신규 필요(HL은 taker/maker bps 있음, IB는 없음).
2. 수집 범위가 trade tick만이 아니라 depth snapshot도 포함(유저 결정: "전부 한번에") — heatmap/iceberg 계열 신호까지 커버.

## 핵심 설계 결정: 수집기가 라이브 Aggregator를 재사용한다

`orderflow/aggregator.py`의 `OrderflowAggregator`는 이미 프론트 히트맵/풋프린트가 쓰는 것과 동일한 버킷팅·diff 로직(footprint 60s 버킷, heatmap 2s 버킷, near-touch만 저장). 연구용 수집기가 raw tick을 따로 저장하지 않고, `IBOrderflowClient.stream()` 이벤트를 이 Aggregator에 그대로 통과시켜 나온 `footprint_delta`/`heatmap_delta`를 jsonl에 append한다.

장점: 연구용 신호 재구성이 라이브 렌더링과 동일 소스코드 기반 — "백테스트가 프론트 로직과 슬쩍 달라지는" 버그 클래스(absorption.py 주석에 이미 한 번 언급된 문제)를 원천 차단. 저장량도 raw stream보다 훨씬 작음(diff만 저장, Phase 167에서 측정한 108msg/s 스트림 기준).

## 컴포넌트

### 1. 수집기 — `research/run_ib_orderflow_tick_collect.py`

`run_hl_orderflow_tick_collect.py` 1:1 패턴 계승:
- `SYMBOLS = ["NQ", "MNQ"]`
- 심볼별 독립 `asyncio` 재연결 루프, exponential backoff(2s~60s), backoff는 "한 번도 이벤트 못 받고 끊긴 경우"에만 escalate(HL 수집기와 동일 `received_event` 플래그).
- **client_id 분리 필수**: 이번에 고친 client_id 충돌 버그(`fd1c755`) 재발 방지 — NQ=20, MNQ=21로 심볼별 고정 할당. `IBOrderflowClient(client_id=...)` 명시 전달.
- 각 심볼마다 `OrderflowAggregator()` 인스턴스 하나 생성, `stream()`에서 나오는 `TradeEvent`/`OrderBookSnapshot`을 `on_trade()`/`on_book_snapshot()`에 통과시켜 delta만 append.
- 저장 경로: `research/data/ib_orderflow_tick/{SYMBOL}_{date}.jsonl`. 라인 포맷: delta dict + `{"symbol": ..., "recv_ts": ...}` 부가.
- `tick_size`: NQ/MNQ 둘 다 0.25(CME 표준 틱).
- tmux 상시 실행(`polymarket-tick`과 같은 운영 방식).

### 2. 비용모델 — `research/validation/cost_model.py`에 추가

신규 상수(코드베이스에 IB futures 커미션 상수 전무 확인함 — grep 결과 无):
```python
IB_FUTURES_COMMISSION_USD = {"NQ": 2.25, "MNQ": 0.55}  # 계약당 왕복 근사, IB 요금표 재확인 필요
IB_FUTURES_TICK_VALUE_USD = {"NQ": 5.0, "MNQ": 0.5}   # 0.25pt당
IB_FUTURES_SLIPPAGE_BUCKET = {"NQ": 0.5, "MNQ": 1.0}  # 틱 단위, MNQ가 유동성 낮아 더 큼
```
`ib_futures_effective_cost_bps(symbol, notional)` 함수 추가: 커미션 + 슬리피지를 notional 대비 bps로 환산해 반환. `hl_effective_cost_bps`와 동일 시그니처 패턴. **주석으로 "실요율 미검증, 페이퍼 전 재확인 필요" 명시** — 하드코딩 요율을 검증된 값처럼 오인하지 않도록.

NQ/MNQ는 별도 심볼로 검증 — 같은 근본 신호라도 tick value 차이(NQ $5 vs MNQ $0.5)로 비용 잠식률이 달라 판정이 갈릴 수 있음.

### 3. 가설 모듈 — `research/hypotheses/orderflow_futures.py`

`orderflow_absorption.py` 패턴 계승, 5개 시그널 함수:
- **footprint 불균형** (`build_footprint_imbalance_signals`): footprint_delta 리플레이 → 버킷별 buy_vol/sell_vol 비율 임계치 초과시 BUY/SELL. bar-index 방식, `engine.simulate_long_short` 그대로.
- **CVD 다이버전스** (`build_cvd_divergence_signals`): 누적 delta(buy-sell) vs 가격 추세 괴리. footprint_delta만 필요.
- **stop-run 패턴** (`build_stop_run_signals`): 이벤트 레벨 — absorption.py의 `run_large_trade_event_hypothesis` 패턴(고정 시간 지평 청산, 랜덤 베이스라인이 방향만 셔플) 그대로 재사용.
- **heatmap 유동성벽 근접** (`build_wall_proximity_signals`): heatmap_delta 리플레이해 근접 대형 벽 추적 → 가격이 벽 접근시 신호.
- **iceberg refill** (`build_iceberg_refill_signals`): 같은 가격 레벨에서 heatmap size가 소진→즉시 재충전되는 패턴 탐지(연속 버킷 비교 필요, 이 신호만 상태를 좀 더 들고 있어야 함).

각 함수는 `(ticks/deltas) → signals + eligible_indices` 반환. 실행 orchestration은 absorption.py의 `run_hypothesis()` 그대로 재사용(심볼/신호명만 파라미터화): `simulate_long_short` → `trade_metrics` → `random_same_frequency`(eligible_indices로 공정 비교) → `empirical_p_value` → `build_report`.

프론트(`lib/orderflow-data.ts`)에 이미 존재하는 임계값 로직 있으면 그대로 가져와 쓰고 재최적화 안 함(absorption.py와 동일 원칙 — "최적화하지 않음").

### 4. 검증/리포트 — 변경 없음

`research/validation/*` 그대로. 5신호 × 2심볼 = 10개 동시검정 → `multiple_testing.benjamini_hochberg(pvals, alpha=0.1)` 필수 적용, 개별 p-value 말고 보정된 결과로 최종 판정. `alpha_report.py` 판정 스케일(EDGE CANDIDATE/WEAK/INDISTINGUISHABLE/REJECT/UNDERPOWERED) 그대로.

## 데이터 흐름 요약

```
IB Gateway ─(reqTickByTickData+reqMktDepth)─> IBOrderflowClient.stream()
  ─(TradeEvent/OrderBookSnapshot)─> OrderflowAggregator.on_trade/on_book_snapshot()
  ─(footprint_delta/heatmap_delta)─> jsonl (research/data/ib_orderflow_tick/)
  ...수집 기간 경과 후...
  ─(load + replay)─> orderflow_futures.py 5개 signal builder
  ─(signals, eligible_indices)─> validation/engine + baselines + metrics + multiple_testing
  ─> alpha_report.py → research/reports/alpha/*.md
```

## 에러 처리

- 데이터 부족(bars < 10, absorption.py `_blocked` 패턴): "BLOCKED" 리포트 작성, 크래시 안 함.
- IB 연결 끊김: 수집기 레벨에서 재연결 루프가 흡수, 검증 실행 시점엔 이미 수집 완료된 jsonl만 읽으므로 영향 없음.
- 커미션/틱밸류 상수 오류 리스크: 코드 주석으로 미검증 명시, 페이퍼 단계 진입 전 IB 실제 요금표 대조 필요(별도 후속 작업, 이 하네스 스콥 밖).

## 테스트

- `test_orderflow_futures_signals.py`: 각 signal builder 함수에 대해 합성 footprint_delta/heatmap_delta 시퀀스 주고 기대 BUY/SELL/HOLD 검증(기존 `test_orderflow_aggregator.py` 스타일).
- `test_ib_futures_cost_model.py`: `ib_futures_effective_cost_bps` bps 계산 검증.
- `test_run_ib_orderflow_tick_collect.py`: `run_hl_orderflow_tick_collect.py`의 테스트(재연결 backoff, append_fn 분리) 패턴 그대로 이식.
- 수집기 자체는 라이브 IB 연결 필요해 CI에서 직접 못 돌림 — mock `IBOrderflowClient`/`IB()` 주입으로 대체(기존 `test_orderflow_ib_adapter.py`의 mock 패턴 재사용).

## 스코프 밖

- 자동매매 실집행(신호 검증까지만).
- IB futures 실제 요금표 확정(별도 확인 필요, 지금은 근사치).
- 프론트 UI 변경 없음(연구용 스크립트만).
