"""Execution Control Plane (P7.4) — 통제된 '의도' 계층. 집행 아님.

ProductionProposal → ExecutionIntent → [6 checks] → ExecutionDecision(BLOCKED/READY).
**ExecutionDecision은 주문이 아니다 — 감사가능한 지시 후보일 뿐.** 결정적·읽기전용.

6개 필수 검사(모두 통과해야 READY):
  1) approval        제안이 사람 승인(APPROVED)이어야 함
  2) production_gate  프로덕션 게이트가 ALLOW여야 함
  3) risk            리스크 거버너(읽기전용)가 허용해야 함
  4) reconciliation  P7.3 대조 심각도가 CRITICAL이면 안 됨
  5) data_freshness  시장데이터 신선도 충족
  6) arm             사람 ARM(수동 무장) 존재
추가) not_expired    의도 만료 전

**MUST NOT: 집행 게이트웨이 import·브로커 호출·주문 생성·포지션/리스크/레지스트리 변경.**
각 검사 플래그는 주입 가능(테스트) — 미주입 시 하위 읽기전용 소스에서 산출.
"""
from __future__ import annotations

from jarvis.execution_control import ledger
from jarvis.execution_control.models import (
    BLOCKED,
    ControlCheck,
    DEFAULT_EXPIRY_HOURS,
    ExecutionDecision,
    ExecutionIntent,
    READY,
    add_hours,
    decision_hash,
    intent_id,
    is_expired,
)

_ARM_LEDGER = "execution_control_arm.jsonl"


def _primary(allocation: dict, strategy: str) -> tuple[str, float]:
    """할당에서 대표 심볼/목표비중(절대값 최대). 없으면 (strategy, 0.0)."""
    if not allocation:
        return strategy, 0.0
    sym = max(sorted(allocation), key=lambda k: abs(float(allocation[k])))
    return sym, float(allocation[sym])


def _side(weight: float) -> str:
    if weight > 1e-9:
        return "BUY"
    if weight < -1e-9:
        return "SELL"
    return "HOLD"


class ExecutionControlPlane:
    """제안 → 통제된 의도 → 감사가능 결정. 주문/집행 없음."""

    # ── 의도 생성 ────────────────────────────────────────────────
    def build_intent(self, proposal: dict, now: str, *,
                     expiry_hours: float = DEFAULT_EXPIRY_HOURS,
                     commit: bool = False) -> ExecutionIntent | None:
        """제안에서 ExecutionIntent 생성. 중복(동일 source_proposal_id) 방지.

        **주문 사이징 없음(no capital deployment)** — quantity=0.0, 목표비중만 전달.
        """
        pid = proposal["proposal_id"]
        if commit and ledger.intent_exists(pid):
            return None
        sym, weight = _primary(proposal.get("allocation", {}), proposal["strategy"])
        eid = intent_id(pid, proposal["strategy"], sym, _side(weight))
        intent = ExecutionIntent(
            intent_id=eid, strategy=proposal["strategy"], symbol=sym,
            side=_side(weight), quantity=0.0, target_weight=weight,
            source_proposal_id=pid, created_at=now,
            expiry=add_hours(now, expiry_hours))
        if commit:
            if ledger.intent_exists(pid):
                return None
            ledger.append_intent(intent.to_dict())
            ledger.append_event({"event": "intent_created", "intent_id": eid,
                                 "source_proposal_id": pid, "timestamp": now})
        return intent

    # ── 결정 평가(6 checks + expiry) ─────────────────────────────
    def evaluate(self, intent: ExecutionIntent, now: str, *,
                 approved: bool | None = None, gate_allow: bool | None = None,
                 risk_ok: bool | None = None, reconciliation_severity: str | None = None,
                 data_fresh: bool | None = None, arm_present: bool | None = None,
                 broker_provider=None, live_provider=None,
                 commit: bool = False) -> ExecutionDecision:
        checks: list[ControlCheck] = []

        # 1) approval
        ap = approved if approved is not None else self._approved(intent, now)
        checks.append(ControlCheck("approval", ap,
                                   "proposal APPROVED" if ap else "not human-approved"))
        # 2) production_gate
        ga = gate_allow if gate_allow is not None else self._gate_allow(intent, now)
        checks.append(ControlCheck("production_gate", ga,
                                   "ALLOW" if ga else "BLOCK"))
        # 3) risk (read-only)
        rk = risk_ok if risk_ok is not None else self._risk_ok(intent)
        checks.append(ControlCheck("risk", rk,
                                   "risk permits" if rk else "risk rejects"))
        # 4) reconciliation (P7.3 severity != CRITICAL)
        sev = (reconciliation_severity if reconciliation_severity is not None
               else self._reconciliation_severity(broker_provider, live_provider, now))
        rc = sev != "CRITICAL"
        checks.append(ControlCheck("reconciliation", rc, f"severity={sev}"))
        # 5) data_freshness
        df = data_fresh if data_fresh is not None else self._data_fresh(intent, now, live_provider)
        checks.append(ControlCheck("data_freshness", df,
                                   "fresh" if df else "stale/unavailable"))
        # 6) arm (human manual arming)
        am = arm_present if arm_present is not None else self._arm_present(intent)
        checks.append(ControlCheck("arm", am,
                                   "human ARM present" if am else "no human ARM"))
        # +) not_expired
        expired = is_expired(intent.expiry, now)
        checks.append(ControlCheck("not_expired", not expired,
                                   "expired" if expired else "valid"))

        blockers = [c.name for c in checks if not c.passed]
        status = READY if not blockers else BLOCKED
        chk_dicts = [c.to_dict() for c in checks]
        h = decision_hash(intent.intent_id, status, chk_dicts, now)
        decision = ExecutionDecision(intent_id=intent.intent_id, status=status,
                                     checks=chk_dicts, blockers=blockers,
                                     timestamp=now, hash=h)
        if commit:
            ledger.append_decision(decision.to_dict())
            ledger.append_event({"event": "decision_evaluated", "intent_id": intent.intent_id,
                                 "status": status, "blockers": blockers, "timestamp": now})
        return decision

    # ── 실소스 헬퍼(모두 읽기전용) ────────────────────────────────
    def _approved(self, intent: ExecutionIntent, now: str) -> bool:
        from jarvis.production.approval import proposal_status, read_approvals, read_proposals
        prop = next((p for p in read_proposals()
                     if p["proposal_id"] == intent.source_proposal_id), None)
        if prop is None:
            return False
        return proposal_status(prop, read_approvals(), now) == "APPROVED"

    def _gate_allow(self, intent: ExecutionIntent, now: str) -> bool:
        from jarvis.production.approval import read_proposals
        from jarvis.production.gate import ProductionGate
        from jarvis.production.models import ProductionProposal
        prop = next((p for p in read_proposals()
                     if p["proposal_id"] == intent.source_proposal_id), None)
        if prop is None:
            return False
        pp = ProductionProposal(
            proposal_id=prop["proposal_id"], source=prop.get("source", ""),
            strategy=prop["strategy"], allocation=prop.get("allocation", {}),
            risk_state=prop.get("risk_state", {}), rationale=prop.get("rationale", []),
            created_at=prop.get("created_at", ""))
        return ProductionGate().check(pp, now).decision == "ALLOW"

    def _risk_ok(self, intent: ExecutionIntent) -> bool:
        from jarvis.risk.governor import RiskGovernor, RiskLimits
        rr = RiskGovernor(dry_run=True).check(
            {"strategy_id": intent.strategy, "proposal_id": intent.source_proposal_id,
             "orders": []}, RiskLimits())
        return rr["risk_status"] == "APPROVED"

    def _reconciliation_severity(self, broker_provider, live_provider, now: str) -> str:
        if broker_provider is None:
            return "UNKNOWN"   # 대조 불가 → CRITICAL 아님이지만 data/arm 등에서 차단
        from jarvis.reconciliation.engine import reconcile_runtime
        return reconcile_runtime(broker_provider, live_provider, now, commit=False).severity

    def _data_fresh(self, intent: ExecutionIntent, now: str, live_provider) -> bool:
        if live_provider is None:
            return False   # 라이브 데이터 미구성 → 정직한 CLOSED
        h = live_provider.health_check() if hasattr(live_provider, "health_check") else {}
        if not h.get("connected", False) or h.get("stale", True):
            return False
        tick = live_provider.latest(intent.symbol) if hasattr(live_provider, "latest") else None
        return tick is not None

    def _arm_present(self, intent: ExecutionIntent) -> bool:
        """사람 ARM 원장 조회. 이 엔진은 ARM을 기록하지 않음(사람 전용) — 기본 부재."""
        from jarvis.config import state_path
        import json
        import os
        p = state_path(_ARM_LEDGER)
        if not os.path.exists(p):
            return False
        with open(p) as f:
            rows = [json.loads(ln) for ln in f if ln.strip()]
        return any(r.get("intent_id") == intent.intent_id and r.get("armed") is True
                   for r in rows)
