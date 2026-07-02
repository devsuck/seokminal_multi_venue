"""TSMOM paper_candidate 동결 config (FROZEN — 튜닝 금지).

이 스펙은 검증 통과 시점(Phase 102) 그대로 고정. forward-test는 이걸 사용.
변경 금지: universe / lookback / rebalance / risk target / cost.
sleeve 제거·추가·가중치·레짐필터 추가 금지.
"""
from __future__ import annotations

STATUS = "paper_candidate_forward_test_required"
VERSION = "tsmom_32mkt_v1"
FROZEN_AT = "2026-07-02"

# 32시장 (검증 통과 그대로)
UNIVERSE = [
    "ES", "NQ", "RTY", "YM", "EMD", "NKD",           # equity
    "ZN", "ZB", "ZF", "ZT", "UB", "ZQ",               # rates
    "GC", "SI", "HG", "PL", "PA",                     # metals
    "CL", "NG", "RB", "HO",                           # energy
    "ZC", "ZS", "ZW", "ZL", "ZM",                     # grains
    "KC", "SB", "CT", "CC",                           # softs
    "LE", "HE",                                       # livestock
]

PARAMS = {"lookback": 252, "vol_window": 60, "target_vol": 0.15, "cap": 3.0}
REBALANCE_DAYS = 21
COST_BASE_BPS = 2.0     # primary
COST_STRESS_BPS = 20.0  # 병행 스트레스

# 검증 시점 성과(참조 기준선) — forward-test가 이 봉투 안인지 비교
BASELINE = {
    "sharpe": 0.562, "ann_return": 0.0513, "max_drawdown": -0.1696,
    "sharpe_5bps": 0.547, "random_pct_n1000": 97.1, "p_n1000": 0.03,
    "wf_first": 0.453, "wf_second": 0.423,
}

# 관찰 창
CAPITAL = 0                       # live 금지
MONITORING = "monthly"
MIN_OBSERVATION_MONTHS = 3        # 최소 3~6개월
PREFERRED_OBSERVATION_MONTHS = 12

# 금지(성과 나빠도 절대 하지 말 것 — 하면 데이터 스누핑/규율 붕괴)
FORBIDDEN = [
    "레짐필터 추가", "rates 등 sleeve 제거", "softs 등 sleeve 비중 확대",
    "lookback 변경", "rebalance 주기 변경", "vol target 변경",
    "cost 가정 완화", "paper 1~2개월 좋다고 live 진입",
]

# 월간 리포트에서 볼 것 (수익률 하나 아님)
MONTHLY_CHECKLIST = [
    "월수익이 backtest envelope(P10/P90) 안인가",
    "trend_regime_score와 성과가 논리적으로 맞는가",
    "특정 sleeve 하나가 계속 과도하게 끄는가",
    "turnover/cost drag가 백테스트와 비슷한가",
    "drawdown이 과거 범위 안인가",
    "3~6개월 누적이 기대 행동과 비슷한가 (한 달 이탈은 OK, 반복 이탈은 경고)",
]
