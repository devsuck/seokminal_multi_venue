"""전략별 arm_criteria 호환 edge 판정 프로바이더 — 명시 레지스트리.

fusion/adapters/__init__.py의 "암묵 매칭 금지, 명시적 매핑" 원칙과 동일.
edge provider 없는 전략은 항상 GO 거부(정직한 기본값) — tsmom/turn-of-month는
아직 arm_criteria 호환 edge 함수가 없어 자동 배제(provider 추가하면 재작업 없이 편입).
"""
from __future__ import annotations

import datetime as _dt
from typing import Callable

EdgeProviderFn = Callable[[], tuple[dict, float]]  # -> (edge_dict, paper_months)
EDGE_PROVIDERS: dict[str, EdgeProviderFn] = {}

# venue는 registry.asset_class로 못 뗌 — 전부 None(08-26 확인, 아무도 안 채움).
EDGE_PROVIDER_VENUE: dict[str, str] = {}


def _buyback_edge_provider() -> tuple[dict, float]:
    from research.paper import buyback_config as CFG
    from research.paper.buyback_edge import edge_status
    s = edge_status()
    months = (_dt.date.today() - _dt.date.fromisoformat(CFG.FROZEN_AT)).days / 30.0
    return s, round(months, 1)


EDGE_PROVIDERS["kr_dart_buyback_drift_v1"] = _buyback_edge_provider
EDGE_PROVIDER_VENUE["kr_dart_buyback_drift_v1"] = "KR"


def edge_go(strategy_id: str) -> bool:
    """arm_criteria GO 여부. provider 없는 전략은 항상 False."""
    fn = EDGE_PROVIDERS.get(strategy_id)
    if fn is None:
        return False
    from jarvis.execution.arm_criteria import evaluate
    edge, months = fn()
    return evaluate(edge, months).get("decision") == "GO"
