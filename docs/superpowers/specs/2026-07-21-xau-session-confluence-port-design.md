# XAU Session Confluence 전략 — Pine→Python 포팅 Design Spec

**작성:** 2026-07-21. 브레인스토밍 확정, 사용자 승인 대기.

## 1. 배경

TradingView에서 백테스트/튜닝한 "XAU Session Confluence Strategy"(Pine v6)를 플랫폼에
심으려 했으나, Lv1 에이전트의 `condition` rule은 condition_engine 지표(rsi/ma/bb/macd/
cci/obv)만 표현 가능 — **세션/아시안레인지/돌파/HTF-바이어스 프리미티브가 없어 이 전략을
구조적으로 담을 수 없다.** 따라서 조건 rule로 우겨넣는 대신 **파이썬으로 충실히 포팅**해
BTC ICT 엔진(`run_ict_paper_engine.py`)처럼 별도 XAU 엔진으로 돌린다.

## 2. 목적 및 범위

**충실한 포팅 + 백테스트 재현(검증) 전용.** house 규율대로 페이퍼/검증 먼저, 라이브 실집행
없음. XAU 단일.

핵심 성공기준: **파이썬 백테스트가 TradingView 백테스트와 근사 일치**(트레이드 수/승률/
Profit Factor). 일치해야 "제대로 옮겼다"가 증명되고, 그 뒤 라이브 페이퍼로 승격.

**포함:** 순수 전략 로직 포팅 + 파이썬 백테스트 러너(TV 대조) + 유닛테스트.
**제외:** 라이브 실집행, 비-XAU, Lv1 에이전트 통합(이 엔진이 대체), 라이브 페이퍼 엔진은
후속 페이즈(백테스트 충실도 검증 후).

## 3. 전략 사양 (Pine에서 정밀 이식 — 결과 보고 안 바꿈)

**세션 (NY 타임, America/New_York, DST 반영):**
- Asian 19:00–03:00, London 02:00–11:30, NY 08:00–16:00.

**아시안 레인지:** Asian 세션 중 high/low 추적, **세션 종료(03:00) 시점에 고정**(`fixed_asian_hi/lo`).
Pine은 60분 HTF security로 계산 — 포팅도 60m 리샘플 기준.

**런던 돌파 (사이클당 1회):** London 세션 중 `close > fixed_asian_hi` → 롱 돌파,
`close < fixed_asian_lo` → 숏. 사이클당 1회(dedup). 같은 바에 양방향이면 **롱 우선**.
가드: 아시안 종료 후에만 유효(`cycle_range_ready` — 세션 오버랩 02:00–03:00에서 이전
사이클 stale 레인지로 오탐 방지).

**NY 연속:** NY 세션 중 같은 방향 돌파가 `breakout_level` 재돌파(롱이면 `close > level`).
사이클당 1회.

**엔트리:** `(런던돌파) OR (NY연속)`, 각각 토글(`use_london_breakout`/`use_ny_continuation`).

**리스크 (Task 5):**
- SL: 롱=`fixed_asian_lo`, 숏=`fixed_asian_hi`.
- TP: `entry ± riskReward * risk`(risk=|entry−SL|). **기본 riskReward=0.5**.
- 사이징: `qty = equity * riskPercent/100 / (risk * point_value)`. **기본 riskPercent=3**.

**필터 (전부 토글):**
- 아시안레인지폭(Task 6, **기본 ON**): `(hi−lo)/lo*100 ∈ [1.2, 100]`.
- HTF 바이어스(Task 7, 기본 OFF): 240m close vs EMA(50), 롱=bullish/숏=bearish.
- 스탑거리밴드(Task 9, 기본 OFF): SL 거리% ∈ [min,max].
- 엔트리캔들강도(Task 10, 기본 OFF): 종가의 바내 위치 ≥ 0.6.

**엑싯 (Task 8):**
- 기본: SL + TP(limit).
- 브레이크이븐(OFF): `entry + beTriggerR*origRisk` 도달 시 SL→entry.
- 시간청산(OFF): `maxBarsInTrade`(기본 60) 경과 시 청산.
- 트레일/부분(OFF): TP에서 부분청산(partialExitPct=50) + 러너 ATR 트레일(mult 2, len 14).

**체결 가정:** `process_orders_on_close=true`(바 종가 평가), `calc_on_every_tick=false`,
commission 2.5/계약, slippage 2, pyramiding 0(동시 1포지션).

⚠️ **유저 확인 필요:** 위는 Pine 기본값. 님의 *실제 승리 백테스트* 설정(필터 토글/파라미터,
차트 타임프레임, 심볼)이 이거랑 같은지 확인 — 포팅은 그 설정을 재현해야 함.

## 4. 포팅 충실도 (fidelity) — 여기서 틀리면 백테스트 안 맞음

- **바 종가 평가**: 모든 신호/진입/청산은 확정된 바 close에서(process_orders_on_close). 인트라바 없음.
- **no-lookahead**: 60m 아시안레인지·240m HTF는 `lookahead_off` = 확정된 상위봉만 참조. 미래 누출 금지.
- **타임존/DST**: `zoneinfo("America/New_York")`로 세션 판정(UTC 저장 데이터 → NY 로컬 변환). DST 경계 정확히.
- **사이클 상태머신**: 아시안시작(19:00) 리셋 → 아시안종료(03:00) 레인지 고정 → 런던 돌파 1회 →
  NY 연속 1회. dedup/타이브레이크/오버랩가드 Pine 그대로.

## 5. 아키텍처 (신규)

```
research/xau_session/strategy.py    ← 순수 신호+리스크 로직(바 시퀀스 → 트레이드). 상태머신.
research/xau_session/sessions.py    ← NY 세션/아시안레인지 판정(tz-aware). 순수.
research/run_xau_session_backtest.py ← 저장된 XAU 인트라데이로 백테스트 → 트레이드/통계(TV 대조용)
tests/test_xau_session_*.py
```
재사용: `research/data/intraday_store`(XAU 인트라데이), 리샘플(15m→60m/240m, 기존 `_resample_*`
패턴), cost model. 데이터 심볼: `xyz:GOLD`/`PAXG`(HL) 또는 `GC`(IB) — 보유분 중 선택.
라이브 페이퍼 엔진(후속)은 ICT 엔진 패턴 재사용.

## 6. 검증

- **TV 대조(핵심)**: 파이썬 백테스트 트레이드 수/승률/PF/총손익을 님 TradingView 결과와 대조.
  근사 일치(소수 트레이드 차이는 데이터소스/체결가정 차이 허용) = 충실도 OK.
- **유닛테스트**: 세션/아시안레인지 고정, 런던돌파 dedup·타이브레이크, NY연속 의존성,
  R:R 청산, 각 필터 게이트, 사이클 리셋 — 합성 바로 수학 검증.
- ⚠️ 라이브 데이터 검증은 맥(원격은 Polymarket만 막힘 — XAU 인트라데이는 로컬 store라
  이 컨테이너에 데이터 있으면 여기서도 백테스트 가능, 없으면 맥).

## 7. Out of scope
라이브 실집행, 비-XAU, Lv1 에이전트/condition_engine 통합, 실자본. 라이브 페이퍼 엔진은 후속.

## 8. 정직한 함정
- **R:R=0.5**(타깃이 리스크의 절반) = 소익다승 구조, 높은 승률 전제 — 님 튜닝값이니 그대로 포팅하되 비용후 민감.
- Pine `security()`↔파이썬 리샘플의 봉경계·확정시점 차이가 트레이드 미세차이 유발 가능(§4로 최소화).
- 사이징이 `strategy.equity`(복리) — 포팅 시 고정자본 vs 복리 결정(백테스트 재현엔 복리로 맞춤).
- 데이터 소스 차이(TV 스팟 XAU ↔ HL xyz:GOLD/IB GC): 가격 레벨·틱 다름 → 트레이드 완전동일 기대 말 것, *통계적 근사*가 목표.

## 9. 구현 순서(플랜 태스크화)
1. `sessions.py`(tz 세션+아시안레인지) + 테스트
2. `strategy.py`(상태머신: 돌파/연속/엔트리/R:R/필터/엑싯) + 테스트
3. `run_xau_session_backtest.py`(저장 데이터 백테스트+통계) + 테스트
4. TV 대조(유저 백테스트 수치와 비교) → 충실도 확인
5. (후속) 라이브 페이퍼 엔진
