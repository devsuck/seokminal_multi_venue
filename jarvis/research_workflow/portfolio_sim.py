"""Portfolio Construction Simulator (P92) — 전략 조합 **의사결정 지원 시뮬레이션**. **자동 배분 없음.**

상관·중복·드로다운 상호작용·리스크 집중·레짐 노출을 분석하고 기대 수익/리스크/드로다운/스트레스 시나리오를
낸다. **재사용**: PortfolioIntelligence.combination_analysis(P61), cross_strategy(P83). 사람이 결정한다.

원칙(문서 §Constitution, §P92): 통합·조율만. 결정적. 자동 자본배분·거래·집행 없음.
"""
from __future__ import annotations


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def simulate(strategies: list, *, assistant=None) -> dict:
    """전략 조합 시뮬레이션(결정적, 읽기전용). strategies: [{name, returns?, max_drawdown?, regimes?, weight?}]."""
    strats = [s for s in (strategies or []) if isinstance(s, dict)]
    if len(strats) < 2:
        return {"strategies": [s.get("name") for s in strats], "note": "2개 이상 전략 필요.",
                "is_advisory": True, "is_decision": False}

    from jarvis.portfolio_research.intelligence import PortfolioIntelligence
    comb = PortfolioIntelligence().combination_analysis(strats)
    pairs = comb.pairs

    # 리스크 집중 — 가중치(주면) 또는 균등
    weights = [_num(s.get("weight")) for s in strats]
    if any(w is None for w in weights):
        weights = [1.0 / len(strats)] * len(strats)
    hhi = round(sum(w * w for w in weights), 4)      # 허핀달(집중도)

    # 드로다운 상호작용 — 최대 개별 mdd + 상관 조정(결정적 근사)
    mdds = [_num(s.get("max_drawdown")) for s in strats if _num(s.get("max_drawdown")) is not None]
    avg_corr = round(sum(abs(p["correlation"]) for p in pairs if p.get("correlation") is not None)
                     / max(1, len([p for p in pairs if p.get("correlation") is not None])), 4) if pairs else None
    combined_mdd = round(min(mdds) * (0.6 + 0.4 * (avg_corr or 0)), 4) if mdds else None

    # 레짐 노출 — 합집합
    regime_exposure = sorted({r for s in strats for r in (s.get("regimes") or [])})

    # 기대 프로파일(정성적, 결정적)
    diversifying = sum(1 for p in pairs if p.get("diversification") == "BENEFIT")
    redundant = sum(1 for p in pairs if p.get("diversification") == "REDUNDANT")
    risk_band = "LOW" if (avg_corr is not None and avg_corr < 0.3 and hhi < 0.4) else \
                "HIGH" if (hhi >= 0.5 or (avg_corr or 0) >= 0.6) else "MEDIUM"

    stress = []
    if hhi >= 0.5:
        stress.append("집중 리스크 — 단일 전략 실패 시 큰 손실")
    if avg_corr is not None and avg_corr >= 0.6:
        stress.append("높은 상관 — 동시 드로다운 위험")
    if not diversifying:
        stress.append("분산 이점 부족 — 조합의 리스크조정 개선 제한")
    if not stress:
        stress.append("특이 스트레스 신호 없음 — 다만 OOS·레짐 로버스트니스 확인")

    return {"strategies": [s.get("name", f"S{i}") for i, s in enumerate(strats)],
            "pairs": pairs, "correlation_avg": avg_corr, "overlap": [p.get("overlap") for p in pairs],
            "drawdown_interaction": combined_mdd, "risk_concentration_hhi": hhi,
            "regime_exposure": regime_exposure,
            "expected": {"return_profile": f"{diversifying} diversifying / {redundant} redundant pairs",
                         "risk": risk_band, "drawdown": combined_mdd, "stress_scenarios": stress},
            "verdict": comb.verdict,
            "is_advisory": True, "is_decision": False,
            "note": "조합 시뮬레이션 — 자동 배분 없음, 사람이 결정. 거래·집행 없음."}
