# Polymarket Sharp-Wallet Convergence — Confidence Score 확장 Design Spec

**작성:** 2026-07-21. 브레인스토밍 중 확정, 사용자 승인 완료.

## 1. 배경

`docs/superpowers/specs/2026-07-20-polymarket-sharp-wallet-design.md`(이하
"원 스펙")에서 구현한 컨버전스 감지는 `convergence_count`(윈도우 내 distinct
sharp wallet 수) → `convergence_bucket`(1/2/3 캡) 하나의 축만 쓴다. 지갑
숫자만 세고 "얼마나 좋은 지갑들이, 얼마나 큰 돈으로, 얼마나 유동적인 마켓에서"
움직였는지는 반영하지 않는다.

SNS 마케팅 영상(하이프 계정, 수치는 연출 — 참고용) 파이프라인 중 "Score & rank
edges" 단계에서 아이디어만 추출: 컨버전스 이벤트를 이산 버킷이 아니라 연속
confidence score로 매겨서, 원 스펙의 버킷 검증과 나란히 forward-return 예측력을
비교한다.

## 2. 목적 및 범위

**연구/검증 파이프라인 전용.** 라이브 시그널 노출·알림(텔레그램 등)·실집행은
전부 이번 스펙 범위 밖 — 아직 버킷 방식조차 BH-FDR 통과 전이라, 검증 안 된
스코어를 라이브에 노출하면 오해를 부른다(§7 Out of scope 참고).

기존 `convergence_bucket` 로직은 건드리지 않는다. `score` 컬럼을 anchor에
**추가**하고, score 기반 3분위(tercile) 검증을 원 스펙의 버킷 검증과 나란히
돌려 어느 쪽이 forward return을 더 잘 설명하는지 비교한다.

## 3. 스코어 공식

4개 raw 컴포넌트 — 전부 기존에 수집된 데이터로만 계산, **신규 수집 없음**:

1. **`wallet_count`** — 원 스펙의 `convergence_count` 그대로 재사용(윈도우 내
   distinct sharp wallet 수, 자기 자신 포함).
2. **`pnl_sum`** — 그 컨버전스 윈도우 안에서 감지된 distinct sharp wallet들의
   `wallet_pnl`(리더보드 PnL, 이미 anchor 행마다 저장돼있음) 합.
3. **`notional`** — anchor 체결 자체의 `notional_usd`.
4. **`liquidity`** — anchor 시각부터 `MAX_HORIZON_S`(300초) 안에 같은
   `condition_id`에서 쌓인 context 체결(지갑 무관) `notional_usd` 합. 수집기
   구조상 anchor 이전 구간의 체결은 저장돼 있지 않으므로(원 스펙 §6) forward
   window만 가능 — forward-return 라벨링과 동일한 시간축이라 방법론
   일관성 있음.

**정규화: 데이터셋 내 percentile 랭크.** 그 검증 run에 모인 전체 anchor
집합 안에서 각 raw 컴포넌트를 percentile(0~100)로 변환한다(`pandas
.rank(pct=True) * 100`). 고정 reference cap을 쓰지 않는 이유: 표본이 아직
작고(§ 원 스펙 기준 sharp wallet 4개, 마켓 38개) 실측 분포 없이 cap을 찍으면
근거가 약함 — percentile은 매직넘버 없이 런 내부에서만 상대비교하므로 표본이
작을 때 더 견고하다. **트레이드오프:** 점수는 런 간 절대비교 불가(오늘 80점과
다음달 80점은 다른 기준) — 이번 스펙은 런 내부 검증용이라 문제 아님.

**최종 score = 4개 percentile의 동일가중 평균.** 가중치 차등을 줄 근거(실측
예측력 비교)가 없는 상태라 동일가중이 기본값 — 이후 이터레이션에서 개별
컴포넌트 예측력이 갈리면 재검토.

## 4. 아키텍처 (원 스펙 확장, 신규 파일 없음)

기존 2개 파일만 수정:

```
research/hypotheses/polymarket_sharp_wallet.py      ← build_convergence_score() 추가
research/run_polymarket_sharp_wallet_validate.py     ← score tercile 검증 추가
```

### 4.1 `research/hypotheses/polymarket_sharp_wallet.py`

신규 함수 `build_convergence_score(trades, anchors) -> pd.DataFrame`:

- 입력: `load_sharp_wallet_trades()`가 반환한 전체 체결(`trades`)과
  `build_convergence_count()`가 반환한 anchor 테이블(`anchors`, `convergence_count`
  포함).
- 각 anchor 행마다:
  - `wallet_count` = 해당 행의 `convergence_count`(이미 있음, 재계산 안 함).
  - `pnl_sum` 계산을 위해 컨버전스 윈도우 내 distinct wallet 집합이 필요 —
    `build_convergence_count`가 현재 카운트만 반환하고 지갑 목록은 버리므로,
    이 함수 내부에서 동일 윈도우 로직(`t-CONVERGENCE_WINDOW_S ~ t`, anchor만
    대상)을 다시 돌며 distinct wallet들의 `wallet_pnl` 합을 구한다. (윈도우
    스캔 로직이 `build_convergence_count`와 중복되지만, 두 함수의 반환 계약을
    분리 유지하는 쪽이 각 함수를 독립적으로 이해·테스트하기 쉬움 — anchor
    개수가 하루 수백 건 수준이라 O(n²) 재스캔 성능은 문제 안 됨.)
  - `notional` = 해당 anchor 행의 `notional_usd`.
  - `liquidity` = `trades`에서 `condition_id`가 같고 `ts`가
    `[anchor.ts, anchor.ts + MAX_HORIZON_S]` 구간인 모든 행(anchor+context
    구분 없이)의 `notional_usd` 합.
  - 4개 raw 값을 anchor 테이블 전체 기준으로 `pandas .rank(pct=True) * 100`
    percentile 변환 → 4개 평균 → `score` 컬럼.
- 반환: 입력 `anchors`에 `pnl_sum_raw`, `notional_raw`, `liquidity_raw`,
  `score` 4개 컬럼을 추가한 DataFrame(기존 컬럼 전부 유지 — `convergence_bucket`
  포함, 하위호환).
- anchor가 0~1건이면 percentile 랭크가 정의상 무의미(분모 1) — 그 경우 해당
  run은 `score` 전부 `NaN`으로 두고 호출자(검증 러너)가 표본부족으로 스킵.

`build_labels_multi_horizon`은 이미 `anchors` 행 전체를 순회하며 필요한
컬럼(`convergence_bucket`)만 골라 쓰는 구조 — `score`도 같은 방식으로
pass-through하도록 결과 딕셔너리에 `"score": row["score"]` 한 줄만 추가.

### 4.2 `research/run_polymarket_sharp_wallet_validate.py`

- `build_convergence_score()` 호출 추가(anchor 계산 직후, 라벨링 이전).
- 신규 함수 `run_score_tercile(tercile: str, labels: pd.DataFrame) -> dict`:
  `run_bucket()`과 동일 구조(방향 셔플 랜덤베이스라인, `empirical_p_value`,
  `MIN_EVENTS=10` 게이트) — 그룹 키만 `convergence_bucket` 대신 `score_tercile`
  ("low"/"mid"/"high").
- `score_tercile` 계산: `labels["score"]`를 `pd.qcut(..., 3, labels=["low",
  "mid", "high"])`으로 3등분(데이터 적응형 — 원 스펙 §7의 percentile 스코어
  자체가 이미 런 내부 상대값이므로, 버킷 경계도 같은 방식으로 그 run 안에서
  정함).
- 그룹 단위: `score_tercile`(3) × `horizon`(3) = 최대 9개 p-value. 기존
  `convergence_bucket×horizon` 9개와 **완전히 분리된 신규 BH-FDR 풀**로
  correction(원 스펙 §8과 동일 규율 — 프로젝트 전역 컨벤션, 다른 가설/축과
  안 섞음). `alpha=0.1`.
- 출력: 기존 버킷 리포트 아래에 `=== score tercile ===` 섹션 추가해 나란히
  출력. 두 방식 중 어느 쪽 p-value가 더 잘 살아남는지(BH-FDR survivors)로
  다음 이터레이션에 스코어 방식으로 전환할지 판단.

## 5. 테스트 계획

- `tests/test_polymarket_sharp_wallet.py`(기존 파일에 추가):
  - `build_convergence_score`: 4개 raw 값 계산 정확성(고정 fixture로 손계산
    가능한 소규모 케이스), percentile 정규화(예: 3개 anchor면 각각
    0/50/100 percentile이 되는지), anchor 1건일 때 `score`가 `NaN`인지.
  - `liquidity` 컴포넌트: context 체결이 윈도우 밖(anchor.ts + 300s 초과)이면
    합산에서 제외되는지 경계 테스트.
- `tests/test_run_polymarket_sharp_wallet_validate.py`(기존 파일에 추가):
  - `run_score_tercile`: `MIN_EVENTS` 미달 시 BLOCKED, tercile 3그룹 정상
    분리, 기존 버킷 BH-FDR 풀과 score tercile BH-FDR 풀이 서로 섞이지 않는지
    (survivors 리스트가 각자 자기 풀의 키만 포함하는지).

## 6. Out of scope

- 라이브 시그널 노출/알림(텔레그램 등) — score 자체가 아직 통계 검증 전이라
  실집행 근거로 못 씀. BH-FDR 통과 시 별도 스펙에서 재검토.
- 실제 orderbook depth 수집(Polymarket CLOB API 신규 연동) — `liquidity`는
  기존 체결 데이터 기반 프록시로 근사. 표본 늘어나서 프록시 정확도가 병목이라
  판단되면 다음 이터레이션에서 재검토.
- 지갑 클러스터링(동일 운영자가 여러 지갑 쓰는지 탐지) — 원 스펙 §11에서
  이미 out of scope 처리(검증 불가능한 추정). 이번 스펙도 동일 — `wallet_count`
  컴포넌트는 여전히 distinct proxyWallet 카운트로 근사.
- 컴포넌트 가중치 튜닝/ML 기반 스코어링 — 동일가중 평균이 기본값, 실측
  예측력 비교 없이 조기 최적화 안 함(YAGNI).
