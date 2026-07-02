# Research — Strategy Validation Terminal

목적: **엣지 검증.** "좋아 보이는 백테스트"가 아니라 "비용·랜덤·워크포워드 후에도 살아남는 엣지인지" 판정.
포지셔닝: ❌ AI 트레이딩 봇 → ⭕ **전략을 냉정하게 죽이는 검증 터미널.**

원칙: **구조는 알파가 아니다.** 하네스가 먼저, 데이터 그 다음, 전략은 마지막. 못 이기면 폐기.

> **현황(2026-07-02): 10개 가설 검증 → 검증된 엣지 0개.** 결과: [`reports/VALIDATION_SUMMARY.md`](reports/VALIDATION_SUMMARY.md).
> 알파 사냥 중단. Lv3 자율루프 보류. 실투자는 패시브/저빈도. 고급 알파원은 학습·제품기능 한정.

## 구조

```
research/
  data/
    intraday_store.py   인트라데이 봉 저장소 (data/intraday/{SYM}_{tf}.parquet, 재개가능)
    ib_downloader.py    IB reqHistoricalData 청크·페이싱·백워드 수집
    pull_intraday.py    수집 CLI (TWS 필요)
  validation/
    cost_model.py       effective_cost_bps = cost + slippage + spread/2
    engine.py           인덱스 기반 롱숏/고정보유 체결 시뮬
    metrics.py          거래기반 expectancy·PF·Sharpe·MDD + underpowered 가드(<30)
    baselines.py        random_same_frequency(N=500 분포) · naive · empirical_p_value
    walk_forward.py     순수 롤링 윈도우 러너 + consistency
  reports/
    alpha_report.py     md + json 리포트 ("HARNESS VALIDATION, NOT ALPHA" 배너)
    alpha/              생성된 리포트
  run_validation.py     드라이런: 일봉 ema_cross 기니피그로 전 파이프 실행
```

## 순서 (합의된 로드맵)

1. **B — 검증 하네스** ✅ (Phase 94). 데이터 무관, 재사용 가능.
2. **A — IB 15m 데이터저장소** ✅ 코드 (수집은 TWS 필요).
3. **ORB+RVOL+VWAP 단일 가설** ⏳ — 다음.

## 실행

### 하네스 드라이런 (데이터 불필요, 일봉)
```bash
PYTHONPATH=. python3 research/run_validation.py
```
→ `research/reports/alpha/*.md|json`. **이건 하네스 sanity지 알파 아님.**

### 인트라데이 수집 (TWS/Gateway 필요, 127.0.0.1:${IB_PORT:-7497})
```bash
# 스모크 (AAPL 5일)
PYTHONPATH=. python3 research/data/pull_intraday.py --test
# 기본 유니버스 15m 2년 (느림, 재개가능 — 중단 후 재실행하면 이어받음)
PYTHONPATH=. python3 research/data/pull_intraday.py --tf 15m --years 2
```
⚠️ IB 페이싱 ~6 req/min → 요청당 ~11s 대기. 20+종목 2년이면 수십 분~시간. useRTH=True(정규장만).

### 테스트
```bash
python3 -m pytest tests/test_validation_harness.py tests/test_intraday_store.py tests/test_labeling.py -q
```

## ORB 붙이는 법 (다음 단계)

`run_validation.py`의 `signal_fn`만 ORB 로직으로 교체 → 나머지(cost/random/walk-forward/report) 그대로.
random 베이스라인은 **ORB 셋업 가능했던 인덱스만** `eligible_indices`로 넘겨 공정 비교.

판정 질문 하나: **비용 후 random same-frequency 분포의 95퍼센타일을 넘는가?** 못 넘으면 폐기 — ablation/레짐/LLM 필터 논할 것도 없음.

## 하지 말 것
LLM risk_score(0~100) 만들기 / 6레짐 분해·풀 ablation을 엣지 확인 전에 / 백테스트 수익률만 보고 실거래.
