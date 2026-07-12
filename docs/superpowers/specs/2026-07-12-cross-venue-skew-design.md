# 크로스벤뉴 오더북 스큐 — 설계

**날짜**: 2026-07-12
**목적**: BTC/ETH 오더플로우 미세구조 신호(16개, `orderflow_context_gate.py` 포함) 전부 REJECT 이후, 근본적으로 다른 메커니즘 검증. 여러 거래소(HL/Binance/OKX)의 오더북 임밸런스가 서로 괴리(스큐)되는 순간이 가격 선행지표가 되는지 확인. 실집행 없음, 통계적 유의미성 검증이 목표.

## 배경

기존 오더플로우 트랙(footprint_imbalance/absorption/cvd_divergence/confluence/gated_confluence, 총 16개)이 단일 벤뉴(HL) 체결테이프 기반 신호로 전부 REJECT됨. 청산 캐스케이드 가설은 검토했으나 Hyperliquid 공개 API에 마켓전체 청산 탐지용 채널이 없어(공식 subscription 24종 확인, `liquidations` 채널 부재, `userEvents`는 유저별이라 스캔 불가) 폐기. 펀딩레이트 극단치는 Phase99에서 이미 REJECT된 메커니즘이라 재시도 안 함(`project_phase99_hl_funding` 메모). 남은 방향인 크로스벤뉴 오더북 스큐로 진행.

`orderflow/multi_venue_adapter.py`가 이미 HL+Binance+OKX 3개 벤뉴 오더북을 실시간 풀링하지만, 풀링 과정에서 벤뉴별 스냅샷이 하나로 합쳐져 사라짐 — 스큐(벤뉴간 괴리) 계산엔 벤뉴별로 분리된 원장이 필요해서 신규 수집기가 필요하다.

## 핵심 설계 결정

**스큐 정의**: 벤뉴간 최우선호가 가격 괴리(차익거래 갭)가 아니라, 벤뉴간 오더북 임밸런스(매수/매도 잔량 비율) 괴리를 본다. 가격 갭은 차익봇이 즉시 메꿔 신호 수명이 극히 짧지만, 임밸런스 괴리("한 벤뉴만 매수벽/매도벽 급붕괴")는 유동성 구조 변화를 반영해 수명이 더 길 가능성이 있다.

**방향 컨벤션(사전고정)**: 스큐가 발생한 벤뉴의 임밸런스 방향과 같은 방향으로 포지션을 잡는다(모멘텀 컨벤션 — "그 벤뉴가 매수우위로 급격히 기울면 롱"). 반대방향(평균회귀) 컨벤션은 이번 스코프에 포함하지 않는다 — 두 방향을 동시에 테스트하면 사실상 가설 2개(멀티플 테스팅 이중계상)가 되므로, 모멘텀 하나만 사전등록하고 결과와 무관하게 이 컨벤션을 유지한다.

**호라이즌**: 5s/15s/60s 세 개를 사전등록해 같은 BH-FDR 풀에 넣는다(방향은 사전고정하되 호라이즌은 다중검정 보정 대상으로 명시).

**저장은 raw, 공식은 나중에**: 수집기는 벤뉴별 오더북 스냅샷을 가공 없이 그대로 저장한다. depth_n·zscore_threshold 같은 공식 파라미터는 첫 결과를 보기 전에 이 문서에 숫자로 고정하고, 결과를 본 뒤에는 바꾸지 않는다.

## 컴포넌트

### 1. 수집기 — `research/run_cross_venue_skew_collect.py` (신규, tmux 상시실행)

기존 어댑터를 `multi_venue_adapter.py`를 거치지 않고 직접 사용:
- `BinanceOrderflowClient.stream_depth(coin)` → `OrderBookSnapshot`
- `OkxOrderflowClient.stream_depth(coin)` → `OrderBookSnapshot`
- `HyperliquidOrderflowClient.stream(coin)` → `OrderBookSnapshot | TradeEvent` 중 `OrderBookSnapshot`만 필터

코인 2개(BTC/ETH) × 벤뉴 3개 = 6개 독립 태스크, 코인별·벤뉴별 개별 재연결(기존 `run_hl_orderflow_tick_collect.py`의 `run_coin_forever` 패턴 그대로: 지수백오프 2s→60s, 스트림 정상수신 후 종료면 백오프 리셋, 무수신 종료는 백오프 유지).

```python
def append_snapshots(venue: str, coin: str, snapshots: list[dict]) -> None:
    """research/data/cross_venue_skew/{venue}_{coin}_{date}.jsonl 에 append.
    한 줄 = {"venue": venue, **OrderBookSnapshot.model_dump()}"""

async def run_venue_coin_forever(venue: str, coin: str, client, append_fn=append_snapshots) -> None:
    """run_hl_orderflow_tick_collect.run_coin_forever와 동일 구조 —
    OrderBookSnapshot만 필터링(HL은 TradeEvent도 섞여오므로), venue 태그 추가."""

async def run_forever() -> None:
    """venue×coin 6개 조합에 대해 run_venue_coin_forever를 asyncio.gather."""
```

### 2. 가설모듈 — `research/hypotheses/cross_venue_skew.py` (신규)

```python
IMBALANCE_DEPTH_N = 5  # OKX books5가 top5까지만 주므로 3개 벤뉴 공통 depth를
                        # 이 값으로 고정 — 이보다 깊게 잡으면 OKX만 얕은 임밸런스가 됨.
                        # 최적화 대상 아님, 결과 보고 안 바꿈.

def load_venue_snapshots(venue: str, coin: str, dates: list[str]) -> "pd.DataFrame":
    """jsonl 로드, columns=[ts, bids, asks]."""

def build_imbalance(df: "pd.DataFrame", depth_n: int = IMBALANCE_DEPTH_N) -> "pd.Series":
    """시점별 imbalance = sum(bid.size[:depth_n]) / (sum(bid.size[:depth_n]) + sum(ask.size[:depth_n])).
    0.5=중립, 1에 가까울수록 매수우위. index=ts."""

RESAMPLE_GRID_S = 1.0     # 1초 고정 그리드
FFILL_TOLERANCE_S = 5.0   # 마지막 스냅샷이 5초 넘게 안 갱신되면 그 벤뉴는 해당 버킷 NaN

def align_venues(imbalance_by_venue: dict[str, "pd.Series"]) -> "pd.DataFrame":
    """RESAMPLE_GRID_S 그리드로 각 벤뉴 imbalance를 asof-ffill(tolerance=FFILL_TOLERANCE_S)
    정렬. 컬럼=벤뉴명. tolerance 초과分은 NaN으로 남기고(추정값으로 메우지 않음),
    이후 divergence 계산에서 자연스럽게 제외된다."""

DIVERGENCE_ZSCORE_LOOKBACK = 300  # 1s그리드 기준 300틱=5분 롤링 윈도우, 고정

def build_skew_divergence(aligned: "pd.DataFrame") -> "pd.DataFrame":
    """벤뉴 컬럼 2개 이상 유효한 시점만 대상. 각 벤뉴 v에 대해
    divergence[v] = imbalance[v] - mean(imbalance[다른 벤뉴들]).
    반환은 벤뉴별 divergence 컬럼을 가진 DataFrame(어느 벤뉴가 튀었는지 방향 정보 보존)."""

SPIKE_ZSCORE_THRESHOLD = 2.0  # 고정, 최적화 금지

def build_spike_signal(divergence: "pd.DataFrame", lookback: int = DIVERGENCE_ZSCORE_LOOKBACK,
                        threshold: float = SPIKE_ZSCORE_THRESHOLD) -> "pd.DataFrame":
    """벤뉴별 divergence 컬럼마다 롤링(lookback) z-score 계산, |z|>=threshold인 시점을
    스파이크로 표시. 반환 컬럼: spike(bool), direction(divergence 부호 그대로:
    양수=그 벤뉴가 매수우위로 튐→모멘텀 컨벤션상 롱, 음수=숏)."""

HORIZONS_S = [5, 15, 60]  # 사전등록, BH-FDR 풀 공용

def build_price_series(aligned_books_by_venue: dict[str, "pd.DataFrame"]) -> "pd.Series":
    """RESAMPLE_GRID_S 그리드에서 벤뉴별 mid=(best_bid+best_ask)/2를 구하고
    벤뉴간 평균 — 레이블 계산용 단일 가격 시계열(코인당 1개).
    best_bid/best_ask는 리스트 순서를 신뢰하지 않고 명시적으로
    best_bid=max(bid.price), best_ask=min(ask.price)로 계산한다."""

def build_labels_multi_horizon(price: "pd.Series", spikes: "pd.DataFrame",
                                horizons_s: list[int] = HORIZONS_S) -> "pd.DataFrame":
    """스파이크 시점 t마다 각 h in horizons_s에 대해
    forward_return = (price[t+h] - price[t]) / price[t] * direction(모멘텀 컨벤션 부호 반영).
    t+h가 데이터 범위 밖이면 그 행 제외."""
```

### 3. 검증러너 — `research/run_cross_venue_skew_validate.py` (신규)

`research/validation/*`(baselines/walk_forward/cost_model/multiple_testing)를 그대로 재사용 — 새 통계 엔진 만들지 않음. `simulate_long_short`/`trade_metrics`/`random_same_frequency`/`empirical_p_value`, HL 비용모델(`hl_effective_cost_bps("major", taker=True)`) 동일 적용.

코인 2개 × 호라이즌 3개 = 6개 p-value → **신규 독립 BH-FDR 풀**(기존 16개 오더플로우 배치, context-gate 2개 배치와 별도 — 사후에 합치면 각 배치의 "사전 고정 가설셋" 전제가 깨짐).

## 에러 처리

- 수집기: 벤뉴×코인 6개 독립 재연결루프(기존 패턴 그대로). 파싱 실패는 기존 `parse_*` 관례대로 조용히 스킵. 디스크 쓰기 실패는 별도 처리 안 함(로컬 파일시스템 신뢰, 기존 컬렉터 관례와 동일).
- 검증러너: 벤뉴 데이터 공백(재연결 중 tolerance 초과)은 `align_venues`의 NaN으로 자연 처리 — `build_skew_divergence`가 유효 벤뉴 2개 미만인 시점을 자동 제외.

## 테스트 계획

`tests/test_run_cross_venue_skew_collect.py` (신규):
- mock adapter stream으로 jsonl 출력 검증, venue 태그 정확성, OrderBookSnapshot/TradeEvent 필터링(HL 소스에서 TradeEvent는 저장 안 됨) 확인

`tests/test_cross_venue_skew.py` (신규):
- `build_imbalance`: depth_n 이내/밖 레벨 반영 여부, 0.5 중립 케이스
- `align_venues`: tolerance 안/밖 ffill, 그리드 정렬 정확성
- `build_skew_divergence`: 벤뉴 1개만 유효할 때 제외되는지, 3개 다 유효할 때 부호 정확성
- `build_spike_signal`: threshold 경계값, lookback 미달 구간(z-score 계산 불가) 처리
- `build_labels_multi_horizon`: 방향 부호 반영, 범위 밖 horizon 제외

## 파일 변경 요약

- 신규: `research/run_cross_venue_skew_collect.py`
- 신규: `research/hypotheses/cross_venue_skew.py`
- 신규: `research/run_cross_venue_skew_validate.py`
- 신규: `tests/test_run_cross_venue_skew_collect.py`
- 신규: `tests/test_cross_venue_skew.py`
- 무수정: `orderflow/multi_venue_adapter.py`, `orderflow/binance_adapter.py`, `orderflow/okx_adapter.py`, `orderflow/hl_adapter.py` (기존 클라이언트 그대로 재사용, 라이브 대시보드 코드패스 리스크 없음)

## 스코프 밖

- 평균회귀(반대방향) 컨벤션 — 모멘텀 하나만 사전등록, 사후에 반대방향 추가 테스트 안 함
- 벤뉴 가격 갭(차익거래) 기반 스큐 — 신호수명 문제로 배제
- BTC/ETH 외 코인 확장 — 기존 REJECT 트랙과 모집단 동일하게 유지
- depth_n/zscore_threshold/lookback 그리드서치 — 여기 고정값으로 1회 검증, 결과 보고 안 바꿈
- 데이터 축적 기간/최소 표본수 결정 — 수집 시작 후 별도 판단(신규 라이브수집이라 이 스펙 시점엔 미확정, 수집기 실행 자체는 이 스펙 승인 즉시 가능)
