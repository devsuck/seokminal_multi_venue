"""KR 횡단면 팩터 paper_candidate 동결 config (FROZEN — 튜닝 금지).

research/autoresearch/engines_factor.py의 사전등록 스펙(월말 리밸런스 L-S quintile,
cost 80bps/월, permutation p) 그대로. forward-test(factor_forward.py)는 이 baseline과
frozen_at을 사용 — engines_factor.py 자체는 수정하지 않는다(동결 모듈).
CANDIDATES 3개는 2026-08-25 registry 스냅샷(251일 연속 재현) 그대로 고정.
"""
from __future__ import annotations

STATUS = "paper_candidate_forward_test_required"
FROZEN_AT = "2026-08-25"
COST_BASE_BPS = 80.0    # engines_factor.COST_M
COST_STRESS_BPS = 160.0  # engines_factor.STRESS_M

CANDIDATES = {
    "kr_size_smb": {
        "version": "fac_kr_size_smb_v1",
        "thesis": "소형주 프리미엄(SMB)",
        "long_low": True, "signal": "marcap",
        "baseline": {"n": 82, "net": 0.042305, "percentile": 100.0, "p": 0.0033,
                     "wf_first": 0.043223, "wf_second": 0.041387},
    },
    "kr_amihud_illiq": {
        "version": "fac_kr_amihud_illiq_v1",
        "thesis": "Amihud 비유동성 프리미엄 — 비유동 보유 보상. 비용 스트레스가 심판",
        "long_low": False, "signal": "amihud",
        "baseline": {"n": 82, "net": 0.016354, "percentile": 100.0, "p": 0.0033,
                     "wf_first": 0.015717, "wf_second": 0.016992},
    },
    "kr_turnover_neglect": {
        "version": "fac_kr_turnover_neglect_v1",
        "thesis": "저회전(neglected) 프리미엄 — 관심 밖 종목 보상",
        "long_low": True, "signal": "turnover",
        "baseline": {"n": 82, "net": 0.012017, "percentile": 100.0, "p": 0.0033,
                     "wf_first": 0.007855, "wf_second": 0.016178},
    },
}

# 관찰 창
CAPITAL = 0                       # live 금지
MONITORING = "monthly"
MIN_OBSERVATION_MONTHS = 3        # 최소 3~6개월
PREFERRED_OBSERVATION_MONTHS = 12

# 금지(성과 나빠도 절대 하지 말 것 — 하면 데이터 스누핑/규율 붕괴)
FORBIDDEN = [
    "신호 정의 변경(marcap/amihud/turnover)", "L-S quintile 비율(20%) 변경",
    "월말 리밸런스 주기 변경", "cost 가정 완화", "direction=research를 실제 롱온리로 전환(별도 사전등록 필요)",
    "paper 1~2개월 좋다고 live 진입",
]

MONTHLY_CHECKLIST = [
    "월수익이 backtest envelope(P10/P90) 안인가",
    "3개 팩터 상관관계가 과도하지 않은가(같은 소형주 편향 중복 아닌지)",
    "turnover/cost drag가 백테스트(80bps) 가정과 비슷한가",
    "3~6개월 누적이 기대 행동과 비슷한가(한 달 이탈은 OK, 반복 이탈은 경고)",
]
