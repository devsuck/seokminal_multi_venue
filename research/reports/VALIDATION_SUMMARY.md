# Strategy Validation — Results Summary

> **검증된 엣지: 0개.** 이 시스템은 "돈 버는 봇"이 아니라 **전략을 냉정하게 죽이는 검증 터미널**이다.
> 방법: 비용 반영 + random same-frequency 분포 + walk-forward + BH-FDR + underpowered guard + gross/net 분해.

- 테스트한 가설: **11**
- REJECT: **10**  |  BLOCKED(데이터): 1  |  후보: 0
- **Lv3 자율 리서치 에이전트: 진입 보류**(탐색할 검증 엣지 0개)

## 판정 테이블
| 가설 | 상태 | net | 실패 기전 |
|---|---|---|---|
| orb_rvol_vwap | rejected | -5401.780621 | signal_dead (gross도 음수) |
| vwap_mean_reversion | rejected | -50316.06586 | cost_killed (gross+, 거래당 엣지<비용) |
| orb_failed_reversal | rejected | -47360.06905 | cost_killed (gross+, 거래당 엣지<비용) |
| gap_continuation | rejected | -7646.884451 | cost_killed (gross+, 거래당 엣지<비용) |
| atr_compression | rejected | -1641.726528 | signal_dead (gross도 음수) |
| sector_relative_momentum | rejected | -19314.615378 | cost_killed (gross+, 거래당 엣지<비용) |
| delta_neutral_carry_hl | blocked_by_data |  | blocked_by_data (메이저 spot 부재) |
| funding_extreme_reversal | rejected | 1044.6041 | indistinguishable_from_random (net+ but <80pct) |
| cross_sectional_funding | rejected | -42804.2301 | cost_killed (일 리밸런스 과잉거래) |
| cross_sectional_funding_weekly | rejected | 13621.733 | indistinguishable_from_random (net+ but 82.6pct, WF 불안정) |
| futures_tsmom | rejected |  | decayed/marginal (Sharpe 0.44 최고근접·buyhold초과·91.5pct지만 <95·WF후반 붕괴=감쇠) |

## 실패 기전 분류
- **signal_dead**: gross(비용 0)도 음수 → 신호 자체 없음. (ORB, ATR압축)
- **cost_killed**: gross 양수지만 거래당 엣지가 비용보다 작음(과잉거래). (VWAP-MR, 실패돌파, 갭, 섹터, cross-sectional daily)
- **indistinguishable_from_random**: net 양수지만 random 분포 95pct 미달 = 운/변동성. (funding reversal, weekly funding)
- **blocked_by_data**: 데이터 게이트 실패. (delta-neutral carry — 메이저 spot 부재)

## 핵심 교훈
1. 교과서 알파(주식 인트라데이 + 크립토 funding)는 리테일 규모·현실 비용에서 척박.
2. gross 양수 ≠ 엣지. 거래당 엣지가 비용을 넘고 random 분포를 이겨야 함.
3. weekly funding이 net+13.6k 냈지만 random 82.6pct = 엣지 아니라 변동성.
4. 값진 자산 = 알파가 아니라 **알파 없음을 싸게 증명하는 검증 프레임워크**.

## 포지셔닝
- ❌ AI Trading Bot  →  ⭕ **Strategy Validation Terminal**
- 실투자: 패시브/저빈도. 고급 알파원(이벤트/온체인/옵션)은 학습·제품기능 한정.
