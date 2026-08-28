# KR Factor Forward-Test Report — fac_kr_size_smb_v1 (kr_size_smb)

> **paper_candidate_forward_test_required** · as of 2026-08 · ⚠️ PAPER ONLY, NO LIVE CAPITAL.
> config 동결(튜닝 금지): signal=marcap long_low=True cost 80.0/160.0bps

## Backtest Envelope (forward 비교 기준)
- 월평균 0.044065 std 0.089618 · P10 -0.045714 / P90 0.137592 (n=83)

## 비용 스트레스
- base 월평균 0.044065 / stress(160bps) 월평균 0.036065

## Baseline (auto-research 검증 시점, frozen_at=2026-08-25)
- {'n': 82, 'net': 0.042305, 'percentile': 100.0, 'p': 0.0033, 'wf_first': 0.043223, 'wf_second': 0.041387}

## Forward Months (envelope 이탈)
- (아직 forward 월 없음 — 월마다 최신 데이터 pull 후 재실행)

## 운영 원칙
- live capital 금지. 신호/quintile/리밸런스/비용 변경 금지. 결과 후 튜닝 금지.
