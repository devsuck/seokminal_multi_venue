"""KR turn-of-month(월말진입) 포트폴리오-레벨 paper_candidate 동결 config (FROZEN — 튜닝 금지).

풀링(n=49057, 개별종목)은 상관 뻥튀기로 p 과장 — 포트레벨(월별 EW 1개, n=84)
재검이 진짜 기준선. 검증 통과 시점(2026-07-16) 그대로 고정.
"""
from __future__ import annotations

STATUS = "paper_candidate_yellow"  # REJECT 아님. WF 후반 급격히 약화(16배 감쇠) → forward-test 필수
VERSION = "kr_turn_of_month_v1_portfolio"
FROZEN_AT = "2026-07-16"

MARKETS = ["KOSPI", "KOSDAQ"]
LIQUID_FILTER = {"min_bars": 300, "min_tval_20d": 1e9, "min_marcap": 5e10}
ENTRY = "month_end_close_approx"  # 월 마지막 거래일 종가 인덱스에서 진입(기존 검증과 동일 정의)
HOLD_DAYS = 4
COST_BASE_BPS = 40.0  # 왕복

# 검증 기준선(포트레벨, 상관보정)
BASELINE = {
    "n_months": 84, "net_mean": 0.006221, "random_pct": 100.0, "p_value": 0.002,
    "wf_first": 0.011704, "wf_second": 0.000738,
}
# ⚠️ WF 후반(+0.07%)이 전반(+1.17%)보다 16배 약함 — 감쇠 추세일 수 있음.
#    개별종목 풀링(n=49057) 버전은 WEAK(상관 뻥튀기 의심)였음 — 포트레벨만 신뢰.

CAPITAL = 0
MONITORING = "monthly"
MIN_OBSERVATION_MONTHS = 3
PREFERRED_OBSERVATION_MONTHS = 12

FORBIDDEN = [
    "hold 4일 변경", "entry를 월말 종가 아닌 다른 시점으로", "유동성 필터 완화",
    "cost 완화", "특정 섹터/종목 overweight", "paper 1~2개월 좋다고 live",
    "분해 결과로 파라미터 튜닝",
]
