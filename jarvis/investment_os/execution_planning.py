"""Execution Layer — 계획·시뮬레이션·준비도 사다리. **실제 주문 라우팅 없음(브로커 미연결).**

실행 사다리: PAPER → SHADOW → SMALL_CAPITAL → PRODUCTION_CANDIDATE → (선택)AUTO_EXECUTION.
  · **AUTO_EXECUTION 은 영구 비활성(기본).** 사람 승인 필수. 게이트 우회 불가.
  · Investment OS 는 **주문을 실행하지 않는다** — 계획(plan)과 시뮬레이션(simulate)만. 실제 라우팅은
    별도 브로커 계층(자격증명 없음 → 구조적으로 실행 불가). Kill switch 는 전부 PAPER 로 강제.

이 모듈은 execute()/place_order()/trade() 를 **정의하지 않는다.** 계획·시뮬레이션만.
"""
from __future__ import annotations

from jarvis.investment_os import (
    AUTO_EXECUTION_ENABLED,
    EXECUTION_RUNGS,
    HUMAN_APPROVAL_MANDATORY,
)

# 사다리에서 사람 승인 없이는 전진 불가. AUTO_EXECUTION 은 추가로 영구 비활성.
_TERMINAL_DISABLED = "AUTO_EXECUTION"


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def kill_switch_status() -> dict:
    """Kill switch — 걸리면 모든 것을 PAPER 로 강제. 기본 clear. 사람이 개입해 engage/clear."""
    # 라이브 실행 비활성이면 kill switch 는 사실상 상시 안전(추가 방어)
    live = _safe(lambda: __import__("jarvis.config",
                                    fromlist=["live_execution_enabled"]).live_execution_enabled(), False)
    return {"engaged": False, "live_execution_enabled": bool(live),
            "forces_rung": "PAPER", "is_advisory": True, "is_decision": False,
            "note": "Kill switch — 걸리면 전부 PAPER 강제. 라이브 실행 비활성이 기본 방어."}


class ExecutionLadder:
    """실행 준비도 사다리 — 사람 승인 + 4게이트 통과로만 전진. AUTO_EXECUTION 영구 비활성. 실행 아님."""

    def __init__(self, rung: str = "PAPER") -> None:
        self.rung = rung if rung in EXECUTION_RUNGS else "PAPER"

    def _next(self) -> str:
        i = EXECUTION_RUNGS.index(self.rung)
        return EXECUTION_RUNGS[i + 1] if i + 1 < len(EXECUTION_RUNGS) else self.rung

    def advance(self, portfolio: dict, *, human_approved: bool = False) -> dict:
        """다음 사다리로 전진 시도. 사람 승인 필수 + 4게이트 통과 필수. AUTO_EXECUTION 은 영구 차단."""
        nxt = self._next()
        gates = _safe(lambda: __import__("jarvis.investment_os.gates",
                                         fromlist=["evaluate_gates"]).evaluate_gates(portfolio),
                      {"passed": False, "failed_gates": ["unknown"]})
        # 1) AUTO_EXECUTION 영구 비활성 — 승인·게이트와 무관하게 차단
        if nxt == _TERMINAL_DISABLED and not AUTO_EXECUTION_ENABLED:
            return {"advanced": False, "rung": self.rung, "blocked_reason": "AUTO_EXECUTION permanently disabled",
                    "auto_execution_enabled": False, "requires_human_review": True, "is_decision": False}
        # 2) 사람 승인 필수
        if HUMAN_APPROVAL_MANDATORY and not human_approved:
            return {"advanced": False, "rung": self.rung, "blocked_reason": "human approval required",
                    "requires_human_review": True, "is_decision": False}
        # 3) 4게이트 우회 불가
        if not gates.get("passed"):
            return {"advanced": False, "rung": self.rung, "blocked_reason": "mandatory gates failed",
                    "failed_gates": gates.get("failed_gates", []), "is_decision": False}
        self.rung = nxt
        return {"advanced": True, "rung": self.rung, "gates_passed": True, "human_approved": True,
                "requires_human_review": True, "is_advisory": True, "is_decision": False,
                "note": "사다리 전진 — 사람 승인 + 4게이트 통과. AUTO_EXECUTION 은 영구 차단. 실제 주문 없음."}


def advance_rung(current_rung: str, portfolio: dict, *, human_approved: bool = False) -> dict:
    """모듈 진입점 — 사다리 전진(사람 승인 + 게이트). AUTO_EXECUTION 영구 비활성."""
    return ExecutionLadder(current_rung).advance(portfolio, human_approved=human_approved)


def plan_execution(target_weights: dict, current_weights: dict | None = None) -> dict:
    """실행 **계획**(주문 아님) — 목표 vs 현재 → 리밸런스 스케줄(계획). 실제 라우팅 없음."""
    cur = current_weights or {}
    orders_plan = []
    for sym in sorted(set(target_weights or {}) | set(cur)):
        delta = round(float((target_weights or {}).get(sym, 0.0)) - float(cur.get(sym, 0.0)), 4)
        if abs(delta) > 1e-6:
            orders_plan.append({"symbol": sym, "side": "increase" if delta > 0 else "decrease",
                                "weight_delta": delta})
    return {"planned_adjustments": orders_plan, "count": len(orders_plan),
            "is_plan_only": True, "routes_orders": False,
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": "Execution Plan(계획만) — 리밸런스 스케줄. 실제 주문 라우팅 없음(브로커 미연결). 사람 승인 필수."}


def simulate_orders(orders_plan, *, cost_bps: float = 10.0, notional: float = 0.0) -> dict:
    """주문 **시뮬레이션**(실제 체결 아님) — 계획된 조정에 비용/슬리피지 적용한 가상 결과. 실행 없음."""
    adjustments = orders_plan.get("planned_adjustments") if isinstance(orders_plan, dict) else (orders_plan or [])
    turnover = round(sum(abs(float(o.get("weight_delta", 0.0))) for o in adjustments), 4)
    est_cost = round(turnover * (cost_bps / 10000.0) * (notional or 0.0), 2)
    return {"simulated": True, "is_real_fill": False, "turnover": turnover,
            "estimated_cost": est_cost, "cost_bps": cost_bps, "notional": notional,
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": "Order Simulation(가상) — 실제 체결 아님. 비용/슬리피지 추정. 실행·주문 라우팅 없음."}
