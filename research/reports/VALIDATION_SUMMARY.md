# Strategy Validation — Results Summary

> **검증된 엣지: 0개.** 이 시스템은 "돈 버는 봇"이 아니라 **전략을 냉정하게 죽이는 검증 터미널**이다.
> 방법: 비용 반영 + random same-frequency 분포 + walk-forward + BH-FDR + underpowered guard + gross/net 분해.

- 테스트한 가설: **16**
- REJECT: **11**  |  BLOCKED(데이터): 1  |  후보: 4
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
| futures_tsmom | candidate |  | decayed/marginal (Sharpe 0.44 최고근접·buyhold초과·91.5pct지만 <95·WF후반 붕괴=감쇠) |
| futures_tsmom_32mkt | paper_candidate_forward_test_required |  | PAPER_CANDIDATE (Sharpe 0.56·random95.5pct·WF안정·비용robust, 32시장 확장) |
| kr_liquidity_wave_pullback_v1 | rejected |  | REJECT (survivorship 통제 후 유의성 소멸: p=0.136·86.6pct·severe비용 음수·delisted −3%가 상방편향 확증) |
| kr_liquidity_wave_pullback_v1_survctrl | underpowered |  | superseded (게이트 결함, delisted 1개만 포함) |
| kr_liquidity_wave_pullback_v1_eventwin | underpowered |  | REJECT (이벤트윈도우 게이트=제대로된 survivorship 통제판, delisted 39개) |
| kr_dart_buyback_drift_v1 | watchlist |  | superseded by _PIT (FDR 생존편향, p=0.002 부풀려짐) |
| kr_liquidity_wave_pullback_v1_PIT | rejected |  | REJECT 확정 (KRX 공식 PIT/survivorship-free 1923종목: gross −1.26% 음수, net −1.66% random 0.2pct = 랜덤보다 나쁨. survivor-only +2.28%는 100% 편향) |
| kr_dart_buyback_drift_v1_PIT | watchlist |  | WATCHLIST→PAPER 후보 (전체 PIT/survivorship-free 2906종목: buyback net +1.73% random 97pct p=0.032, WF 양쪽 양수, 비용스트레스 통과, 유상증자 대조 낮음. 급등주 죽인 테스트 생존=진짜 엣지, TSMOM 다음 2번째) |

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
