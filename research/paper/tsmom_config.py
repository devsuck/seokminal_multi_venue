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
