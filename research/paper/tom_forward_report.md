# KR Turn-of-Month Portfolio Forward-Test — kr_turn_of_month_v1_portfolio

> **paper_candidate_yellow** · ⚠️ PAPER ONLY, NO LIVE. config 동결(entry=month_end_close_approx, hold=4d, cost=40.0bps)
> ⚠️ backtest WF 후반이 전반보다 16배 약함(감쇠 의심) — forward가 진짜 시금석.

## Overall (완결 월코호트)
- 월수=84 · 평균 0.006221 · 승률 0.619

## Envelope (월 코호트 평균 분포)
- 월수 84 · 평균 P10 -0.028996 / P90 0.046201 · 평균 0.006221

## Forward 월 코호트 (envelope 비교)
- (--since 지정 필요, 매월 신규 데이터 pull 후 재실행)

## 운영 원칙
- live 금지. entry/hold/cost/유동성필터 변경 금지. 분해결과로 튜닝 금지.
- WF 감쇠 의심 → forward에서도 약화 지속되면 KILL 후보.
