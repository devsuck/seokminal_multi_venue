# KR Factor Forward-Test Report — fac_kr_turnover_neglect_v1 (kr_turnover_neglect)

> **paper_candidate_forward_test_required** · as of 2026-09 · ⚠️ PAPER ONLY, NO LIVE CAPITAL.
> config 동결(튜닝 금지): signal=turnover long_low=True cost 80.0/160.0bps

## Backtest Envelope (forward 비교 기준)
- 월평균 0.010207 std 0.076581 · P10 -0.090062 / P90 0.094079 (n=84)

## 비용 스트레스
- base 월평균 0.010207 / stress(160bps) 월평균 0.002207

## Baseline (auto-research 검증 시점, frozen_at=2026-08-25)
- {'n': 82, 'net': 0.012017, 'percentile': 100.0, 'p': 0.0033, 'wf_first': 0.007855, 'wf_second': 0.016178}

## Forward Months (envelope 이탈)
- 2026-09: -0.0659 → in_envelope

## 운영 원칙
- live capital 금지. 신호/quintile/리밸런스/비용 변경 금지. 결과 후 튜닝 금지.
