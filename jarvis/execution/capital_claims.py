"""자본 청구 — 전략이 필요 자금을 청구, 엔벨로프 내면 AI 자율승인, 초과면 사람 대기열.

**배정 장부(bookkeeping)만.** 실제 브로커 자금이동/주문 집행 없음(`moves_real_capital=False`
불변). 실행은 여전히 기존 `arm.py` + `AUTONOMY_LEVEL` + `broker_bridge.py` 게이트가 유일한 문턱.

LIVE 자본 한도는 여기서 만들지 않는다 — `jarvis.execution.arm.arm()`의 `capital_limit`
재사용(이미 사람이 전략별로 설정하는 이중게이트). 여기는 그 한도 안에서 청구를 장부에
기록/판정할 뿐이다. PAPER 자본 한도 + 전체 풀 한도는 `capital_envelope.py`가 관리.

설계 근거: docs/superpowers/specs/2026-09-11-capital-claim-model-design.md
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

from jarvis.audit import record
from jarvis.config import state_path
from jarvis.execution.arm import arm_state, is_armed
from jarvis.execution.capital_envelope import get_envelope, paper_limit_for
from jarvis.permissions import Principal, require
from jarvis.registry import Status, StrategyRegistry

_CLAIMS = "capital_claims.jsonl"
_STALE_AFTER_DAYS = 14
_LIVE_STATUSES = {Status.LIVE_CANDIDATE.value, Status.MICRO_LIVE.value, Status.CONSTRAINED_LIVE.value}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _claims() -> list[dict]:
    p = state_path(_CLAIMS)
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def _append(row: dict) -> None:
    os.makedirs(os.path.dirname(state_path(_CLAIMS)), exist_ok=True)
    with open(state_path(_CLAIMS), "a") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _ceiling_ref(strategy_id: str) -> dict:
    from api_server.ai_portfolio import latest_recommendation
    rec = latest_recommendation()
    if not rec or strategy_id not in (rec.get("weights") or {}):
        return {"weight": None, "total_capital_basis": None, "capital_amount": None,
                "as_of": None, "stale": True}
    weight = rec["weights"][strategy_id]
    as_of = rec.get("timestamp")
    stale = True
    if as_of:
        try:
            ts = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
            stale = (datetime.now(timezone.utc) - ts) > timedelta(days=_STALE_AFTER_DAYS)
        except ValueError:
            stale = True
    return {"weight": weight, "total_capital_basis": None, "capital_amount": None,
            "as_of": as_of, "stale": stale}


def propose_claim(strategy_id: str, requested_amount: float | None = None,
                   total_capital_basis: float = 0.0) -> dict:
    """requested_amount 없으면 ceiling_ref(weight × total_capital_basis)로 제안."""
    ceiling = _ceiling_ref(strategy_id)
    if ceiling["weight"] is not None:
        ceiling["total_capital_basis"] = total_capital_basis
        ceiling["capital_amount"] = round(ceiling["weight"] * total_capital_basis, 2)
    proposed = requested_amount if requested_amount is not None else (ceiling["capital_amount"] or 0.0)
    return {"strategy_id": strategy_id, "requested_amount": requested_amount,
            "proposed_amount": proposed, "ceiling_ref": ceiling}


def _fulfillment_mode(strategy_id: str) -> tuple[str, float]:
    """(mode, hard_limit). live인데 arm 안 됐으면 paper로 강등."""
    st = StrategyRegistry().state(strategy_id)
    status = st["status"] if st else None
    if status in _LIVE_STATUSES and is_armed(strategy_id):
        return "live", float(arm_state(strategy_id)["capital_limit"])
    return "paper", paper_limit_for(strategy_id)


def strategy_capacity(strategy_id: str) -> dict:
    """전략별 남은 배정여력 — mode(paper/live)는 registry상태+arm여부로 자동판정."""
    mode, limit = _fulfillment_mode(strategy_id)
    used = _current_allocations().get(strategy_id, 0.0)
    return {"mode": mode, "limit": limit, "used": used, "remaining": max(limit - used, 0.0)}


def pool_capacity() -> dict:
    """전체 풀 남은 배정여력 — paper/live 구분 없이 capital_envelope.pool_limit 기준."""
    limit = get_envelope()["pool_limit"]
    used = sum(_current_allocations().values())
    return {"pool_limit": limit, "pool_used": used, "pool_remaining": max(limit - used, 0.0)}


def pool_capacity_by_mode() -> dict:
    """배정 가능 잔여 — LIVE/PAPER 분리. LIVE는 armed 전략들의 arm.py capital_limit 합,
    PAPER는 capital_envelope.pool_limit 기준(LIVE 배정은 이 풀을 안 씀)."""
    paper_pool_limit = get_envelope()["pool_limit"]
    paper_used = 0.0
    live_limit = 0.0
    live_used = 0.0
    for sid, amt in _current_allocations().items():
        mode, limit = _fulfillment_mode(sid)
        if mode == "live":
            live_limit += limit
            live_used += amt
        else:
            paper_used += amt
    return {
        "paper_limit": paper_pool_limit, "paper_used": paper_used,
        "paper_remaining": max(paper_pool_limit - paper_used, 0.0),
        "live_limit": live_limit, "live_used": live_used,
        "live_remaining": max(live_limit - live_used, 0.0),
    }


def _current_allocations() -> dict[str, float]:
    """strategy_id -> 최신 approved 청구의 allocated_capital.

    청구는 누적이 아니라 절대값(그 시점 전략이 원하는 총 배정액) — 새 approved 청구가
    이전 배정을 대체한다. 그래서 풀/전략 한도 검사도 '더하기'가 아니라 '교체' 기준이어야
    이중계산을 안 한다."""
    # _latest_by_claim_id().values()는 각 claim_id 최초 등장 순서 = 제출 시간순이라
    # 단순 순회 덮어쓰기만으로 전략별 최신 approved 배정액이 남는다(타임스탬프 비교 불필요 —
    # 초 단위 타임스탬프라 같은 초에 두 청구가 나면 문자열 비교로는 동률이 생김).
    by_strategy: dict[str, float] = {}
    for c in _latest_by_claim_id().values():
        if c["status"] == "approved":
            by_strategy[c["strategy_id"]] = c["allocated_capital"]
    return by_strategy


def _has_open_claim(strategy_id: str) -> bool:
    return any(c["strategy_id"] == strategy_id and c["status"] == "queued" for c in _claims())


def submit_claim(strategy_id: str, ai: Principal, requested_amount: float | None = None,
                  total_capital_basis: float = 0.0) -> dict:
    require(ai, "submit_capital_claim", strategy_id)

    st = StrategyRegistry().state(strategy_id)
    if st is None:
        row = _base_row(strategy_id, requested_amount, None, "paper", 0.0)
        row.update(status="rejected", allocated_capital=0.0, decided_by="AI",
                    decided_at=_now(), reason="not_registered")
        _append(row)
        record({"layer": "capital_claims", "action": "submit_claim", "strategy_id": strategy_id,
                "result": "rejected", "reason": "not_registered"})
        return row

    if _has_open_claim(strategy_id):
        row = _base_row(strategy_id, requested_amount, None, "paper", 0.0)
        row.update(status="rejected", allocated_capital=0.0, decided_by="AI",
                    decided_at=_now(), reason="duplicate_open_claim")
        _append(row)
        return row

    proposal = propose_claim(strategy_id, requested_amount, total_capital_basis)
    mode, hard_limit = _fulfillment_mode(strategy_id)

    current = _current_allocations()
    strategy_used = current.get(strategy_id, 0.0)  # 대체될 이전 배정(정보용)
    pool_used_excl = sum(v for sid, v in current.items() if sid != strategy_id)
    pool_limit = get_envelope()["pool_limit"]
    amount = proposal["proposed_amount"]
    within_strategy = amount <= hard_limit
    within_pool = (pool_used_excl + amount) <= pool_limit

    row = _base_row(strategy_id, requested_amount, proposal, mode, amount)
    row["envelope_check"] = {
        "strategy_limit": hard_limit, "pool_limit": pool_limit,
        "strategy_used_before": strategy_used, "pool_used_before": pool_used_excl + strategy_used,
        "within_strategy": within_strategy, "within_pool": within_pool,
    }

    if within_strategy and within_pool:
        row.update(status="approved", allocated_capital=amount, decided_by="AI",
                    decided_at=_now(), reason="within_envelope")
        record({"layer": "capital_claims", "action": "auto_fulfill", "strategy_id": strategy_id,
                "claim_id": row["claim_id"], "allocated_capital": amount, "fulfillment_mode": mode,
                "result": "approved"})
    else:
        row.update(status="queued", allocated_capital=0.0, decided_by=None, decided_at=None,
                    reason="envelope_exceeded")
        record({"layer": "capital_claims", "action": "submit_claim", "strategy_id": strategy_id,
                "claim_id": row["claim_id"], "result": "queued"})
    _append(row)
    return row


def _base_row(strategy_id: str, requested_amount: float | None, proposal: dict | None,
              mode: str, amount: float) -> dict:
    return {
        "claim_id": str(uuid.uuid4()), "strategy_id": strategy_id,
        "requested_amount": requested_amount,
        "proposed_amount": proposal["proposed_amount"] if proposal else None,
        "ceiling_ref": proposal["ceiling_ref"] if proposal else None,
        "fulfillment_mode": mode, "envelope_check": None,
        "status": "pending", "allocated_capital": 0.0, "decided_by": None,
        "created_at": _now(), "decided_at": None, "reason": "",
        "is_decision": True, "executes_broker_order": False, "moves_real_capital": False,
        "note": "Capital Claim — 배정 장부 기록만. 실제 브로커 자금이동/주문 아님.",
    }


def approve_queued(claim_id: str, human: Principal, approve: bool, note: str = "") -> dict:
    require(human, "approve_capital_claim", claim_id)
    rows = _claims()
    target = next((c for c in rows if c["claim_id"] == claim_id), None)
    if target is None:
        raise ValueError(f"claim not found: {claim_id}")
    if target["status"] != "queued":
        raise ValueError(f"claim not queued (status={target['status']}): {claim_id}")

    updated = dict(target)
    if approve:
        updated.update(status="approved", allocated_capital=updated["proposed_amount"],
                        decided_by=human.name, decided_at=_now(), reason=note or "human_approved")
    else:
        updated.update(status="rejected", allocated_capital=0.0,
                        decided_by=human.name, decided_at=_now(), reason=note or "human_rejected")
    _append(updated)  # append-only 장부 — 새 상태를 새 레코드로 기록(최신 = 마지막)
    record({"layer": "capital_claims", "action": "approve_queued", "claim_id": claim_id,
            "approved_by": human.name, "result": updated["status"]})
    return updated


def pending_queue() -> list[dict]:
    latest = _latest_by_claim_id()
    return [c for c in latest.values() if c["status"] == "queued"]


def claim_history(strategy_id: str | None = None, limit: int = 50) -> list[dict]:
    latest = list(_latest_by_claim_id().values())
    if strategy_id:
        latest = [c for c in latest if c["strategy_id"] == strategy_id]
    latest.sort(key=lambda c: c["created_at"])
    limit = max(1, limit)
    return latest[-limit:][::-1]


def _latest_by_claim_id() -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for c in _claims():
        latest[c["claim_id"]] = c
    return latest


def allocated_capital(strategy_id: str) -> float:
    return _current_allocations().get(strategy_id, 0.0)
