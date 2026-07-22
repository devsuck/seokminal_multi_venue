"""Signal Provider 어댑터 — 검증전략 → FusionEngine 연결(전략 로직 무수정).

import 시 PROVIDER_REGISTRY에 자기등록. registry strategy_id ↔ 어댑터 매핑은 명시적.
"""
from __future__ import annotations

from jarvis.fusion.adapters.buyback import BuybackPositionAdapter
from jarvis.fusion.adapters.tom import TurnOfMonthAdapter
from jarvis.fusion.adapters.tsmom import TsmomAdapter
from jarvis.fusion.providers import PROVIDER_REGISTRY


def _bind(provider):
    return lambda as_of="": provider.signals(as_of)


# registry strategy_id → 어댑터 인스턴스(명시 매핑, 암묵 매칭 금지)
ADAPTERS = {
    "kr_dart_buyback_drift_v1": BuybackPositionAdapter(),
    "kr_turn_of_month_v1_PORTFOLIO": TurnOfMonthAdapter(),
    "futures_tsmom": TsmomAdapter("futures_tsmom"),
    "futures_tsmom_32mkt": TsmomAdapter("futures_tsmom_32mkt"),
}


def register_all() -> list[str]:
    for sid, prov in ADAPTERS.items():
        PROVIDER_REGISTRY[sid] = _bind(prov)
    return list(ADAPTERS)


register_all()
