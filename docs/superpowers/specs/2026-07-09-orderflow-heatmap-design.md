# 오더플로우(풋프린트) + 유동성 히트맵 — 백엔드 데이터 파이프라인

**상태:** 설계 승인됨, 플랜 작성 대기
**관련 스펙:** `seokminal-dashboard/docs/superpowers/specs/2026-07-09-orderflow-heatmap-design.md` (프론트엔드, 이 스펙의 WS 계약을 소비)

## 목적

Hyperliquid + IBKR에서 실시간 L2 오더북 + 체결 데이터를 받아 풋프린트(가격×시간버킷 매수/매도량)와 유동성 히트맵(가격×시간 잔량) 데이터로 집계, WS로 프론트에 델타 스트리밍한다. 페이퍼매매 실행 로직과는 완전히 격리 — 이 기능이 죽어도 매매 실행에 영향 없어야 함.

## 파일럿 스코프 (v1)

- Hyperliquid: `BTC.HL`
- IBKR: `NQ` (나스닥 미니 선물)
- 심볼 1개씩만 동시 수집 (멀티 심볼 동시 수집은 스코프 아웃)

## 아키텍처

```
orderflow/                      ← 신규 격리 모듈. 매매 실행 코드와 공유 상태 없음
├── models.py                   OrderBookSnapshot, TradeEvent, FootprintCell, HeatmapCell (pydantic)
├── tick_rule.py                Lee-Ready 체결 방향 분류 (IBKR용)
├── hl_adapter.py                Hyperliquid WS 신규 클라이언트 (L2Book + trades 구독)
├── ib_adapter.py                기존 IBClient(ib_async) 확장 — 심볼별 지속 연결로 reqMktDepth + reqTickByTickData(Last, BidAsk) 동시 구독
├── aggregator.py                롤링 버퍼: footprint(1분 버킷 기본값), heatmap(2초 버킷 기본값). 델타 생성
└── manager.py                   심볼별 수집 task 감독. 재연결 백오프. try/except로 예외 흡수 — 앱 전체에 전파 안 함

api_server/router_orderflow.py   REST(GET /orderflow/symbols) + WS(/ws/orderflow/{symbol})
                                  main.py에 라우터 등록만. 실행엔진(live_engine 등)과 임포트/상태 공유 없음
```

### 격리 원칙

- `orderflow/` 모듈은 `live_engine`, 봇 실행 로직, 주문 실행 코드를 import하지 않는다 (단방향 의존 금지 — 반대도 마찬가지).
- `manager.py`의 수집 task는 개별 `try/except`로 감싸 실행 — 한 심볼의 어댑터가 죽어도 다른 심볼/앱 전체는 안 죽음.
- 기존 `IBClient`(`backends/ib/client.py`)의 `stream_trades()`는 건드리지 않는다. `ib_adapter.py`는 이를 확장하는 새 진입점(심볼별 지속 연결 + `reqMktDepth`/`BidAsk` 추가 구독)이며, 기존 호출부에 영향 없음.

## 데이터 모델

```python
# orderflow/models.py
class OrderBookLevel(BaseModel):
    price: float
    size: float

class OrderBookSnapshot(BaseModel):
    symbol: str
    ts: float                     # epoch seconds
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]

class TradeEvent(BaseModel):
    symbol: str
    ts: float
    price: float
    size: float
    side: Literal["buy", "sell"]  # HL: payload의 buyer/seller로 결정. IBKR: tick_rule로 결정

class FootprintCell(BaseModel):
    bucket_ts: float              # 버킷 시작 시각
    price: float                  # 가격 레벨 (심볼별 tick size로 라운딩)
    buy_vol: float
    sell_vol: float

class HeatmapCell(BaseModel):
    ts: float
    price: float
    size: float                   # 해당 시점 해당 가격의 잔량(주문북 depth)
```

## 체결 방향 분류 (IBKR)

```python
# orderflow/tick_rule.py
def classify(price: float, bid: float, ask: float) -> Literal["buy", "sell"]:
    """Lee-Ready 근사. price >= ask -> buy(공격적 매수), price <= bid -> sell.
    중간이면 mid 기준(price >= mid -> buy)."""
```

Hyperliquid는 `trades` 페이로드에 `users: [buyer, seller]`가 있어 이 분류기를 타지 않고 그대로 사용한다.

## IBKR 어댑터 — 지속 연결

기존 `IBClient`는 호출 단위로 연결(connectAsync)한다. `ib_adapter.py`는 심볼 하나당 **하나의 지속 연결**을 열고 그 위에서:
- `reqMktDepth(contract)` — L2 오더북
- `reqTickByTickData(contract, "Last")` — 체결 (기존 `stream_trades`가 쓰는 것과 동일 API, 별도 연결)
- `reqTickByTickData(contract, "BidAsk")` — tick_rule 분류용 best bid/ask

세 구독을 동시에 유지. 연결이 끊기면 `manager.py`가 지수 백오프로 재연결 (심볼 하나 재연결이 다른 심볼에 영향 없음 — 연결은 심볼별로 독립).

## 집계 (aggregator.py)

- **풋프린트**: 1분 버킷(설정 가능한 상수, 기본 60s) × 가격 레벨(심볼 tick size로 라운딩). 체결 이벤트 하나마다 해당 버킷/가격 셀의 `buy_vol`/`sell_vol`에 가산, 델타로 emit.
- **히트맵**: 2초 버킷(설정 가능, 기본 2s) × 가격 레벨. 오더북 스냅샷마다 해당 시점의 잔량을 기록, 델타로 emit.
- 메모리 내 롤링 윈도우만 유지 (기본 최근 2시간). 디스크 영속화 없음 — v1은 라이브 전용, 히스토리 재생 스코프 아웃.

## WS 계약 (`/ws/orderflow/{symbol}`)

연결 시 스냅샷 1회, 이후 델타만 push:

```json
{"type":"snapshot","symbol":"BTC.HL","footprint":[FootprintCell,...],"heatmap":[HeatmapCell,...]}
{"type":"footprint_delta","bucket_ts":1720000000,"price":65000,"side":"buy","delta_vol":0.12}
{"type":"heatmap_delta","ts":1720000002,"price":65010,"size":3.4}
{"type":"status","state":"reconnecting"}
{"type":"status","state":"live"}
```

`symbol` 파라미터가 `.HL` 접미사면 `hl_adapter`, 아니면 `ib_adapter`로 라우팅 (기존 프론트 심볼 접미사 컨벤션과 동일).

## REST 계약

`GET /orderflow/symbols` — 현재 `manager`가 활성 수집 중인 심볼 목록 반환 (디버그/상태 확인용).

## 에러 처리

- HL/IBKR WS(or TWS 연결) 끊김 → 지수 백오프 재연결. `research/polymarket_tick/ws_collector.py`의 백오프 패턴 재사용.
- 재연결 중에는 WS 클라이언트들에게 `{"type":"status","state":"reconnecting"}` broadcast.
- 어댑터 예외는 `manager.py`에서 흡수·로깅, 앱 프로세스에 전파되지 않음.

## 테스트 계획

- `tick_rule.classify()` — 테이블 기반 단위 테스트 (price/bid/ask 조합별 buy/sell/mid 케이스).
- `aggregator` 버킷 롤업 — 체결/스냅샷 시퀀스 주입 → 셀 값·델타 검증.
- `manager` 재연결 백오프 — mock 어댑터로 연결 끊김 시뮬레이션, 백오프 타이밍/횟수 검증.
- 기존 `IBClient`/`stream_trades` 관련 기존 테스트 회귀 없음 확인.

## 스코프 아웃 (v1)

- 멀티 심볼 동시 수집
- 히스토리 저장/재생 (디스크 영속화 없음, 라이브 전용)
- IBKR market data 구독 설정 자체 (사용자 책임 — TWS/게이트웨이 쪽 구독 세팅은 코드로 다루지 않음)
- 심볼 간 UI 스위칭 시 백엔드 자동 구독 전환 (수동 REST/WS 연결 기준)
