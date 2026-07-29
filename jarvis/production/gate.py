"""Production Safety Gate (P6.1) — 프로덕션-레디 검사. ALLOW / BLOCK.

검사: risk governor 상태 · 포트폴리오 품질 · 데이터 신선도 · 전략 상태 · 권한(autonomy).
**risk governor가 최종 권위** — 그 REJECT는 곧 BLOCK. 집행 게이트웨이 호출 안 함.
현주소: autonomy<MIN_LIVE + 전략 live 승인 전 → 무조건 BLOCK(정직한 경계).
"""
from __future__ import annotations

import json
import os

from jarvis.config import AUTONOMY_LEVEL, MIN_LIVE_LEVEL, live_execution_enabled, state_path
from jarvis.production.audit import record_production
from jarvis.production.models import (
    FRESHNESS_HOURS,
    PRODUCTION_READY_STATUSES,
    GateDecision,
    ProductionProposal,
    hours_between,
)

_GATE_LEDGER = "production_gate_decisions.jsonl"


class ProductionGate:
    def check(self, proposal: ProductionProposal, now: str, ts: str = "") -> GateDecision:
        failed: list[str] = []
        checks: dict = {}

        # 1) risk governor (최종 권위, read-only)
        from jarvis.risk.governor import RiskGovernor, RiskLimits
        rr = RiskGovernor(dry_run=True).check(
            {"strategy_id": proposal.strategy, "proposal_id": proposal.proposal_id, "orders": []},
            RiskLimits())
        checks["risk_governor"] = rr["risk_status"]
        if rr["risk_status"] != "APPROVED":
            failed.append(f"risk_governor:{rr['reason']}")

        # 2) 포트폴리오 품질
        qmode = (proposal.risk_state or {}).get("quality_mode")
        checks["portfolio_quality"] = qmode or "unknown"
        if qmode == "exclude":
            failed.append("portfolio_quality:exclude")

        # 3) 데이터 신선도
        age = hours_between(proposal.created_at, now)
        checks["data_age_hours"] = round(age, 2) if age is not None else None
        if age is None:
            failed.append("data_freshness:unknown_timestamp")
        elif age > FRESHNESS_HOURS:
            failed.append(f"data_stale({round(age, 1)}h>{FRESHNESS_HOURS}h)")

        # 4) 전략 상태 (registry, read-only)
        from jarvis.registry import StrategyRegistry
        st = StrategyRegistry().state(proposal.strategy)
        status = st["status"] if st else None
        checks["strategy_status"] = status
        if status not in PRODUCTION_READY_STATUSES:
            failed.append(f"strategy_status:{status}(not production-ready)")

        # 5) 권한/autonomy
        checks["autonomy_level"] = AUTONOMY_LEVEL
        checks["live_enabled"] = live_execution_enabled()
        if not live_execution_enabled():
            failed.append(f"permission_level:autonomy({AUTONOMY_LEVEL}<{MIN_LIVE_LEVEL})")

        decision = "ALLOW" if not failed else "BLOCK"
        reason = "all_checks_passed" if not failed else "; ".join(failed)
        return GateDecision(decision=decision, reason=reason, failed_checks=failed,
                            timestamp=ts, checks=checks)

    def persist(self, proposal: ProductionProposal, decision: GateDecision) -> dict:
        """게이트 결정 append + audit(선택; check --commit)."""
        p = state_path(_GATE_LEDGER)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        row = {"proposal_id": proposal.proposal_id, "strategy": proposal.strategy,
               **decision.to_dict()}
        with open(p, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        record_production({"action": "production_gate_check", "proposal_id": proposal.proposal_id,
                           "decision": decision.decision, "failed_checks": decision.failed_checks,
                           "result": "recorded"})
        return {"persisted": True, "decision": decision.decision}


def read_gate_decisions() -> list[dict]:
    p = state_path(_GATE_LEDGER)
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [json.loads(ln) for ln in f if ln.strip()]
