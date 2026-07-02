"""KR 자사주(buyback) 이벤트 paper_candidate 동결 config (FROZEN — 튜닝 금지).

검증 통과 시점(Phase 110) 그대로 고정. 분해 결과로 파라미터 변경 금지.
"""
from __future__ import annotations

STATUS = "paper_candidate_forward_test_required"
VERSION = "kr_buyback_drift_v1"
FROZEN_AT = "2026-07-02"

EVENT = "buyback"                 # 자기주식취득(직접+신탁), 처분 제외
MARKETS = ["KOSPI", "KOSDAQ"]
ENTRY = "next_open"              # 공시 다음 거래일 시가 (announcement-close는 lookahead)
HOLD_DAYS = 20
COST_BASE_BPS = 40.0            # 왕복 (=20bps/side)
COST_STRESS_BPS = 100.0

# 검증 기준선(전체 PIT/survivorship-free)
BASELINE = {
    "trade_count": 1735, "net_base": 0.0173, "random_pct": 97.0, "p": 0.032,
    "net_stress_50": 0.0113, "wf_first": 0.0131, "wf_second": 0.0215,
    "rights_contrast_base": 0.0010,
}

CAPITAL = 0
MONITORING = "monthly"
MIN_OBSERVATION_MONTHS = 3
PREFERRED_OBSERVATION_MONTHS = 12

FORBIDDEN = [
    "holding period 변경", "entry timing을 announcement-close(lookahead)로",
    "특정 공시유형만 사후선택", "특정 섹터/시총 overweight",
    "cost 완화", "관리종목 포함", "paper 1~2개월 좋다고 live",
    "분해 결과로 파라미터 튜닝",
]
