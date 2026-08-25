"""Lv4 — Micro-live ARM. 사람만 전략을 micro-live 실행에 무장(arm)한다.

이중 게이트: ①사람 ADMIN이 명시 arm ②autonomy level >= MIN_LIVE_LEVEL.
level 4에선 무장해도 Execution Gateway가 여전히 BLOCK(안전). arm = 사람 승인 기록.
승격 규칙: paper_active → live_candidate(사람) → micro_live(사람 + 최소 6개월 페이퍼).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from jarvis.audit import record
from jarvis.config import state_path
from jarvis.permissions import Level, PermissionDenied, Principal, require
from jarvis.registry import Status, StrategyRegistry

_ARM = "microlive_arms.jsonl"
_AUTO_EXECUTION_APPROVAL = "auto_execution_approval.json"
MIN_PAPER_MONTHS = 6
_ARMABLE = {Status.LIVE_CANDIDATE.value, Status.MICRO_LIVE.value}


def record_auto_execution_approval(human: Principal, note: str) -> dict:
    """investment_os.AUTO_EXECUTION_ENABLED=True에 대한 사람 승인 기록. 사람만.

    이 플래그는 Investment OS 어디에도 execute()가 없어 실제로 무엇도 게이트하지
    않지만(진짜 게이트는 jarvis.config.AUTONOMY_LEVEL), separation.py의 self-test는
    이 기록 없이는 invariant를 실패로 표시한다 — 사람이 의식적으로 확인했다는
    감사 흔적을 남기기 위함."""
    if not human.is_human or human.level < Level.ADMIN_HUMAN_ONLY:
        raise PermissionDenied("auto_execution 승인은 사람 ADMIN만")
    row = {"approved_by": human.name, "note": note,
           "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    with open(state_path(_AUTO_EXECUTION_APPROVAL), "w") as f:
        json.dump(row, f, ensure_ascii=False)
    record({"layer": "arm", "action": "record_auto_execution_approval",
            "approved_by": human.name, "result": "recorded"})
    return row


def auto_execution_approved() -> bool:
    return os.path.exists(state_path(_AUTO_EXECUTION_APPROVAL))


def _arms() -> list[dict]:
    p = state_path(_ARM)
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def arm_state(strategy_id: str) -> dict | None:
    """최신 arm/disarm 상태."""
    cur = None
    for a in _arms():
        if a.get("strategy_id") == strategy_id:
            cur = a
    return cur


def is_armed(strategy_id: str) -> bool:
    a = arm_state(strategy_id)
    return bool(a and a.get("armed"))


def _append(row: dict) -> None:
    os.makedirs(os.path.dirname(state_path(_ARM)), exist_ok=True)
    with open(state_path(_ARM), "a") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def check_micro_live_eligible(strategy_id: str, paper_months: float) -> dict:
    """micro-live 승격 자격(구조적). 최소 페이퍼 기간 등."""
    st = StrategyRegistry().state(strategy_id)
    reasons = []
    if st is None:
        reasons.append("not_registered")
    elif st["status"] not in _ARMABLE:
        reasons.append(f"not_live_candidate({st['status'] if st else '-'})")
    if paper_months < MIN_PAPER_MONTHS:
        reasons.append(f"insufficient_paper_months({paper_months}<{MIN_PAPER_MONTHS})")
    return {"eligible": not reasons, "reasons": reasons}


def arm(strategy_id: str, human: Principal, capital_limit: float, max_order_qty: float = 1.0,
        paper_months: float = 0.0, kill_switch: bool = False) -> dict:
    """사람만 arm. 자격검사 + 감사. level<6이면 무장해도 실행은 여전히 BLOCK."""
    if not human.is_human or human.level < Level.ADMIN_HUMAN_ONLY:
        record({"layer": "arm", "action": "arm", "strategy_id": strategy_id,
                "agent": human.name, "result": "denied", "reason": "not_human_admin"})
        raise PermissionDenied("arm은 사람 ADMIN만 가능")
    require(human, "approve_live_promotion", strategy_id)
    elig = check_micro_live_eligible(strategy_id, paper_months)
    if not elig["eligible"]:
        record({"layer": "arm", "action": "arm", "strategy_id": strategy_id,
                "result": "denied", "reason": elig["reasons"]})
        return {"strategy_id": strategy_id, "armed": False, "reasons": elig["reasons"]}
    row = {"strategy_id": strategy_id, "armed": True, "armed_by": human.name,
           "capital_limit": capital_limit, "max_order_qty": max_order_qty,
           "kill_switch": kill_switch, "paper_months": paper_months,
           "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    _append(row)
    record({"layer": "arm", "action": "arm", "strategy_id": strategy_id, "armed_by": human.name,
            "capital_limit": capital_limit, "result": "armed"})
    return {"strategy_id": strategy_id, "armed": True, "note": "무장됨. 단 autonomy<6이면 실행은 여전히 BLOCK."}


def disarm(strategy_id: str, human: Principal) -> dict:
    if not human.is_human:
        raise PermissionDenied("disarm은 사람만")
    row = {"strategy_id": strategy_id, "armed": False, "disarmed_by": human.name,
           "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    _append(row)
    record({"layer": "arm", "action": "disarm", "strategy_id": strategy_id, "result": "disarmed"})
    return {"strategy_id": strategy_id, "armed": False}
