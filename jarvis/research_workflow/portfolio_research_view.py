"""Portfolio Research View (P164) — **연구 관점만.** 배분 제안 없음. 읽기 전용.

**재사용**: portfolio intelligence(portfolio_sim)·cross asset intelligence(P156)·strategy health(P144)·
risk intelligence. 표시: sector exposure·factor exposure·strategy overlap·correlation·concentration·
scenario comparison. **배분(allocation) 제안 없음** — 연구 관점의 노출/중첩/상관 뷰일 뿐.

원칙(문서 §Constitution, §P164): 통합·조율만. 결정적. 거래·집행·배분 없음. 사람 결정.
"""
from __future__ import annotations


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def build_portfolio_research(*, strategies: list | None = None, correlations: dict | None = None,
                             market: dict | None = None, assistant=None) -> dict:
    """포트폴리오 연구 뷰(읽기전용) — 노출·중첩·상관·집중·시나리오. 배분 제안 없음. 결정적."""
    # 전략 건강 보드 — strategy_health(P144)
    health = _safe(lambda: __import__("jarvis.research_workflow.strategy_health",
                                      fromlist=["StrategyHealthMonitor"]).StrategyHealthMonitor()
                   .board(strategies=strategies), {"strategies": []})
    rows = health.get("strategies", [])

    # 교차자산 상관/전이 — cross_asset_intelligence(P156)
    cross = _safe(lambda: __import__("jarvis.research_workflow.cross_asset_intelligence",
                                     fromlist=["build_cross_asset"])
                  .build_cross_asset(correlations=correlations, market=market, assistant=assistant), {})

    # 전략 중첩(결정적) — 같은 리스크 프로파일/이름 유형끼리
    overlap = _strategy_overlap([r["strategy"] for r in rows])

    # 섹터/팩터 노출(결정적, 연구 관점) — 전략 유형 분포
    factor_exposure = _factor_exposure([r["strategy"] for r in rows])

    # 집중도(결정적)
    concentration = {"n_strategies": len(rows),
                     "review_needed": health.get("review_needed_count", 0),
                     "concentration": "HIGH" if len(rows) and len(rows) <= 3 else "MODERATE"}

    # 시나리오 비교(결정적, 레짐별 관점) — 배분 아님
    scenarios = [
        {"scenario": "regime_shift", "note": "레짐 전환 시 고상관 전략 동조화 위험", "research_focus": "레짐 로버스트니스"},
        {"scenario": "high_vol", "note": "변동성 확대 시 회전율 높은 전략 비용 잠식", "research_focus": "비용 민감도"},
    ]
    return {"strategy_health": rows,
            "sector_exposure": {"note": "섹터 노출은 연구 관점 — 전략 유형 분포 기반", "distribution": factor_exposure},
            "factor_exposure": factor_exposure,
            "strategy_overlap": overlap,
            "correlation": cross.get("correlations", []),
            "relationship_changes": cross.get("relationship_changes", []),
            "concentration": concentration,
            "scenario_comparison": scenarios,
            "current_regime": cross.get("current_regime"),
            "report_type": "PortfolioResearchView",
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("PortfolioResearchView(읽기전용) — 노출·중첩·상관·집중·시나리오. 배분 제안 아님. "
                     "portfolio_sim/cross_asset/strategy_health/risk 재사용, 새 저장소 없음.")}


def _strategy_overlap(names) -> list:
    """전략 유형별 중첩(결정적) — risk 프로파일 유형이 같으면 중첩."""
    try:
        from jarvis.research_risk_intelligence.failure_reasoning import _profile
        by_type: dict = {}
        for n in names:
            by_type.setdefault(_profile(n)["type"], []).append(n)
        return [{"type": k, "strategies": v, "overlap": "HIGH" if len(v) > 1 else "NONE"}
                for k, v in by_type.items() if len(v) > 1]
    except Exception:  # noqa: BLE001
        return []


def _factor_exposure(names) -> dict:
    try:
        from jarvis.research_risk_intelligence.failure_reasoning import _profile
        dist: dict = {}
        for n in names:
            typ = _profile(n)["type"]
            dist[typ] = dist.get(typ, 0) + 1
        return dist
    except Exception:  # noqa: BLE001
        return {}
