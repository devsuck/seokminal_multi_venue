"""통제 카탈로그 — 전략 특성 → 필요한 결정적 통제. 오늘 교훈 encode.

각 통제 = 없으면 승격 못 하는 결정적 검사. LLM은 이걸 "요구"하고 코드가 실행.
"""
from __future__ import annotations

# 통제 카탈로그: id → 무엇을 잡나
CONTROLS = {
    "random_baseline": "매칭 random(같은 빈도·비용·보유) 이기나 — 운/베타 배제",
    "walk_forward": "전후반 분할 안정성 — 소멸/역전 잡음(turn-of-month·crypto momentum)",
    "cost_stress": "극단 비용(2~3x)서 생존 — 소형주·단타 비용사망 잡음",
    "multiple_testing": "여러 변형 = BH-FDR — 우연 통과 잡음(ICT unicorn·iFVG)",
    "survivorship": "PIT survivorship-free 유니버스 — 폐지종목 편향(유동성웨이브)",
    "lookahead": "신호에 미래봉 없나 — swings/fractal/centered 지표(ICT swings)",
    "entry_confound": "극단(저점/고점) 진입이면 = 같은 극단 baseline 통제 — 딥매수 착시(SMT)",
    "ex_date_adjustment": "권리락 수정주가 — 무상증자/분할/권리/큰배당(무상증자 -26% 아티팩트)",
    "outlier_dependence": "median vs mean·상위꼬리 기여 — right-tail 의존(buyback)",
    "capacity": "유동성 대비 배치가능 자본 — live 규모 현실성",
    "regime_dependence": "특정 레짐 집중? — 불장한정(crypto momentum)",
}

# 항상 필요한 기본 통제
_BASE = ["random_baseline", "walk_forward", "cost_stress"]


def required_controls(spec: dict) -> list[str]:
    """전략 특성 dict → 필요 통제 리스트. LLM(레드팀 MD)이 spec 채우면 결정적 매핑.

    spec 키(있으면): market · asset_class · entry · timeframe · event_type ·
                     n_variants · uses_swings · entry_at_extreme · stage · family
    """
    req = list(_BASE)
    market = str(spec.get("market", "")).upper()
    asset = str(spec.get("asset_class", "")).lower()
    family = str(spec.get("family", "")).lower()

    # 주식 유니버스 = survivorship 필수
    if market in ("KR", "US", "CRYPTO") or "equity" in asset or family in ("event", "factor", "seasonality"):
        req.append("survivorship")
    # 미래봉 신호(스윙/프랙탈/센터드) = lookahead
    if spec.get("uses_swings") or spec.get("uses_fractal") or str(spec.get("timeframe", "")) in ("1m", "5m", "15m"):
        req.append("lookahead")
    # 극단 진입 = confound 통제
    if spec.get("entry_at_extreme"):
        req.append("entry_confound")
    # 권리락 이벤트 = 수정주가
    if str(spec.get("event_type", "")) in ("bonus_issue", "stock_split", "rights", "large_dividend"):
        req.append("ex_date_adjustment")
    # 여러 변형 = 다중검정
    if int(spec.get("n_variants", 1)) > 1:
        req.append("multiple_testing")
    # 이벤트 = 팻테일 아웃라이어
    if family == "event":
        req.append("outlier_dependence")
    # live 후보 = 수용력
    if str(spec.get("stage", "")) in ("live_candidate", "micro_live", "paper_active"):
        req.append("capacity")
    # dedup 유지 순서
    seen, out = set(), []
    for c in req:
        if c not in seen:
            seen.add(c); out.append(c)
    return out
