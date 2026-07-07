# Polymarket 합가격 차익거래 — 리서치 수집·검증 파이프라인 (알파 사냥 1/2)

**작성일:** 2026-07-07
**상태:** 설계 승인됨 → 구현 계획 대기
**로드맵 위치:** "최고의 폴리마켓 배팅 에이전트" 2단계 계획 중 1단계 (같은 마켓 내 YES+NO 합가격 차익). 2단계(Polymarket vs Kalshi 크로스플랫폼 차익)는 별도 spec→plan 사이클.

## 목표 (한 줄)

Polymarket 이진(YES/NO) 마켓에서 `YES ask + NO ask < 1 - 수수료버퍼`인 순간이 **실제로 존재하고, 지속되고, 체결 가능한 크기로 잡을 수 있는지** 라이브 오더북 수집으로 정직하게 검증한다. 실주문 체결(지갑 서명)은 이번 스코프 밖 — 독일에서 Polymarket 계정이 지역차단되어 있어 한국 귀국 후 별도 트랙으로 붙인다.

## 배경 / 제약

- `polymarket/client.py`는 읽기전용, Gamma API(마켓 메타데이터+최종체결가)만 씀. 오더북 bid/ask는 안 줌 — CLOB API(`https://clob.polymarket.com`) 별도 필요.
- 차익거래는 랜덤보다 나은지 보는 방향성 알파(TSMOM류)와 판정 성격이 다르다 — "구조적으로 존재하는가 + 캡처 가능한가"가 기준. 기존 `research/validation/`(random baseline p-value, walk-forward)은 방향성 알파용이라 이번엔 그대로 안 맞고, 지속시간·순마진·빈도 3축으로 별도 게이트를 둔다.
- 과거 오더북 데이터는 API로 못 구함 → 반드시 지금부터 라이브 수집, 사후분석은 그 다음.
- 프로덕션 페이퍼봇(`api_server/polymarket_bot.py`)은 이번 작업과 완전히 분리 — 검증 통과 전까지 손대지 않는다.

## 아키텍처

```
research/
  polymarket_arb/
    __init__.py
    collector.py       ← CLOB 오더북 폴링 1틱 로직 (순수 I/O)
    detector.py         ← sum(ask_yes, ask_no) < 1-버퍼 판정 (순수함수, 입출력 dict)
  data/polymarket_arb/
    YYYY-MM-DD.jsonl    ← 스냅샷 로그 (날짜별 분할)
run_polymarket_arb_scan.py         ← collector 무한루프 진입점 (tmux로 상시 실행)
run_polymarket_arb_validation.py   ← 쌓인 jsonl 읽어 go/no-go 판정 리포트 출력
tests/test_polymarket_arb_detector.py  ← detector 유닛테스트
tests/test_polymarket_arb_collector.py ← collector 유닛테스트 (CLOB 페이크 응답)
```

### 데이터 흐름

```
Gamma API get_markets()
   │  (다각화봇과 동일 필터: min_liquidity/min_price/max_price/min_days_to_resolution)
   ▼
유동성 상위 N개 이진마켓 선정 (기본 N=50)
   │  각 마켓의 clobTokenIds(YES/NO 토큰ID) 추출 — client.py에 필드 추가 필요
   ▼
collector.py: 마켓당 폴링주기(기본 10초)마다 CLOB /book 조회
   │  best_bid/best_ask(YES), best_bid/best_ask(NO) 추출
   ▼
detector.py: sum_ask = yes_ask + no_ask 계산, 버퍼(기본 1%) 적용해 기회 여부 판정
   ▼
research/data/polymarket_arb/YYYY-MM-DD.jsonl 에 매틱 append
   │  필드: ts, condition_id, question, yes_ask, yes_bid, no_ask, no_bid, sum_ask, liquidity, is_opportunity
   ▼
(수집 N주 후) run_polymarket_arb_validation.py
   → 기회별로 연속 유지시간 계산 (같은 condition_id, 연속 tick 동안 is_opportunity=true)
   → 그 순간 유동성 감안 체결가능 마진 추정
   → 주당 발생빈도 집계
   → go/no-go 판정 (아래 기준)
```

## 감시 대상 선정

Gamma API에서 `api_server/polymarket_bot.py`와 동일한 필터(`min_liquidity`, `min_price`~`max_price`, `min_days_to_resolution`) 통과한 이진마켓 중 유동성(`liquidity` 필드) 상위 N개. 기본값 N=50 — 구현 계획 단계에서 CLOB API 레이트리밋 실측 후 조정 가능하게 config화.

`polymarket/client.py::_map_market()`이 현재 `clobTokenIds`를 버리고 있어 이 필드를 결과 dict에 추가해야 한다 (Gamma raw response의 `clobTokenIds`는 JSON 문자열 리스트 — 기존 `outcomes`/`outcomePrices` 파싱과 동일 패턴으로 `_parse_json_list` 재사용).

## 수집 주기 / 저장 형식

- 마켓당 기본 10초 폴링 (설정 가능). 50마켓 × 10초 = 초당 5req 수준, CLOB 공개 엔드포인트 레이트리밋 안에서 조정.
- jsonl append, 날짜별 파일 분할 — 기존 `data/*_bot_log.jsonl` 포맷 철학과 동일선상이나 저장 위치는 `research/data/`(리서치 원자재)로 프로덕션 로그(`seokminal-multi-venue/data/`)와 분리.
- 컬렉터는 매 사이클 top-N을 새로 불러오므로 재시작해도 상태 안 꼬임 (내부 상태 없음, 매 폴링이 독립 스냅샷).

## Go/No-Go 판정 기준

기존 하우스 방식(랜덤 베이스라인 p-value)과 다른 3축 게이트:

1. **지속성**: `sum_ask < 1 - 버퍼` 조건이 **연속 T초 이상**(기본 3초 — 사람/봇이 실제로 주문 두 개 넣을 시간) 유지된 사례만 "잡을 수 있는 기회"로 카운트. 한 틱만 반짝이면 노이즈로 폐기.
2. **순마진**: 그 순간의 실제 체결가능 수량(오더북 사이즈)까지 감안한 마진이 수수료·가스비 추정치를 제하고도 양수인가.
3. **빈도**: 수집기간(기본 2주) 동안 위 조건 만족 사례가 **주당 X회 이상**(기본값은 구현계획에서 첫 수집 결과 보고 정함 — 사전에 임의로 못 박지 않음, 최소 "인프라 유지비 대비 기회비용이 맞는 수준"이 기준). 너무 드물면 REJECT.

세 축 모두 통과해야 `paper_candidate` 승격 검토 — 하나라도 실패하면 REJECT, 결과는 다른 가설들처럼 정직하게 기록.

## 에러 처리

- CLOB API 429/타임아웃 → 재시도+백오프 (`polymarket/client.py::_get`의 기존 패턴 재사용).
- 마켓이 수집 도중 만기/상장폐지 → 다음 사이클의 top-N 재선정에서 자연히 빠짐, 별도 처리 불필요.
- 컬렉터 프로세스 죽음 → tmux/systemd로 재시작 시 이어서 수집 (상태 없는 설계라 유실 구간만 생기고 꼬이지 않음).

## 테스트

- `detector.py`: 순수함수라 페이크 오더북 dict 넣고 기회판정/버퍼 경계값 유닛테스트.
- `collector.py`: CLOB API 페이크 응답(HTTP mock 또는 함수 patch)으로 폴링→파싱→저장 로직 테스트, 실제 네트워크 호출 없이.
- `run_polymarket_arb_validation.py`: 합성 jsonl 데이터로 지속성/마진/빈도 집계 로직 테스트.

## 스코프 밖 (2단계로 분리)

- Polymarket vs Kalshi 크로스플랫폼 차익 — 별도 spec.
- 실주문 체결(지갑 서명, CLOB 주문 API) — 한국 귀국 후 별도 트랙, 이번 스펙은 페이퍼 검증까지만.
