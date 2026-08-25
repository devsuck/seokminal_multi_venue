"""전략별 arm_criteria 호환 edge 판정 프로바이더 — 명시 레지스트리.

fusion/adapters/__init__.py의 "암묵 매칭 금지, 명시적 매핑" 원칙과 동일.
edge provider 없는 전략은 항상 GO 거부(정직한 기본값).
"""
from __future__ import annotations

import datetime as _dt
from typing import Callable

EdgeProviderFn = Callable[[], tuple[dict, float]]  # -> (edge_dict, paper_months)
EDGE_PROVIDERS: dict[str, EdgeProviderFn] = {}

# venue 미등록 = live_router가 "unsupported_venue"로 거부(안전한 기본값).
# tsmom은 futures/32개 시장이라 단일 venue 없음 — 의도적으로 비워둠.
EDGE_PROVIDER_VENUE: dict[str, str] = {}


def _buyback_edge_provider() -> tuple[dict, float]:
    from research.paper import buyback_config as CFG
    from research.paper.buyback_edge import edge_status
    s = edge_status()
    months = (_dt.date.today() - _dt.date.fromisoformat(CFG.FROZEN_AT)).days / 30.0
    return s, round(months, 1)


EDGE_PROVIDERS["kr_dart_buyback_drift_v1"] = _buyback_edge_provider
EDGE_PROVIDER_VENUE["kr_dart_buyback_drift_v1"] = "KR"


def _tsmom_edge_provider() -> tuple[dict, float]:
    from research.paper import tsmom_config as CFG
    from research.paper.tsmom_edge import edge_status
    s = edge_status()
    months = (_dt.date.today() - _dt.date.fromisoformat(CFG.FROZEN_AT)).days / 30.0
    return s, round(months, 1)


EDGE_PROVIDERS["futures_tsmom_32mkt"] = _tsmom_edge_provider
# venue 의도적 미등록 — _kr_last_close/_kr_position_qty가 KR 종목코드 전제라 futures엔 불가.
# live_router._build_order()가 venue!="KR"이면 "unsupported_venue"로 거부(안전).


def _tom_edge_provider() -> tuple[dict, float]:
    from research.paper import tom_config as CFG
    from research.paper.tom_edge import edge_status
    s = edge_status()
    months = (_dt.date.today() - _dt.date.fromisoformat(CFG.FROZEN_AT)).days / 30.0
    return s, round(months, 1)


EDGE_PROVIDERS["kr_turn_of_month_v1_PORTFOLIO"] = _tom_edge_provider
EDGE_PROVIDER_VENUE["kr_turn_of_month_v1_PORTFOLIO"] = "KR"


def edge_go(strategy_id: str) -> bool:
    """arm_criteria GO 여부. provider 없는 전략은 항상 False."""
    fn = EDGE_PROVIDERS.get(strategy_id)
    if fn is None:
        return False
    from jarvis.execution.arm_criteria import evaluate
    edge, months = fn()
    return evaluate(edge, months).get("decision") == "GO"
