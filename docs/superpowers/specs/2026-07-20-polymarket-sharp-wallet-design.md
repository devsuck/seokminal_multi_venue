# Polymarket Sharp-Wallet Convergence — Design Spec

**작성:** 2026-07-20. 브레인스토밍 중 확정, 사용자 승인 완료.

## 1. 배경

SNS 스캠 광고("고래찾기" 봇 마케팅 영상) 검토 중 나온 파이프라인 중 "Cluster
operators / Cross-market dedup / Detect convergence" 단계에서 아이디어만 추출:
과거 적중률 좋은("샤프") 지갑이 새 포지션을 잡을 때, 특히 여러 샤프월렛이 비슷한
시점에 동시에 움직일 때 그게 forward return과 상관 있는지 검증한다.

기존 whale-tracking(`docs/superpowers/specs/2026-07-13-polymarket-whale-tracking-design.md`)과
차이: whale은 "체결 사이즈"가 신호, 이건 "누가 체결했는지"가 신호. 처음엔 지갑별
과거 적중률을 우리가 직접 쌓으려 했으나(주 데이터: `research/data/polymarket_whale/`),
실측 결과 7일치 4277건 기준 distinct wallet 2268개 중 5건 이상 거래한 지갑이 115개뿐
— 지갑당 표본이 너무 얇아 자체 트랙레코드 구축은 몇 주가 더 필요했다.

**전환:** Polymarket 공식 리더보드 API(`https://data-api.polymarket.com/v1/leaderboard`,
무인증)가 전체기간 PnL 기준 트레이더 랭킹을 이미 제공한다(확인 완료, `docs.polymarket.com`
API 레퍼런스). 이걸 그대로 "샤프월렛" 명단으로 쓴다 — 우리가 트랙레코드를 새로
쌓을 필요가 없다.

## 2. 가설

Polymarket 전체기간 PnL 상위 50명(공식 리더보드) 중 한 명이 새 포지션(notional
≥$50)을 잡으면, 그 방향으로 이후 가격이 선행 이동하는가. 같은 트레일링 윈도우
안에 다른 샤프월렛이 몇 명 더 동시에 움직였는지(컨버전스 카운트, 마켓 무관 —
크로스마켓)를 그룹 변수로 둬서, 컨버전스가 강할수록 신호가 강해지는지도 함께
스크리닝한다. 대칭 가설(양방향 동일 검정), 방향 사전지정 없음 — whale과 동일 형식.

## 3. 리더보드 소스

- 엔드포인트: `GET https://data-api.polymarket.com/v1/leaderboard`
- 파라미터: `category=OVERALL`, `timePeriod=ALL`(반짝 운 아니라 전체기간 실력),
  `orderBy=PNL`, `limit=50`, `offset=0`
- 응답에서 쓰는 필드: `rank`, `proxyWallet`, `pnl`, `vol`
- **결정: 상위 50명 고정.** `limit` API 상한이 50(1-50 범위, 문서 확인)이라
  offset 페이지네이션으로 더 넓힐 수도 있지만 v1은 top 50만 — 표본이 부족하면
  다음 이터레이션에서 넓힌다.

## 4. 아키텍처 (5계층, 기존 whale 패턴 확장)

```
research/polymarket_sharp_wallet/leaderboard.py    ← 리더보드 조회(순수함수)
research/run_polymarket_sharp_wallet_collect.py     ← 수집기(REST 폴링, tmux 상시실행)
research/hypotheses/polymarket_sharp_wallet.py      ← 가설 모듈(순수함수)
research/run_polymarket_sharp_wallet_validate.py    ← 검증 러너(p-value/BH-FDR)
api_server/lab_api.py + 프론트 HUD                  ← 상태 등록(whale과 동일 패턴)
```

## 5. 리더보드 모듈 (`research/polymarket_sharp_wallet/leaderboard.py`)

```python
LEADERBOARD_URL = "https://data-api.polymarket.com/v1/leaderboard"
LEADERBOARD_CATEGORY = "OVERALL"
LEADERBOARD_TIME_PERIOD = "ALL"
LEADERBOARD_LIMIT = 50
```

- `fetch_leaderboard() -> list[dict]`: 위 상수로 GET 요청, 응답 리스트 그대로
  반환(`rank`, `proxyWallet`, `pnl`, `vol`만 남기고 나머지 필드는 버림).
- `build_sharp_wallet_set(entries: list[dict]) -> dict[str, dict]`:
  `proxyWallet(lowercase) -> {rank, pnl}` 매핑. 대소문자 비교 문제 방지를 위해
  키는 항상 `.lower()`.

## 6. 수집기 (`run_polymarket_sharp_wallet_collect.py`)

whale 수집기와 동일한 무한루프+폴링 골격(`/trades` 글로벌 피드, 5초 폴링,
transactionHash 기반 dedup, try/except 사이클스킵)을 재사용하되 **필터 기준이
다르다**: 마켓 family가 아니라 "이 체결의 지갑이 샤프월렛인지".

```python
POLL_INTERVAL_S = 5.0                     # whale 수집기와 동일값(공개 API 예의상 하한)
LEADERBOARD_REFRESH_INTERVAL_S = 86400.0  # 1일 1회 — PnL 랭킹은 느리게 변함
MIN_NOTIONAL_USD = 50.0                   # 이 미만 체결은 먼지거래로 간주, 저장 안 함
MAX_HORIZON_S = 300.0                     # research.hypotheses.polymarket_sharp_wallet.HORIZONS_S의
                                           # 최댓값과 반드시 일치시킬 것(가설 모듈과 독립 선언 —
                                           # 컬렉터/가설 모듈 분리 컨벤션, whale과 동일 이유)
DEDUP_HASH_RING_SIZE = 5000               # whale(2000)보다 큼 — context 체결까지 저장해 볼륨이 큼
```

**왜 컨텍스트 체결까지 저장하는가:** forward-return 계산엔 각 마켓의 조밀한
가격 시계열이 필요하다. 샤프월렛 체결만 저장하면 마켓당 표본이 1건뿐인 경우가
대부분이라(50명 지갑이 특정 마켓에 동시에 다 몰릴 리 없음) ffill 리샘플이 사실상
"영원히 anchor 가격 고정"이 되어 forward return이 항상 0으로 나온다 — whale은
family 전체를 통째로 저장해서 이 문제가 없었지만, 여기는 지갑 50개로 스코프가
좁아서 같은 문제가 재발한다.

**해결:** 샤프월렛 체결이 마켓 X에서 감지되면, 그 시점부터 `MAX_HORIZON_S`초
동안 마켓 X의 **모든** 체결(지갑 무관)을 "컨텍스트 체결"로 같이 저장해 가격
시계열을 조밀하게 만든다.

- 상태: `watch_until: dict[condition_id, float]` — 샤프월렛 체결 감지 시
  `watch_until[cid] = trade_ts + MAX_HORIZON_S`로 갱신(연장 포함). 매 폴링마다
  `watch_until[cid] < now - MAX_HORIZON_S`인 항목은 정리(무한 성장 방지).
- 폴링당 처리 로직:
  ```python
  for t in trades:
      cid = t["conditionId"]
      wallet = t["proxyWallet"].lower()
      notional = t["size"] * t["price"]
      sharp = sharp_wallets.get(wallet)  # dict{rank,pnl} 또는 None
      is_anchor = sharp is not None and notional >= MIN_NOTIONAL_USD
      is_context = cid in watch_until and t["timestamp"] <= watch_until[cid]
      if not (is_anchor or is_context):
          continue
      if is_anchor:
          watch_until[cid] = t["timestamp"] + MAX_HORIZON_S
      # dedup(transactionHash) 통과 후 저장
      record = {**t, "notional_usd": notional, "is_sharp_wallet": is_anchor,
                "wallet_rank": sharp["rank"] if sharp else None,
                "wallet_pnl": sharp["pnl"] if sharp else None}
  ```
- 저장 경로: `research/data/polymarket_sharp_wallet/{date}.jsonl`
- tmux 세션명: `polymarket-sharp-wallet-tick`
- **HUD 등록 필수** — whale spec 5절과 동일 이유(수집기가 죽어도 티가 안 나는
  문제 재발 방지). `api_server/lab_api.py`의 `COLLECTOR_SESSIONS`에
  `"polymarket_sharp_wallet_tick": _tmux_process_status("polymarket-sharp-wallet-tick", "research/data/polymarket_sharp_wallet")`
  추가, `lib/api.ts` + `app/hud/page.tsx`에 유닛카드 추가.

## 7. 가설 모듈 (`research/hypotheses/polymarket_sharp_wallet.py`)

```python
CONVERGENCE_WINDOW_S = 600.0   # 10분 — 여러 샤프월렛을 "동시 진입"으로 볼 트레일링 윈도우
MAX_CONVERGENCE_BUCKET = 3     # 3 이상은 전부 "3" 버킷으로 캡(그 이상은 표본 희소 예상)
RESAMPLE_GRID_S = 5.0          # 수집기 폴링주기와 동일
HORIZONS_S = [30, 120, 300]    # whale과 동일값(30s/2min/5min)
```

- `load_sharp_wallet_trades(dates) -> list[dict]`: jsonl 로드, ts 오름차순 정렬.
  (`notional_usd`, `is_sharp_wallet`은 이미 수집기가 붙여 저장 — 재계산 안 함.)
- `build_convergence_count(trades) -> list[dict]`: `is_sharp_wallet=True`인
  행(anchor)만 대상. 각 anchor 시각 t에 대해, **마켓 무관**하게 t-`CONVERGENCE_WINDOW_S`
  ~ t 구간에 체결이 있는 다른 anchor들의 distinct `proxyWallet` 수(자기 자신 포함)를
  `convergence_count`로 기록. `convergence_bucket = min(convergence_count, MAX_CONVERGENCE_BUCKET)`.
- `build_price_series(trades, condition_id) -> list[dict]`: 해당 `condition_id`의
  **모든** 행(anchor+context 구분 없이)을 `RESAMPLE_GRID_S` 그리드로 ffill 리샘플.
  whale과 동일 로직, 입력 필터만 다름(family 대신 condition_id 단일 마켓).
- `build_labels_multi_horizon(anchors, price_series_by_market, horizons=HORIZONS_S) -> list[dict]`:
  각 anchor 이후 각 horizon 시점 forward return을 그 마켓의 price series에서 계산.
  `side`(BUY/SELL)와 raw return 부호를 그대로 기록 — 방향 일치 여부 판정은 검증
  러너 몫(whale과 동일 원칙).

## 8. 검증 러너 (`run_polymarket_sharp_wallet_validate.py`)

whale과 동일 배선(`empirical_p_value`, `benjamini_hochberg`, `trade_metrics`,
`polymarket_effective_cost_bps` — 전부 기존 함수 재사용, 신규 비용모델 불필요).

- 그룹 단위: `convergence_bucket`(1/2/3) × `horizon`(3) = 최대 9개 p-value.
  whale의 family×horizon 축을 convergence_bucket×horizon으로 교체.
- 최소 `MIN_EVENTS=10` 샘플 게이트(기존 컨벤션 값 그대로) — 버킷별 표본 미달 시
  해당 버킷은 BLOCKED로 스킵(whale의 sports family 처리와 동일 패턴).
- 방향 셔플 랜덤베이스라인(`N_RUNS=500`, `SEED=42` — 기존 컨벤션 값).
- BH-FDR: **신규 독립 풀**(convergence_bucket×horizon p-value만, 다른 가설과
  절대 안 섞음 — 프로젝트 전역 규율). `alpha=0.1`.
- Walk-forward 스킵(신규 수집 데이터, 표본 부족 예상) — BH-FDR 통과 시 다음
  이터레이션에서 추가.

## 9. HUD 등록

whale spec 5절과 동일 패턴 — 백엔드 `COLLECTOR_SESSIONS` + 프론트 `lib/api.ts`
`LabStatus.processes` 필드 + `app/hud/page.tsx` 유닛카드. 생략 불가(6절 참조).

## 10. 테스트 계획

- `tests/test_polymarket_sharp_wallet_leaderboard.py`: 리더보드 응답 파싱,
  `build_sharp_wallet_set`의 lowercase 정규화, 빈 응답 처리.
- `tests/test_run_polymarket_sharp_wallet_collect.py`: anchor/context 판정 로직
  (샤프월렛+notional 충족 → anchor, watch_until 안의 비샤프월렛 체결 → context,
  둘 다 아니면 드롭), watch_until 연장, dedup, 오래된 watch_until 정리.
- `tests/test_polymarket_sharp_wallet.py`: 컨버전스 카운트(윈도우 경계, 마켓
  무관 카운트, 버킷 캡), 가격시계열 ffill, 멀티호라이즌 라벨 정합성.
- `tests/test_run_polymarket_sharp_wallet_validate.py`: 최소 스모크 테스트
  (빈 입력 시 verdict 필드 존재, 버킷별 MIN_EVENTS 미달 시 BLOCKED 처리).

## 11. Out of scope

- 실주문/지갑 서명/실집행 — 전부 제외.
- Sybil/운영자 클러스터링(동일 실체가 여러 지갑 쓰는지 탐지) — 검증 불가능한
  추정이라 v1에서 제외. 컨버전스 카운트(여러 distinct 지갑이 동시에 움직이는지)로
  근사한다.
- 리더보드 `category`별 세분화(POLITICS/SPORTS/CRYPTO 등) — v1은 OVERALL만.
  표본 부족하면 다음 이터레이션에서 카테고리 축 추가 검토.
- top 50 밖 지갑(offset 페이지네이션으로 확장) — v1 범위 밖.
