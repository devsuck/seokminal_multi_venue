# 폴리마켓 이벤트 내 후보군 합산 괴리 탐지 — Design Spec

**작성:** 2026-07-20. 발단은 SNS에서 본 "AI 예측봇" 광고 스크린샷("EDGE ENGINE",
"3 shared bets aligned")을 검토하면서 — 광고 자체는 `WALLET: SIMULATED`
표기 등 스캠성이 짙지만, 그 밑에 깔린 아이디어 중 "크로스마켓 괴리 탐지"는
현재 코드베이스에 없는 진짜 신규 기능이라 판단해 별도로 만들기로 함.

## 1. 배경

폴리마켓 관련 기존 모듈은 두 개:
- `research/polymarket_arb/` — **단일 마켓** 자체의 YES+NO 합가격이
  100%(-수수료버퍼)에서 벗어나는지만 본다.
- `research/polymarket_tick/` — sports/news 필터로 고른 마켓의 WSS 틱을
  수집만 한다(판단 로직 없음).

둘 다 "같은 이벤트 아래 묶인 여러 후보 마켓 사이의 관계"는 안 본다. 폴리마켓
Gamma API는 멀티후보 이벤트(예: "누가 우승?")를 후보마다 별도 이진(YES/NO)
마켓으로 쪼개서 노출하는데, 후보들이 상호배타적이므로 이론적으로 YES가격
합은 ~100%(-수수료)에 수렴해야 한다. 이 스프레드가 정량화 가능한 새 시그널.

## 2. 스코프 — "같은 이벤트 내 후보군 합산 괴리"로 확정

`event_id`로 묶인 마켓 그룹의 YES가격 합이 100%에서 벗어난 정도만 다룬다.
서로 다른 이벤트 간의 논리적/통계적 상관관계(예: "Fed 금리인하 확률" vs
"2026 경기침체 확률") 같은 퍼지한 크로스이벤트 분석은 범위 밖 — 수학적
보장이 없고 별도 설계가 필요.

## 3. 아키텍처 — 폴링 스캐너 (기존 `polymarket_arb` 구조 그대로)

```
research/polymarket_event_divergence/
  collector.py                              ← 핵심 로직
research/run_polymarket_event_divergence_scan.py  ← 진입점, JSONL 적재
```

`polymarket_arb`와 형제 디렉토리. 기존 컨벤션대로 다른 research 모듈에서
상수/필터 import 금지 — 필요한 값(`MIN_LIQUIDITY`, `FEE_BUFFER` 등)은
값만 복제하고 "import 금지" 주석을 남긴다.

### 3.1 `collector.py`

```python
MIN_LIQUIDITY = 5000.0       # polymarket_arb/collector.py와 동일값(복제, import 금지)
FEE_BUFFER = 0.01            # 동일
MIN_DAYS_TO_RESOLUTION = 3   # 동일
POLL_INTERVAL_SEC = 30
TOP_N_EVENTS = 50

def group_by_event(markets: list[dict]) -> dict[str, list[dict]]:
    """event_id 기준 그룹핑. 소속 마켓 1개뿐인 이벤트는 제외(비교 대상 없음)."""

def compute_divergence(event_markets: list[dict]) -> dict | None:
    """단일 이벤트의 스냅샷 산출. 필터(유동성 합/active/accepting_orders/
    잔여기간/yes_price 존재) 불통과 시 None."""

def run_once(top_n: int = TOP_N_EVENTS, fee_buffer: float = FEE_BUFFER) -> list[dict]:
    """get_markets() → group_by_event → 이벤트별 compute_divergence
    → |divergence| 내림차순 top_n개 스냅샷 반환."""
```

- `group_by_event`, `compute_divergence`는 순수함수(입력 `list[dict]`,
  네트워크 I/O 없음) — `market_selector.py` 패턴 그대로.
- `run_once`만 `polymarket/client.py::get_markets()`를 호출.

### 3.2 진입점 (`run_polymarket_event_divergence_scan.py`)

`run_polymarket_arb_scan.py`와 동일 구조:

```python
def append_snapshots(snapshots: list[dict]) -> None:
    ...  # research/data/polymarket_event_divergence/{date}.jsonl에 append

def run_forever(poll_interval_sec: float = POLL_INTERVAL_SEC, max_iterations: int | None = None) -> None:
    ...  # run_once() → append_snapshots() → sleep, 반복
```

## 4. 데이터 스키마 (스냅샷 1건)

```json
{
  "ts": "2026-07-20T12:00:00Z",
  "event_id": "12345",
  "event_title": "누가 다음 대선 후보가 될까?",
  "n_markets": 4,
  "yes_sum": 1.07,
  "divergence": 0.07,
  "total_liquidity": 82000.0,
  "markets": [
    {"condition_id": "0xabc...", "question": "후보A 지명될까?", "yes_price": 0.42, "liquidity": 30000.0},
    {"condition_id": "0xdef...", "question": "후보B 지명될까?", "yes_price": 0.35, "liquidity": 28000.0}
  ]
}
```

`divergence = yes_sum - 1.0`. 판단(`|divergence| > fee_buffer`일 때만
"시그널"로 볼지 여부)은 스캐너 책임이 아니라 후속 검증 스크립트 책임 —
`polymarket_arb` / `run_polymarket_arb_validation.py`와 동일 관례.

## 5. 필터 기준 (기존 값 재사용)

이벤트가 스냅샷 대상이 되려면:
- 소속 마켓 2개 이상
- 모든 소속 마켓이 `active=True`, `accepting_orders=True`, `yes_price` 존재
- 소속 마켓 유동성 합계 ≥ `MIN_LIQUIDITY`(5000)
- 모든 소속 마켓 잔여기간 ≥ `MIN_DAYS_TO_RESOLUTION`(3일) — 마감 임박
  이벤트는 스프레드가 정보라기보다 유동성 고갈로 벌어지는 경우가 많아 제외

## 6. 에러 처리

- `get_markets()` API 호출 실패: 해당 사이클 스킵, 다음 폴링에서 재시도
  (`run_polymarket_arb_scan.py`의 기존 패턴 — 크래시 없이 계속 돔)
- 이벤트 내 마켓 하나라도 `yes_price` 없음/필터 불통과: 그 이벤트만 스킵,
  나머지 이벤트는 정상 처리

## 7. 실행 방식

`research/run_polymarket_event_divergence_scan.py`를 CLI로 직접 실행하는
독립 프로세스. 이번 스코프는 **데이터 수집까지만** — ICT 엔진처럼 tmux
상시구동으로 올리는 것도, 페이퍼 포지션을 자동으로 잡는 것도 범위 밖.
데이터가 쌓인 뒤 어떤 임계치가 실제로 유의미한 시그널인지는 사람이 보고
판단(추후 `run_polymarket_arb_validation.py` 같은 후처리 스크립트로 발전
가능, 이번 스펙에는 포함 안 함).

## 8. 테스트 계획

- `tests/test_polymarket_event_divergence_collector.py`:
  - `group_by_event`: 소속 마켓 1개인 이벤트 제외, 2개 이상인 이벤트만 그룹
    반환
  - `compute_divergence`: 정상 케이스 divergence 계산 정확성, 유동성 미달
    필터, `accepting_orders=False` 필터, 잔여기간 미달 필터, `yes_price`
    누락 마켓 포함 시 스킵
  - `run_once`: `get_markets` mock, top_n 정렬(|divergence| 내림차순) 확인
- 라이브 API 호출은 테스트에서 하지 않음(기존 컨벤션)

## 9. Out of scope

- 크로스*이벤트* 논리적 상관관계 분석 (2절 참조)
- WSS 실시간화 — 폴링만
- 페이퍼 포지션 자동 진입/저널링 — 스냅샷 수집까지만
- 판단/검증 로직(어느 divergence 크기가 실제 차익거래로 유효한지) — 후속
  작업
