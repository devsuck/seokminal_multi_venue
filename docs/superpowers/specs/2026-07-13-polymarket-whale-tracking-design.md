# Polymarket Whale Tracking — Design Spec

**작성:** 2026-07-13. 사용자가 브레인스토밍 중 취침 진입("허락 맡지말고 쭈욱 작업해놔") —
남은 질문(마켓 스코프/임계값/호라이즌/수집방식)은 기존 코드베이스 컨벤션을 그대로
따라 assistant가 확정. 사용자 리뷰는 기상 후.

## 1. 배경

`polymarket_arb`(가격 재정거래) 트랙은 방금 `REJECT_NO_PERSISTENT_RUNS`로 종료
(10.4만 틱 전수 확인, sum_ask가 1.0 밑으로 내려간 적 0회 — fee_buffer 이전에 이미
차익 없음). 사용자가 다음 후보로 whale tracking을 지목: 큰 체결이 뜬 뒤 가격이
그 방향으로 선행 움직이는지 — `hl_orderflow_tick`/`cross_venue_skew`와 같은 패턴
(체결/오더북 신호 → forward return 라벨 → 랜덤베이스라인 대비 p-value → BH-FDR)을
벤뉴만 Polymarket으로 바꿔 재사용한다.

**중요 발견 (이번 조사):** 기존 `research/polymarket_tick/ws_collector.py`는 CLOB
WSS `market` 채널(`book`/`price_change` 이벤트)만 구독 — 오더북 델타만 있고 실제
체결(size, 지갑주소, 방향)이 없다. Whale tracking엔 이 데이터를 못 쓴다. 새 수집기가
필요하고, 데이터 소스는 Polymarket **Data-API** `GET https://data-api.polymarket.com/trades`
(공개, 무인증, 확인 완료 — `curl`로 라이브 응답 200 받음). 필드: `proxyWallet, side,
asset(token_id), conditionId, size(주식수, USD 아님), price, timestamp(unix),
title, slug, outcome, name, transactionHash`.

## 2. 가설

Polymarket 특정 마켓에서 노션(size × price, USD 환산) 기준 이상치급 체결이 발생하면,
그 체결 방향(buy=YES/NO 매수)으로 이후 가격이 선행 이동하는가. 대칭 가설(양방향
동일 검정), 방향 사전지정 없음 — `cross_venue_skew`의 spike→forward-return 패턴과
동일한 형식.

## 3. 마켓 스코프

전체 글로벌 `/trades` 피드는 라이브 샘플링 결과 "Bitcoin Up or Down — 5min/15min"류
초단기 크립토 마켓이 최고빈도를 차지 — 가격 갱신 패턴이 정보 기반 베팅이 아니라
자동화 마켓메이커/봇 플로우로 보임(수 초 단위 반복 체결, 방향 무근거 반전). "큰돈
= 정보 우위"라는 whale-tracking 전제가 이 마켓군엔 안 맞는다.

**결정:** 기존 `research/polymarket_tick/market_selector.select_target_markets()`를
그대로 재사용해 뉴스/스포츠 패밀리로 스코프를 좁힌다(유동성≥5000, 스포츠는 경기
시작 -30분~+4시간, 뉴스는 잔여만기<3일 — 이미 코드에 있는 정확한 값, 복제 없이
import). 초단기 크립토 updown 마켓은 이 필터를 통과 못 하므로 자동 제외된다.
추가 필터 로직 불필요 — 기존 순수함수 재사용이 DRY에도 맞는다.

## 4. 아키텍처 (3계층, 기존 cross_venue_skew 패턴 그대로)

```
research/run_polymarket_whale_collect.py   ← 수집기(REST 폴링, tmux 상시실행)
research/hypotheses/polymarket_whale.py    ← 가설 모듈(순수함수, load→feature→label)
research/run_polymarket_whale_validate.py  ← 검증 러너(p-value/BH-FDR)
```

## 5. 수집기 (`run_polymarket_whale_collect.py`)

- **폴링, WSS 아님** — Data-API에 체결 전용 WSS가 없음(확인됨, market 채널은
  오더북 전용). `run_cross_venue_skew_collect.py`의 무한루프+백오프 골격은 유지하되
  스트림 대신 폴링으로 교체.
- 폴링 주기: **5초.** 공개 API 예의상 하한(rate limit 문서 없음, 보수적으로 잡음).
- 대상 마켓 목록: Gamma API(`polymarket/client.py`의 `get_markets`)로 5분마다
  재조회 → `select_target_markets()` 통과분의 `condition_id` 집합을 갱신. 폴링마다
  Gamma를 다시 부르지 않음(무거움) — 별도 저빈도 루프.
- 글로벌 `/trades` 응답을 받아 `condition_id`가 대상 집합에 있는 행만 필터링 후
  저장. (마켓별 개별 폴링은 대상마켓 수만큼 요청이 늘어나 비효율 — 글로벌 1회
  폴링 후 로컬 필터가 낫다.)
- 중복 제거: `transactionHash` 기준. 폴링 커서로 `last_seen_ts`(직전 폴링에서 관측한
  최대 timestamp)를 유지 → 이보다 오래된 행은 스킵, 동일 timestamp 내 중복은
  `transactionHash` set(최근 2000개 유지, 링버퍼)으로 걸러 재현(replay) 방지.
- 저장 경로: `research/data/polymarket_whale/{date}.jsonl` (cross_venue_skew와
  같은 날짜별 파일 컨벤션). 원본 필드 그대로 저장 — 가공은 가설 모듈에서.
- tmux 세션명: `polymarket-whale-tick` (기존 `polymarket-tick`, `polymarket-arb`,
  `cross-venue-skew-tick`과 동일 네이밍 컨벤션).
- **HUD 등록 필수** — 이번 세션에 이미 고친 `_tmux_process_status` 패턴 그대로:
  `api_server/lab_api.py`의 `processes` dict에
  `"polymarket_whale_tick": _tmux_process_status("polymarket-whale-tick", "research/data/polymarket_whale")`
  추가, `lib/api.ts`의 `LabStatus.processes`에 필드 추가, `app/hud/page.tsx`에
  유닛 카드 추가. (이 항목 빠지면 이번에 사용자가 지적한 "안 돌아가는 거 모르는"
  문제가 새 수집기에서 재발한다 — 필수, 생략 불가.)

## 6. 가설 모듈 (`research/hypotheses/polymarket_whale.py`)

`cross_venue_skew.py`와 동일 골격: 고정 상수(설계 시점 동결, 결과 보고 후 변경 금지)
→ `load_*` → feature builder → `align`(불필요 — 단일 벤뉴라 리샘플 정렬 단계 생략,
cross_venue_skew는 벤뉴 간 정렬이 필요했지만 여기는 벤뉴 하나) → spike 신호 →
가격 시계열 → 멀티호라이즌 라벨.

```python
MIN_LIQUIDITY = 5000.0  # market_selector.MIN_LIQUIDITY와 동일값, import해서 씀(복제 금지)
NOTIONAL_ZSCORE_LOOKBACK = 100   # 트레이드 개수 기준(시간 기준 아님) — 마켓별 체결빈도 편차 커서
NOTIONAL_ZSCORE_WARMUP = 20      # 이 미만 샘플이면 z-score 미계산(스킵)
WHALE_ZSCORE_THRESHOLD = 2.0     # cross_venue_skew.SPIKE_ZSCORE_THRESHOLD와 동일값 재사용(컨벤션 일치)
RESAMPLE_GRID_S = 5.0            # 수집기 폴링주기와 동일 — 이보다 촘촘한 그리드는 의미 없음
HORIZONS_S = [30, 120, 300]      # 30s/2min/5min — REST 5s 폴링 해상도에서 노이즈와 분리 가능한 최소 스케일
```

- `load_whale_trades(dates, family=None) -> list[dict]`: jsonl 로드, `size*price`로
  `notional_usd` 컬럼 추가.
- `build_notional_zscore(trades) -> list[dict]`: `condition_id`별로 그룹핑,
  `NOTIONAL_ZSCORE_LOOKBACK` 롤링 윈도우로 notional z-score 계산(웜업 미만 스킵).
- `build_spike_signal(trades_with_z) -> list[dict]`: `abs(z) >= WHALE_ZSCORE_THRESHOLD`인
  행만 통과, `direction = "buy" if side=="BUY" else "sell"`을 그대로 라벨 방향 기준으로
  붙임(사전 방향 가정 없음 — 그냥 체결 side 기록, forward return과 상관 있는지는
  검증 러너가 판정).
- `build_price_series(trades, condition_id) -> list[dict]`: 해당 마켓의 체결가를
  `RESAMPLE_GRID_S` 그리드로 ffill 리샘플(그리드 하나짜리 벤뉴라 `align_venues`류
  as-of 정렬 불필요, 단순 ffill).
- `build_labels_multi_horizon(spikes, price_series, horizons=HORIZONS_S) -> list[dict]`:
  각 spike 이후 각 호라이즌 시점 forward return 계산, `side`(buy/sell)와 raw return
  부호를 그대로 기록(방향 일치 여부는 검증 러너의 p-value 단계에서 처리).

## 7. 검증 러너 (`run_polymarket_whale_validate.py`)

`run_cross_venue_skew_validate.py`와 동일 배선: `research/validation/baselines.empirical_p_value`,
`research/validation/multiple_testing.benjamini_hochberg`, `research/validation/metrics.trade_metrics`.

- 그룹 단위: family(news/sports) × horizon — cross_venue_skew의 coin×horizon 자리를
  대체. 최소 `MIN_EVENTS=10` 샘플 게이트(기존 컨벤션 값 그대로).
- 비용 모델 신규 필요 — Polymarket 전용 함수가 `cost_model.py`에 없음. 추가:
  ```python
  # ── Polymarket 예측시장 전용 ──────────────────────────────────────────────
  # ⚠️ 미검증 근사치. 공식 수수료 0%(2026-07 기준, Polymarket은 트레이딩 수수료
  # 없음 — 대신 스프레드가 사실상 비용) — paper 단계 진입 전 재확인 필수.
  POLYMARKET_TAKER_BPS = 0.0
  POLYMARKET_SPREAD_BPS = 200.0  # 유동성≥5000 컷 통과 마켓 기준 보수적 근사

  def polymarket_effective_cost_bps(spread_bps: float = POLYMARKET_SPREAD_BPS) -> float:
      return POLYMARKET_TAKER_BPS + spread_bps / 2.0
  ```
  (IB futures 커미션 섹션의 "미검증 근사치, 재확인 필요" 경고 패턴을 그대로 따름.)
- BH-FDR: **신규 독립 풀**(family×horizon p-value만, 다른 가설과 절대 안 섞음 —
  프로젝트 전역 규율). `alpha=0.1` 기존 값 그대로.
- Walk-forward는 이번에도 스킵(신규 수집 데이터라 샘플 부족) — BH-FDR 통과하면
  다음 이터레이션에 추가, `cross_venue_skew`와 동일 순서.

## 8. "1초마다 돈버는 봇" 요청에 대한 스코핑 결정

사용자 원문: "이거 그냥 고래찾기도 하고, 그 1초마다 돈 버는 그 봇도 만들고싶어.
(아마 차익매매겠지?)" — 사용자 본인도 "아마"로 불확실하게 표현.

**결정: 이번 야간 작업 범위엔 실집행 봇을 포함하지 않는다.** 대신 "1초마다 돈버는
+ 아마 차익매매"라는 표현이 가리키는 가장 근접한 검증 가능 가설 —
**초단기 크립토 updown 마켓(Bitcoin Up/Down 5min/15min)의 진짜 차익거래 존재 여부**
— 를 별도 트랙으로 조사한다. 근거:

1. `polymarket_arb` REJECT는 4일치 뉴스/스포츠 마켓 데이터 기준이었고, 정확히
   이 초단기 크립토 마켓군을 포함했는지 미확인 — 재확인 가치 있음. 기존
   `research/polymarket_arb/detector.py`(`evaluate_snapshot` 순수함수)를 그대로
   재사용, 수집 스코프만 이 마켓군으로 좁혀 재검증한다.
2. 이건 whale-tracking과 마찬가지로 **순수 리서치**(paper, 실행 없음) — 결과가
   CANDIDATE면 jarvis 감사큐로 제출되어 기존 audit/redteam/permission 게이트를
   그대로 통과해야 하고, 최소 페이퍼 기간(`arm_criteria`, 6개월) 없이는 라이브
   진입 자체가 시스템 구조상 불가능. 이 게이트를 우회하는 코드는 작성하지 않는다.
3. **실행 봇(실제 지갑 서명, 실주문)은 이번 작업 범위에서 명시적으로 제외.**
   "허락 맡지말고 작업해놔"는 이미 승인된 방향(리서치)의 자율 진행을 뜻하는 것으로
   해석 — 실제 자금이 오가는 새 집행 경로 신설은 별개 결정이라 판단, 기상 후
   결과 보고 시 이 판단 근거를 명시한다. (프로젝트 자체가 "AI 자기 집행권한 확장
   불가"를 Jarvis Quant OS의 핵심 설계 목표로 이미 못박아둔 것과 일치하는 선택.)

## 9. 테스트 계획

- `tests/test_run_polymarket_whale_collect.py`: dedup 로직(동일 transactionHash
  재수신 시 스킵), 스코프 필터링(대상 집합 밖 condition_id 제외), 커서 전진.
- `tests/test_polymarket_whale.py`: z-score 웜업 미만 스킵, 임계값 경계(z=1.99
  탈락/z=2.0 통과), 멀티호라이즌 라벨 정합성.
- `tests/test_run_polymarket_whale_validate.py` 또는 기존 validate 러너 테스트
  패턴 따라 최소 스모크 테스트(빈 입력 시 verdict 필드 존재 확인 등).

## 10. Out of scope

- 실주문/지갑 서명/실집행 — 전부 제외(9절 참조).
- 초단기 크립토 updown 마켓의 arb 재검증은 whale-tracking과 **별도 파일**
  (`research/run_polymarket_arb_updown_validate.py` 등, 다음 플랜에서 확정) —
  이 스펙은 whale-tracking 구현만 커버. arb 재검증은 이 스펙 승인 후 별도
  브레인스토밍 없이(작은 재검증 스코프 변경이라 프로세스 씨어터 불필요) 바로
  간단한 플랜으로 진행.
