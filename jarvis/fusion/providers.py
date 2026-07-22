"""신호 프로바이더 — registry 검증전략 → StrategySignal 어댑터.

정직: PROVIDER_REGISTRY는 비어 있음(= 라이브 계기신호 어댑터 아직 미배선).
agent_gate.PROFILE_TO_STRATEGY가 빈 것과 같은 원칙. 어댑터가 붙기 전엔
validated 전략에서 신호가 안 나온다(가짜신호 금지).
"""
from __future__ import annotations

from typing import Callable, Protocol

from jarvis.fusion.types import StrategySignal

# fusion-eligible = registry에서 이 상태 이상(사전등록 게이트 통과분)
FUSION_ELIGIBLE_STATUSES = {"paper_active", "micro_live", "constrained_live", "live"}


class SignalProvider(Protocol):
    strategy_id: str

    def signals(self, as_of: str = "") -> list[StrategySignal]:
        ...


class StaticSignalProvider:
    """명시 신호 프로바이더 — 테스트/수동주입용."""

    def __init__(self, strategy_id: str, sigs: list[StrategySignal]) -> None:
        self.strategy_id = strategy_id
        self._sigs = sigs

    def signals(self, as_of: str = "") -> list[StrategySignal]:
        return list(self._sigs)


# strategy_id → 프로바이더 팩토리(as_of -> list[StrategySignal]).
# 검증전략의 계기신호 어댑터가 준비되면 여기에 명시적으로 등록.
PROVIDER_REGISTRY: dict[str, Callable[[str], list[StrategySignal]]] = {}


def eligible_strategy_ids() -> list[str]:
    """registry에서 fusion 대상 전략 id."""
    from jarvis.registry import StrategyRegistry
    return [r["strategy_id"] for r in StrategyRegistry().all_current()
            if r["status"] in FUSION_ELIGIBLE_STATUSES]


def collect_signals(as_of: str = "") -> tuple[list[StrategySignal], list[dict]]:
    """검증전략들의 신호 수집. 반환: (신호목록, 스킵로그[정직]).

    어댑터 없는 전략은 스킵(사유 기록). PROVIDER_REGISTRY 비면 전부 스킵.
    """
    sigs: list[StrategySignal] = []
    skipped: list[dict] = []
    for sid in eligible_strategy_ids():
        fac = PROVIDER_REGISTRY.get(sid)
        if fac is None:
            skipped.append({"strategy_id": sid, "reason": "no_signal_adapter"})
            continue
        try:
            sigs.extend(fac(as_of))
        except Exception as exc:  # noqa: BLE001
            skipped.append({"strategy_id": sid, "reason": f"provider_error:{exc}"})
    return sigs, skipped
