# 오더플로우 컨텍스트 게이트 — BTC/ETH 설계

**날짜**: 2026-07-12
**목적**: 방금 REJECT난 오더플로우 confluence(footprint_imbalance/absorption/cvd_divergence 다수결)에 실전 트레이더가 쓰는 컨텍스트 필터(상위TF트렌드/키레벨/VWAP/세션)를 게이트로 추가 — 컨텍스트가 방향을 정하고 오더플로우는 그 방향 안에서 타이밍만 잡는 구조. 실집행 없음, 통계적 유의미성 검증이 목표.

## 배경

`research/run_orderflow_futures_on_btc.py`에서 BTC/ETH 틱 데이터(2026-07-10~12)로 footprint_imbalance/absorption/cvd_divergence/confluence(2/3 다수결)/stop_run 전부 REJECT(BH-FDR survivors 14개 전부 False). "오더플로우만 보고 매매하는 트레이더 없다"는 논의 후 컨텍스트 필터 게이트를 새 가설로 검증하기로 함.

**대상 자산**: BTC/ETH (기존 틱 데이터 재사용, 오늘 바로 검증 가능). NQ/MNQ는 원시틱을 저장 안 하는 수집기 구조라 이 설계(고/저가 필요)가 그대로 안 넘어감 — 별개 결정.

**ICT 스코프**: `research/ict/primitives.py`의 `market_structure`/`swings`/`killzone_indices`만 재사용. OTE/Unicorn/iFVG/CISD/SMT 등 이미 죽은 프리셋 자체는 포함 안 함(주식에서 REJECT 확정, `research/run_ict_final.py`).

## 핵심 설계 결정: 게이트 모델, 다수결 아님

트렌드+키레벨+VWAP 3개가 **전부 같은 방향**이어야 bias 성립(2/3 다수결 아님 — 3/3 만장일치, 방향 결정은 더 보수적으로). bias 없으면 그 바는 무조건 HOLD. bias 있고 killzone 안이고, 기존 confluence가 같은 방향이면 진입. 신규 지표 발명 없이 기존 함수(market_structure/swings/killzone_indices, 그리고 이미 있는 confluence)만 조합.

## 컴포넌트

### 1. 바 빌더 — `research/hypotheses/orderflow_context_gate.py` (신규 모듈)

```python
def build_ohlc_bars(ticks: list[dict], bucket_sec: float = 60.0) -> list[dict]:
    """원시 틱({ts,price,size,side}) -> 60s 버킷 OHLC. 진짜 high/low(틱 기준),
    footprint_delta엔 없는 정보라 여기서 별도 계산."""

def resample_bars(bars: list[dict], factor: int = 15) -> list[dict]:
    """연속 factor개 바 묶어 상위 타임프레임 바 생성(o=첫바 o, h=구간 max h,
    l=구간 min l, c=마지막바 c, bucket_ts=첫바 bucket_ts)."""
```
둘 다 순수 함수, 작은 인풋으로 유닛테스트.

### 2. 트렌드 필터 (기존 함수 재사용)

```python
def build_trend_filter(bars_15m: list[dict], k: int = 2) -> list[str]:
    """market_structure(h,l,c,k)를 15분봉에 적용. 최근 BOS/CHoCH의 dir을
    다음 이벤트 나올 때까지 forward-fill(상태 유지). 이벤트 없는 초반 구간은 HOLD."""
```

### 3. 키레벨 필터 (기존 함수 재사용)

```python
KEY_LEVEL_PROXIMITY_PCT = 0.001  # 가격의 0.1% — 고정, 최적화 금지
                                  # (NQ의 tick_size=0.25 같은 절대틱 개념이
                                  # BTC/ETH엔 없어서 %기반으로 치환 — 자산 특성 차이일 뿐
                                  # 결과 보고 튜닝한 값 아님)

def build_key_level_filter(bars_15m: list[dict], proximity_pct: float = KEY_LEVEL_PROXIMITY_PCT) -> list[str]:
    """swings(h,l,k=2)로 스윙하이/로우 추출 -> 현재가가 가장 가까운 스윙레벨의
    proximity_pct 이내면 그 방향(스윙로우 근접=BUY, 스윙하이 근접=SELL)."""
```

### 4. VWAP/value area 필터 (신규 계산, 신규 데이터 아님)

footprint_delta가 이미 price×volume이라 새 수집 불필요.

```python
VWAP_WINDOW_BUCKETS = 240  # 60s버킷 240개 = 4시간, 고정 — 최적화 금지

def build_vwap_filter(deltas: list[dict], window_buckets: int = VWAP_WINDOW_BUCKETS) -> list[str]:
    """각 60s 버킷 시점 기준 직전 window_buckets 구간 footprint_delta로
    VWAP = sum(price*vol)/sum(vol) 계산. close > VWAP -> BUY, close < VWAP -> SELL."""
```
(POC/value area는 이번 스코프에서 제외 — VWAP 단독으로 충분히 방향 신호. 필요해지면 후속 확장.)

### 5. 세션 필터 (기존 함수 그대로)

`research.ict.primitives.killzone_indices` import해서 그대로 사용(파라미터 안 건드림: NY오픈 UTC 13:30–15:00). 60s 버킷 bucket_ts를 이 창에 통과시켜 killzone 밖이면 무조건 차단.

### 6. 해상도 정렬

트렌드/키레벨은 15분봉 기준, VWAP/오더플로우/killzone은 60s 버킷 기준 — 15분봉 신호를 그 구간에 속한 모든 60s 버킷에 broadcast(forward-fill)해서 정렬.

### 7. 게이트 합성 + 진입

```python
def build_gated_confluence_signals(deltas: list[dict], ticks: list[dict]) -> dict:
    """전체 파이프라인 조립:
    1. build_ohlc_bars(ticks) -> resample_bars(15) -> trend_filter, key_level_filter (15m)
    2. build_vwap_filter(deltas) (60s)
    3. killzone_indices (60s bucket_ts)
    4. 15m 신호 -> 60s로 broadcast
    5. bias = trend/key_level/vwap 3개 전부 같은 방향이면 그 방향, 아니면 HOLD
    6. 기존 confluence(footprint/absorption/cvd 2/3 다수결) 계산(이미 있는 build_confluence_signals 재사용)
    7. bias!=HOLD and killzone 안 and confluence==bias -> 그 방향 신호, 아니면 HOLD
    반환 형태는 다른 build_*_signals와 동일: {"closes","signals","eligible"} —
    eligible = bias 계산 가능했던 구간(15분봉 warmup 지난 이후) 전체(신호 뜬 곳만 아님)."""
```
`research/run_orderflow_futures_on_btc.py`의 `build_confluence_signals`를 이 모듈로 이동(신규 모듈이 confluence에 의존하므로) — import 경로만 바뀜, 로직 변경 없음.

### 8. 검증

기존 엔진 그대로: `simulate_long_short`/`trade_metrics`/`random_same_frequency`/`empirical_p_value`, HL 비용모델(`hl_effective_cost_bps("major", taker=True)`). BTC/ETH 각 1개 p-value -> 신규 독립 가설 2개로 `benjamini_hochberg` 별도 풀(이전 14개 배치와 안 섞음 — 사후에 만든 새 가설을 이전 배치에 합치면 그 배치의 "사전에 고정된 가설셋" 해석이 깨짐).

## 테스트 계획

`tests/test_orderflow_context_gate.py` 신규:
- `build_ohlc_bars`: 버킷 경계, 고저 정확성
- `resample_bars`: factor=15 그룹핑, o/h/l/c 정확성
- `build_trend_filter`: BOS 발생 후 forward-fill 확인, 이벤트 전 HOLD 확인
- `build_key_level_filter`: proximity 안/밖 케이스
- `build_vwap_filter`: window 안/밖 케이스, close>VWAP/<VWAP
- `build_gated_confluence_signals`: 3필터 전부 일치+killzone 안+confluence 일치 -> 신호; 하나라도 불일치 -> HOLD; killzone 밖 -> HOLD

## 파일 변경 요약

- 신규: `research/hypotheses/orderflow_context_gate.py`
- 신규: `tests/test_orderflow_context_gate.py`
- 수정: `research/run_orderflow_futures_on_btc.py` — `build_confluence_signals` 제거(모듈로 이동), gated 신호 실행 추가, 신규 BH-FDR 풀 별도 출력

## 스코프 밖

- NQ/MNQ 이식(원시틱 미저장 구조라 별개 결정 필요)
- POC/value area(VWAP만으로 우선 검증)
- ICT 프리셋(OTE/Unicorn/iFVG/CISD/SMT) 재투입 — 이미 사망 확정
- 파라미터 튜닝/그리드서치 — 여기 적힌 고정값 그대로 1회 검증, 결과 보고 바꾸지 않음
