"""Portfolio State Machine (P2.4 F4) — 포트폴리오 수준 생애주기. 이벤트소싱·append-only.

registry FSM 철학: 불법전이 거부, 현재상태=이벤트 폴드, 삭제/재작성 없음.
portfolio_state.jsonl: {previous_state, new_state, reason, timestamp}.
"""
from __future__ import annotations

import json
import os
from enum import Enum

from jarvis.agents import META_PORTFOLIO_AGENT
from jarvis.audit import record
from jarvis.config import state_path
from jarvis.permissions import require

_STATE = "portfolio_state.jsonl"


class PortfolioState(str, Enum):
    INITIALIZING = "INITIALIZING"
    MONITORING = "MONITORING"
    REBALANCE_PENDING = "REBALANCE_PENDING"
    REBALANCED = "REBALANCED"
    RISK_REDUCTION = "RISK_REDUCTION"
    DEFENSIVE = "DEFENSIVE"
    HALTED = "HALTED"


S = PortfolioState
STATES = [s.value for s in PortfolioState]

# 합법 전이표(없으면 IllegalPortfolioTransition)
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    S.INITIALIZING.value: {S.MONITORING.value, S.HALTED.value},
    S.MONITORING.value: {S.REBALANCE_PENDING.value, S.RISK_REDUCTION.value,
                         S.DEFENSIVE.value, S.HALTED.value},
    S.REBALANCE_PENDING.value: {S.REBALANCED.value, S.MONITORING.value, S.HALTED.value},
    S.REBALANCED.value: {S.MONITORING.value, S.HALTED.value},
    S.RISK_REDUCTION.value: {S.MONITORING.value, S.DEFENSIVE.value, S.HALTED.value},
    S.DEFENSIVE.value: {S.MONITORING.value, S.HALTED.value},
    S.HALTED.value: {S.MONITORING.value},
}


class IllegalPortfolioTransition(Exception):
    pass


def _v(x) -> str:
    return x.value if isinstance(x, PortfolioState) else str(x)


class PortfolioStateMachine:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or state_path(_STATE)

    def _events(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        with open(self.path) as f:
            return [json.loads(ln) for ln in f if ln.strip()]

    def current(self) -> str:
        ev = self._events()
        return ev[-1]["new_state"] if ev else S.INITIALIZING.value

    def history(self) -> list[dict]:
        return self._events()

    def transition(self, new_state, reason: str, ts: str = "",
                   principal=META_PORTFOLIO_AGENT) -> dict:
        require(principal, "portfolio_state_transition", _v(new_state))
        cur = self.current()
        to = _v(new_state)
        allowed = ALLOWED_TRANSITIONS.get(cur, set())
        if to not in allowed:
            record({"layer": "portfolio_state", "action": "transition",
                    "from": cur, "to": to, "reason": reason, "result": "denied"})
            raise IllegalPortfolioTransition(f"{cur} → {to} 불법(허용: {sorted(allowed)})")
        ev = {"previous_state": cur, "new_state": to, "reason": reason, "timestamp": ts}
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")
        record({"layer": "portfolio_state", "action": "transition", "from": cur, "to": to,
                "reason": reason, "result": "committed"})
        return ev

    def can_transition(self, new_state) -> bool:
        return _v(new_state) in ALLOWED_TRANSITIONS.get(self.current(), set())
