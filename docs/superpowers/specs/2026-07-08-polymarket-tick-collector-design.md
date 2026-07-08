# Polymarket 실시간 틱 수집기 — 모멘텀/오버리액션 가설 1단계 (데이터만)

**작성일:** 2026-07-08
**상태:** 설계 승인됨 → 구현 계획 대기
**로드맵 위치:** 기존 `polymarket_arb`(합가격 차익, 별도 트랙)와 무관한 신규 트랙. "확률이 초단위로 요동치는 라이브 이벤트 구간에서 짧게 치고 빠지는 전략" 가설의 1단계 — 이번 스펙은 전략/판정 로직 없이 **데이터 수집기만** 만든다. 가설 검증(random baseline p-value + walk-forward + cost-robust)은 데이터가 몇 주 쌓인 뒤 별도 spec에서.

## 목표 (한 줄)

라이브 인플레이 스포츠 마켓과 속보성 이벤트 마켓의 확률을 CLOB WSS로 실시간 구독해 틱 단위로 적재한다. 기존 `polymarket_arb/collector.py`(REST 10초 폴링, 유동성 top-N 필터)는 월드컵 우승·NBA 파이널 같은 장기 시즌 마켓만 잡혀 확률이 거의 안 움직인다 — 이번 수집기는 그 반대, 틱 밀도가 높은 마켓만 골라서 잡는다.

## 배경 / 제약

- 확인됨: Gamma API 마켓 객체에 `sportsMarketType`(예: `soccer_halftime_result`) + `gameStartTime` 필드 존재 — 이걸로 라이브 스포츠 마켓 식별 가능. `polymarket/client.py::_map_market()`은 현재 이 필드들을 버리고 있어 추가 매핑 필요.
- 과거 틱 데이터 자체가 없음 — 사후분석 불가능, 지금부터 라이브 수집만 가능. `polymarket_arb`의 "과거 오더북 데이터 못 구함" 제약과 동일 성격.
- CLOB에는 공개 WSS(`wss://ws-subscriptions-clob.polymarket.com/ws/market`)가 있음 — `book`/`price_change` 이벤트를 `asset_id`(token_id) 구독으로 받음, 인증 불필요. 기존 `polymarket_arb`는 REST 폴링만 썼고 WSS는 이번이 처음 — 새 의존성(websocket 클라이언트 라이브러리, 이미 `requirements`에 있는지 확인 필요).
- 프로덕션 페이퍼봇(`api_server/polymarket_bot.py`)과 완전히 분리 — 검증 전까지 손대지 않는다 (하우스 규율, `polymarket_arb` 스펙과 동일).
- 이번 단계는 방향(모멘텀 추종 vs 오버리액션 페이드) 미확정 — 둘 다 나중에 같은 틱 데이터로 검증한다. 수집기는 방향에 무관하게 원시 틱만 쌓는다.

## 아키텍처

```
research/
  polymarket_tick/
    __init__.py
    market_selector.py   ← 대상 마켓 선정 (순수함수, 입력=마켓 dict 리스트)
    ws_collector.py       ← CLOB WSS 구독 + 틱 적재 (I/O)
  data/polymarket_tick/
    YYYY-MM-DD.jsonl      ← 틱 로그 (날짜별 분할)
run_polymarket_tick_collect.py   ← ws_collector 무한루프 진입점 (tmux로 상시 실행)
tests/test_polymarket_tick_selector.py   ← market_selector 유닛테스트
tests/test_polymarket_tick_collector.py  ← ws_collector 유닛테스트 (WSS 페이크 클라이언트)
```

### 데이터 흐름

```
Gamma API get_markets() 주기적 재조회 (기본 5분)
   │  polymarket/client.py::_map_market()에 sports_market_type, game_start_time 필드 추가
   ▼
market_selector.py: 두 family로 분류
   │  - "sports": sports_market_type 있고, game_start_time이 지금 기준 -30분~+4시간 범위(경기 진행 가능 구간)
   │  - "news": sports_market_type 없고, 잔여기간 3일 미만이면서 24h 거래량이 유동성 대비 급증(예: 유동성의 20%↑)
   ▼
대상 token_id 집합 갱신 (신규 구독 추가, 종료/이탈 마켓 구독 해제)
   ▼
ws_collector.py: CLOB WSS market 채널 구독, book/price_change 이벤트 수신마다 그대로 적재
   ▼
research/data/polymarket_tick/YYYY-MM-DD.jsonl 에 매틱 append
   │  필드: ts, condition_id, question, family(sports|news), token_id, side(yes|no), price, size, event_type(book|price_change)
   ▼
(수집 몇 주 후, 별도 spec) 모멘텀/오버리액션 가설 검증 — random baseline p-value + walk-forward + cost-robust
```

## 감시 대상 선정

`market_selector.py`는 Gamma API 마켓 dict 리스트를 입력받아 두 그룹으로 나누는 순수함수:

- **sports**: `sports_market_type`이 non-null이고 `game_start_time`이 `[now-30min, now+4h]` 구간 — 경기 시작 직전부터 종료 예상 시점까지. 30분/4시간은 기본값, 구현 계획에서 실측 후 조정 가능하게 config화.
- **news**: `sports_market_type`이 null, `end_date`까지 3일 미만, 그리고 직전 관찰 대비 거래량이나 유동성이 급증한 마켓(급증 판정 기준은 구현 계획에서 첫 폴링 데이터 보고 정함 — 임의로 못 박지 않음).

두 그룹 다 `min_liquidity` 하한(기본 `polymarket_arb`와 동일 5000)은 유지 — 오더북이 텅 빈 마켓은 틱이 아니라 노이즈.

## 수집 주기 / 저장 형식

- 마켓 재선정(Gamma REST): 5분 주기.
- 틱 자체는 WSS push 기반 — 폴링 주기 없음, 이벤트 도착하는 대로 적재.
- jsonl append, 날짜별 파일 분할, 저장 위치 `research/data/polymarket_tick/`(`polymarket_arb`와 같은 선상, 프로덕션 로그와 분리).
- 컬렉터 재시작 시 구독 목록은 매번 market_selector로 새로 계산 — 내부 상태 없음, 유실 구간만 생기고 꼬이지 않음 (`polymarket_arb`와 동일 설계 철학).

## 에러 처리

- WSS 연결 끊김 → 지수 백오프 재연결 (`polymarket/client.py::_get`의 재시도 패턴을 WSS reconnect에 맞게 재사용).
- 마켓 종료/청산 → 다음 5분 재선정 사이클에서 자연히 구독 목록에서 빠짐, 명시적 해제 로직 필요(WSS 구독 해제 메시지 전송).
- Gamma REST 재선정 실패 → 기존 구독 유지, 다음 주기에 재시도 (구독 자체는 끊지 않음).

## 테스트

- `market_selector.py`: 순수함수라 페이크 마켓 dict(다양한 game_start_time/거래량 조합) 넣고 sports/news 분류 경계값 유닛테스트.
- `ws_collector.py`: WSS 클라이언트 페이크(mock)로 book/price_change 메시지 주입 → jsonl 적재 로직 테스트, 실제 네트워크 연결 없이.

## 스코프 밖 (다음 spec)

- 모멘텀 추종 vs 오버리액션 페이드 가설 검증 — 데이터 몇 주 쌓인 뒤 별도 spec→plan.
- 실주문 체결 — 페이퍼 검증 통과 전까지 다루지 않음.
- `polymarket_arb`(차익거래) 트랙과의 통합 — 별개 트랙으로 유지.
