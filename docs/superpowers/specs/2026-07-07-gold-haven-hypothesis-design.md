# 금(GC) 안전자산 가설 — Gold Haven 전략 설계

**날짜:** 2026-07-07
**분류:** v2 shadow 신규 가설 (미검증, CAPITAL=0, live 금지)

## 배경

기존 광역 탐색(autoresearch, TSMOM 32시장 등)과 별도로, 금 단일자산에 특화된 가설을
테스트한다. 계기: "금은 안전자산"이라는 통념을 명시적 신호로 옮겨서, 하우스 검증
게이트(random baseline p-value, walk-forward, cost-robust)를 통과하는지 확인.

TSMOM(`research/hypotheses/tsmom.py`, [[project_phase102_tsmom_edge]])은 이미 GC를
32시장 중 하나로 포함해 검증 통과했지만, 그 엣지는 "32개 비상관 슬리브 분산"에서
나온다. 금만 떼어 별도 로직으로 테스트하는 것은 그와 무관한 새 가설이다.

## 신호 로직

**레짐 게이트 (방향 결정, 롱/플랫만— 숏 없음):**
- 실질금리 proxy = `DGS10`(10년물 명목금리) − CPI YoY(`CPIAUCSL` trailing 12개월 변화율)
- 게이트: `real_rate(t) < real_rate(t - lookback)` (lookback=63거래일, 하락 추세) → BULLISH(롱)
- 그 외 → FLAT(무포지션)

**리스크오프 오버레이 (크기만 조절, 게이트 트리거 아님):**
- `VIXCLS` z-score(rolling 252일) 또는 `BAMLH0A0HYM2`(하이일드 스프레드) z-score가
  임계치(+1.5) 초과 → risk_off=True
- BULLISH 상태에서 risk_off=True면 가중치 부스트(배수 1.5, TSMOM과 동일한 `cap`으로 상한)
- risk_off 자체는 롱 진입 트리거 아님 — 게이트가 FLAT이면 risk_off든 아니든 무포지션

**주기:** 매일 체크(REBAL=1) — 리스크오프는 며칠 새 터지는 이벤트라 TSMOM의 21일
리밸런스로는 놓친다는 판단.

## 데이터

- GC 가격: 기존 `research/data/futures_loader.py` BASKET에 이미 포함 → `research/hypotheses/tsmom.py`의
  `build_panel("GC")` 그대로 재사용 (신규 수집 불필요)
- FRED: `DGS10`, `CPIAUCSL`, `VIXCLS`, `BAMLH0A0HYM2` — 전부 `fred/client.py`의
  `SERIES_CATALOG`에 이미 등록. CPI(월간)는 forward-fill로 일봉 정렬, 나머지는 일봉 그대로.

## 파일 구조

**신규: `research/hypotheses/gold_haven.py`**
- `build_macro_panel() -> dict` — FRED 4개 시리즈를 GC 가격 패널의 날짜축에 정렬(forward-fill 포함)
- `gold_haven_weights(panels, date, params, rng=None) -> dict` — 레짐 게이트 + 리스크오프
  오버레이 적용한 자산별 비중. `tsmom.py`의 `WeightFn` 시그니처와 동일하게 맞춰 `run_portfolio()`에
  바로 꽂는다.
- `buyhold_weights(panels, date, params, rng=None) -> dict` — 항상 롱(동일 vol 타겟), 타이밍
  가치 격리용 베이스라인. `tsmom.py`의 동명 함수와 같은 역할.
- `random_weights(panels, date, params, rng) -> dict` — 같은 빈도로 무작위 온(롱)/오프(플랫).
  숏은 애초에 없으므로 `tsmom.py`의 ±1 랜덤과 달리 0/1 랜덤.

**신규: `research/run_gold_haven.py`**
- `research/run_tsmom.py`와 동일 골격: `run_portfolio()`로 전략/buyhold/random(N=200) 실행,
  `empirical_p_value`로 Sharpe 분포 대비 percentile/p-value, walk-forward 반분(전반/후반
  Sharpe 둘 다 양수인지), cost 2bps(primary) / 20bps(stress) 병행.
- verdict 기준은 `run_tsmom.py`와 동일하게 고정: `sharpe>0 and random_percentile>=95 and
  p<0.05 and wf_first>0 and wf_second>0 and sharpe>buyhold_sharpe`.
- `log_experiment()`으로 `research/agents/experiment_registry.jsonl`에 기록.

## 파라미터 (고정, 튜닝 금지 — 최초 실행 전 동결)

```python
DEFAULTS = {
    "real_rate_lookback": 63,      # 거래일
    "risk_off_zscore_window": 252,
    "risk_off_zscore_threshold": 1.5,
    "risk_off_boost": 1.5,
    "target_vol": 0.15,            # TSMOM과 동일
    "cap": 3.0,                    # TSMOM과 동일
}
REBAL = 1        # 매일
COST_BASE_BPS = 2.0
COST_STRESS_BPS = 20.0
N_RUNS = 200
SEED = 42
```

## 한계 / 알려진 리스크

- **단일자산 → 표본 부족 위험.** TSMOM은 32시장 pooled라 통계적 힘이 있지만 이건 GC 하나뿐.
  `portfolio_metrics`가 내는 `underpowered` 플래그가 뜨면 그 자체가 결과(REJECT 근거는 아니고
  "판단 불가"로 처리, `run_tsmom.py`의 처리 방식 그대로 따름).
- **회전율 상승.** 매일 체크로 REBAL=1 선택 → TSMOM(21일)보다 리밸런스 빈도 높음. cost stress(20bps)
  검증이 이 부담을 걸러낼 것.
- **실질금리 proxy의 근사 오차.** TIPS 실질수익률(`DFII10`)을 직접 쓰지 않고 DGS10 − CPI YoY로
  근사 — 카탈로그에 이미 있는 시리즈만 쓰기 위한 선택. 필요시 후속 버전에서 `DFII10` 교체 검토.

## 스코프 밖 (이번 버전에서 하지 않음)

- DXY(`DTWEXBGS`) 역상관 시그널 — 별도 후보, 이번 검증 결과 보고 판단
- 이벤트 트리거형(위기 때만 진입, 트렌드 무관) — 발생 빈도 낮아 표본 문제 커서 보류
- 기존 매크로 레짐 스코어(0~100, Phase 147)와의 통합 — 재사용성은 높지만 이번엔 신호를
  최대한 단순하게 격리해서 해석 명확하게 유지

## 검증 → 다음 단계

1. `research/run_gold_haven.py` 실행, verdict 확인
2. EDGE 후보면 v2 shadow 상태로 관찰(라이브 없음, 최소 3~6개월 forward 관찰 — TSMOM과 동일 원칙,
   [[feedback_tsmom_paper_discipline]])
3. REJECT면 스코프 밖 후보(DXY/이벤트트리거/레짐스코어 통합) 중 하나로 재시도 여부 판단
