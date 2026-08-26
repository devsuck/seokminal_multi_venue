# Microstructure Hypothesis Engine — Design

**Status:** approved by user (2026-08-26), paper-only (no live capital in scope).

## Background

`research/autoresearch/engine.py::collect_candidates()`는 현재 소스 2개, 둘 다 KR 전용:
- `_event_family_candidates()` — DART 공시 11종 (`research/scanner/families.py`)
- `engines_factor.factor_candidates()` — KR 횡단면 팩터 8종

이미 가동 중인 tmux 수집기 3개(`hl-orderflow-tick`, `cross-venue-skew-tick`,
`convergence-legs`, `api_server/lab_api.py::COLLECTOR_SESSIONS`) 중 앞 2개는
비-KR raw tick 데이터를 매일 계속 쌓고 있으나 어떤 가설 엔진에도 연결돼 있지 않음.
`convergence_legs`는 이름과 달리 `dart_corp_action` source — KR이라 확장 대상 아님.

수집된 데이터 실측(2026-08-26 확인):
- `research/data/hl_orderflow_tick/`: Hyperliquid 틱(`{symbol, ts, price, size, side}`),
  BTC/ETH 2026-07-10~, PAXG 2026-07-17~, 매일 gz 로테이션, 삭제 없음. 약 40일치.
- `research/data/cross_venue_skew/`: 오더북 스냅샷(`{symbol, ts, bids, asks}`),
  binance/hl/okx × BTC/ETH, 2026-07-12~, 약 40일치.

목표: 이 두 소스를 새 가설 엔진으로 묶어 `collect_candidates()`의 3번째 소스로 배선.
기존 엔진과 동일한 정직성 기준(사전등록 thesis, BH-FDR 배치 보정, 레드팀 통제)을 따름 —
데이터 마이닝으로 "잘 되는 시그널"을 사후 선택하지 않는다.

## Non-Goals

- Live capital 연결 없음. 결과는 paper-tracking 후보로만 배치에 편입.
- `convergence_legs` 미포함(KR이라 범위 밖).
- 신규 데이터 수집기 추가 없음 — 이미 도는 tmux 세션 데이터만 사용.
- KR 팩터/이벤트 엔진(`engines_factor.py`, `families.py`) 수정 없음.

## Architecture

`research/autoresearch/engines_microstructure.py` 신설. `engines_factor.py`와 동일한
패턴(사전등록 config 딕셔너리 + `_candidates()` 함수 하나)을 따름.

```
collect_candidates()
  ├─ _event_family_candidates(series)        # 기존, 불변
  ├─ engines_factor.factor_candidates(...)     # 기존, 불변
  └─ engines_microstructure.microstructure_candidates()   # 신규
```

### 사전등록 후보 (경제논리당 방향 1개 — 반대방향 이중등록 금지)

**1. HL OFI momentum** (신규 category: `"microstructure"`)
- 시그널: 일별 order flow imbalance = `Σ(buy size) - Σ(sell size)` (그날 틱 전체)
- 근거: informed order flow persistence (Kyle 1985 계열 — 정보 우위 거래자의 flow는
  단기 방향성을 예측)
- 방향: signal 상위 → 다음날 롱, signal 하위 → 다음날 숏(즉 momentum, reversal 아님)
- 심볼: BTC, ETH, PAXG (HL 데이터 존재하는 3개 전부 — 개별 candidate)

**2. Cross-venue basis reversion**
- 시그널: 일별 대표가(중간값 or VWAP) 거래소간 차이 = `price_A - price_B`
- 근거: cash-and-carry 재정거래 — 가격괴리는 차익거래로 수렴
- 방향: basis 극단 → 수렴 방향 베팅(reversion)
- 심볼×거래소쌍: BTC/ETH × (binance vs okx), (binance vs hl), (okx vs hl) — 조합 수는
  구현 시 실제 겹치는 날짜 수 보고 정함(과도한 조합은 BH-FDR에 불리하므로 최대 4개로 제한)

두 thesis 모두 **방향 1개만** 등록 — momentum 반대(reversal)나 reversion 반대(momentum)를
같이 등록하지 않는다(사후에 잘 맞는 쪽 고르는 건 p-hacking).

### 데이터 흐름

```
raw tick(jsonl / jsonl.gz)
  → 일별 리샘플
      OFI: 그날 파일 전체 순회, side별 size 합산 → 1개 스칼라/일
      skew: 그날 스냅샷들의 mid price 평균 → 거래소쌍 basis 1개 스칼라/일
  → (신호[t], 다음날 수익률[t+1]) 페어 시계열 구성
  → 상위/하위 분위(예: median split, 표본 작아 quintile 불가) 별 평균 수익률 차 = strategy_stat
  → research.validation.baselines.random_same_frequency + empirical_p_value 재사용
    (같은 거래횟수·비용의 랜덤 진입 500회 분포 대비 percentile/p)
  → evidence dict {p, net, percentile, n, ...} → 기존 배치(BH-FDR+레드팀) 편입
```

기존 `event_study.py`(KR PIT 전용)는 재사용하지 않고, `research.validation.baselines`의
범용 함수(`random_same_frequency`, `empirical_p_value`)만 재사용 — 이미 심볼/자산 중립적
인터페이스라 크립토 데이터에도 그대로 적용 가능.

### 비용 모델

KR 80bps/월 관행 그대로 못 씀(빈도·구조 다름). HL taker fee(약 3.5bps) + 예상 슬리피지로
왕복 10bps 가정, 스트레스 20bps — `engines_factor.py`의 `COST_M`/`STRESS_M` 패턴과 동일하게
모듈 상수로 고정, 사전등록에 포함.

### 표본 크기와 정직성

일별 버킷 → n≈35~40(심볼별 실제 겹치는 날짜 수에 따라 다름). 기존 최소 기준(event_family는
n<30 시 `underpowered: True`로 배치엔 넣되 run은 None 반환)과 동일 원칙 적용 — 여기서도
`_MIN_DAYS = 30` 미만이면 정직하게 underpowered 표기, 억지로 유의성 만들지 않음.

## 통합 지점

`research/autoresearch/engine.py::collect_candidates()`:
```python
def collect_candidates() -> tuple[list[Candidate], dict]:
    series = load_series()
    cands = _event_family_candidates(series)
    from research.autoresearch.engines_factor import factor_candidates, load_fundamentals
    fund = load_fundamentals(list(series.keys()))
    cands += factor_candidates(series, fund=fund)
    from research.autoresearch.engines_microstructure import microstructure_candidates
    cands += microstructure_candidates()          # 신규 — series/fund 불필요(자체 데이터 로드)
    return cands, series
```

`microstructure_candidates()`는 `series`/`fund` 인자 불필요 — 자체적으로
`research/data/hl_orderflow_tick/`, `research/data/cross_venue_skew/`를 읽음.

## Testing

- 단위: OFI 일별 집계 함수, basis 계산 함수 각각에 대해 알려진 입력→출력 assert.
- `microstructure_candidates()` 통합 테스트: mock 파일 몇 개로 candidate 리스트 형태
  검증(cid/category/thesis/direction/run 필드 존재, run() 호출 시 dict or None).
- 실데이터로 1회 수동 실행(`PYTHONPATH=. python3 -c "..."`) → evidence 값 로그 확인,
  `underpowered` 케이스 있으면 그대로 보고(억지 통과 금지).
- 기존 `tests/ -q` 회귀 없음 확인(신규 파일만 추가, 기존 파일 미수정).

## 운영 원칙(사전등록 — 결과 보고 튜닝 금지)

- OFI 부호/방향, basis 거래소쌍, 비용 가정, 리밸런스 주기(일별) — 등록 후 변경 금지.
- 이 스펙 통과 후보만 배치 편입 → BH-FDR/레드팀 통과분만 `paper_candidate`로.
  KR 팩터 3개와 동일하게, live 전환은 여기서 다루지 않음(3~6개월 관찰 후 별도 결정).
