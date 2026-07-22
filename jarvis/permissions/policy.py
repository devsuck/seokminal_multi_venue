"""권한 정책 — 결정적. 모든 시도는 감사 로그에 남는다.

규칙:
- FORBIDDEN 액션은 누구도(사람 포함 코드경로) 못 함.
- ADMIN_HUMAN_ONLY 액션은 사람 principal만(어떤 AI 에이전트도 불가).
- 그 외 = principal 레벨 랭크 >= 요구 레벨 랭크.
- AI 에이전트는 자기 레벨을 못 올린다(레벨은 생성 시 사람이 부여).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from jarvis.audit import record


class Level(IntEnum):
    READ_ONLY = 0
    RESEARCH_ONLY = 1
    BACKTEST_ONLY = 2
    PAPER_ONLY = 3
    LIVE_PROPOSAL_ONLY = 4
    MICRO_LIVE_EXECUTION = 5
    CONSTRAINED_LIVE_EXECUTION = 6
    ADMIN_HUMAN_ONLY = 7


# 액션 → 요구 권한(문자열은 Level 이름 또는 "FORBIDDEN").
ACTION_PERMISSIONS: dict[str, str] = {
    "read_registry": "READ_ONLY",
    "read_market_memory": "READ_ONLY",
    "create_strategy_hypothesis": "RESEARCH_ONLY",
    "propose_data_source": "RESEARCH_ONLY",
    "request_data_audit": "RESEARCH_ONLY",
    "write_research_memo": "RESEARCH_ONLY",
    "register_rejected_strategy": "RESEARCH_ONLY",
    "add_market_lesson": "RESEARCH_ONLY",
    "run_data_gate": "BACKTEST_ONLY",
    "run_backtest": "BACKTEST_ONLY",
    "critic_review": "BACKTEST_ONLY",
    "promote_to_watchlist": "BACKTEST_ONLY",
    "promote_to_paper_candidate": "BACKTEST_ONLY",
    "create_paper_order": "PAPER_ONLY",
    "record_paper_fill": "PAPER_ONLY",
    "promote_to_paper_active": "PAPER_ONLY",
    "write_fusion_signal": "PAPER_ONLY",
    "propose_allocation": "LIVE_PROPOSAL_ONLY",
    "propose_rebalance": "LIVE_PROPOSAL_ONLY",
    "write_portfolio_journal": "PAPER_ONLY",
    "portfolio_state_transition": "PAPER_ONLY",
    "record_turnover": "PAPER_ONLY",
    "create_live_order_proposal": "LIVE_PROPOSAL_ONLY",
    "execute_micro_live_order": "MICRO_LIVE_EXECUTION",
    "execute_constrained_live_order": "CONSTRAINED_LIVE_EXECUTION",
    # 사람만 —
    "modify_risk_limit": "ADMIN_HUMAN_ONLY",
    "modify_live_config": "ADMIN_HUMAN_ONLY",
    "modify_frozen_config": "ADMIN_HUMAN_ONLY",
    "raise_autonomy_level": "ADMIN_HUMAN_ONLY",
    "change_validation_threshold": "ADMIN_HUMAN_ONLY",
    "approve_live_promotion": "ADMIN_HUMAN_ONLY",
    # 영구 금지 —
    "delete_audit_log": "FORBIDDEN",
    "rewrite_registry_history": "FORBIDDEN",
    "revive_rejected_strategy": "FORBIDDEN",
    "expand_own_permission": "FORBIDDEN",
    "loosen_cost_after_result": "FORBIDDEN",
    "drop_bad_period_after_result": "FORBIDDEN",
}

FORBIDDEN = {a for a, p in ACTION_PERMISSIONS.items() if p == "FORBIDDEN"}


@dataclass(frozen=True)
class Principal:
    """행위 주체. AI 에이전트 또는 사람. 레벨은 생성 시 고정(자가 확장 불가)."""
    name: str
    level: Level
    is_human: bool = False


class PermissionDenied(Exception):
    pass


def _required(action: str) -> str | None:
    return ACTION_PERMISSIONS.get(action)


def check(principal: Principal, action: str, resource: str = "") -> bool:
    """허용 여부 판정 + 감사 로그. 예외 안 던짐(bool 반환)."""
    required = _required(action)
    granted = False
    reason = ""
    if required is None:
        reason = "unknown_action"
    elif action in FORBIDDEN or required == "FORBIDDEN":
        reason = "forbidden_forever"
    elif required == "ADMIN_HUMAN_ONLY":
        granted = principal.is_human and principal.level >= Level.ADMIN_HUMAN_ONLY
        reason = "admin_human_only" if not granted else "ok"
    else:
        need = Level[required]
        granted = principal.level >= need
        reason = "ok" if granted else "insufficient_level"

    record({
        "layer": "permissions", "agent": principal.name,
        "principal_level": principal.level.name, "is_human": principal.is_human,
        "action": action, "permission_required": required,
        "permission_granted": granted, "resource": resource,
        "result": "allowed" if granted else "denied", "reason": reason,
    })
    return granted


def require(principal: Principal, action: str, resource: str = "") -> None:
    """허용 아니면 PermissionDenied. 감사 로그는 check()가 남김."""
    if not check(principal, action, resource):
        raise PermissionDenied(f"{principal.name} denied '{action}' (required={_required(action)})")
