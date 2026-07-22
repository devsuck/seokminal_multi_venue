"""Execution Readiness Engine (P7.7) — 집행 전 최종 인증. **집행 아님.**

ExecutionIntent + 모든 통제 레이어 → ExecutionReadinessCertificate(READY/BLOCKED).
**이 인증서는 거래 허가가 아니다** — "시스템이 프리플라이트 검사를 통과했다"만 진술.

소유권 경계:
  Execution Control(P7.4)        "이 의도가 진행 가능한가?"
  Execution Simulation(P7.5)     "무슨 일이 일어날까?"
  Execution Reconciliation(P7.6) "가상 집행이 기대와 일치했는가?"
  Execution Readiness(P7.7)      "전체 시스템이 집행 인증되었는가?"  ← 본 레이어

8개 필수 검사(하나라도 FAIL → BLOCKED):
  approval · control · risk · arm · broker · market · simulation · reconciliation

각 검사는 주입 가능(테스트) — 미주입 시 하위 읽기전용 소스에서 산출.
**MUST NOT: 집행 게이트웨이 import·브로커 주문·게이트웨이 호출·포지션/리스크/레지스트리 변경.**
결정적·append-only·재현가능.
"""
from __future__ import annotations

from jarvis.execution_readiness import ledger
from jarvis.execution_readiness.models import (
    BLOCKED,
    ExecutionReadinessCertificate,
    FAIL,
    PASS,
    READY,
    ReadinessCheck,
    certificate_hash,
    certificate_id,
    input_hash,
    severity_for,
)

_ARM_LEDGER = "execution_control_arm.jsonl"

# 필수 검사 순서(결정적)
_MANDATORY = ["approval", "control", "risk", "arm", "broker", "market",
              "simulation", "reconciliation"]


class ExecutionReadinessEngine:
    """모든 통제 레이어 집계 → 인증서. 주문/집행/자본 이동 없음."""

    def certify(self, intent, now: str, *,
                approval: bool | None = None, control_ready: bool | None = None,
                risk_ok: bool | None = None, arm_present: bool | None = None,
                broker_ok: bool | None = None, market_ok: bool | None = None,
                simulation_pass: bool | None = None, reconciliation_ok: bool | None = None,
                broker_provider=None, live_provider=None,
                commit: bool = False) -> ExecutionReadinessCertificate:
        iid = getattr(intent, "intent_id", "")
        results = {
            "approval": approval if approval is not None else self._approval(intent, now),
            "control": control_ready if control_ready is not None else self._control(iid),
            "risk": risk_ok if risk_ok is not None else self._risk(intent),
            "arm": arm_present if arm_present is not None else self._arm(iid),
            "broker": broker_ok if broker_ok is not None else self._broker(broker_provider),
            "market": market_ok if market_ok is not None else self._market(live_provider),
            "simulation": simulation_pass if simulation_pass is not None else self._simulation(iid),
            "reconciliation": (reconciliation_ok if reconciliation_ok is not None
                               else self._reconciliation(iid)),
        }
        messages = {
            "approval": "ProductionProposal APPROVED",
            "control": "ExecutionDecision READY",
            "risk": "risk governor acceptable",
            "arm": "human ARM exists",
            "broker": "broker read-only health OK",
            "market": "live market data health OK",
            "simulation": "simulation validation PASS",
            "reconciliation": "no FAILED validation",
        }
        checks = []
        for name in _MANDATORY:
            ok = bool(results[name])
            status = PASS if ok else FAIL
            detail = messages[name] if ok else f"required: {messages[name]}"
            checks.append(ReadinessCheck(name=name, status=status,
                                         severity=severity_for(status), message=detail,
                                         timestamp=now).to_dict())

        blockers = [c["name"] for c in checks if c["status"] == FAIL]
        warnings = [c["name"] for c in checks if c["status"] == "WARN"]
        status = READY if not blockers else BLOCKED

        ih = input_hash(iid, checks)
        cid = certificate_id(iid, now)
        ch = certificate_hash(cid, status, checks, blockers, warnings, ih)
        cert = ExecutionReadinessCertificate(
            certificate_id=cid, status=status, checks=checks, blockers=blockers,
            warnings=warnings, intent_id=iid, created_at=now, input_hash=ih, hash=ch)
        if commit and not ledger.certificate_exists(cid):
            ledger.append_certificate(cert.to_dict())
            ledger.append_event({"event": "certificate_issued", "certificate_id": cid,
                                 "intent_id": iid, "status": status, "blockers": blockers,
                                 "timestamp": now})
        return cert

    # ── 실소스 헬퍼(모두 읽기전용) ────────────────────────────────
    def _approval(self, intent, now: str) -> bool:
        from jarvis.production.approval import proposal_status, read_approvals, read_proposals
        pid = getattr(intent, "source_proposal_id", "")
        prop = next((p for p in read_proposals() if p["proposal_id"] == pid), None)
        if prop is None:
            return False
        return proposal_status(prop, read_approvals(), now) == "APPROVED"

    def _control(self, intent_id: str) -> bool:
        from jarvis.execution_control.ledger import read_decisions
        decs = [d for d in read_decisions() if d.get("intent_id") == intent_id]
        return bool(decs) and decs[-1].get("status") == "READY"

    def _risk(self, intent) -> bool:
        from jarvis.risk.governor import RiskGovernor, RiskLimits
        rr = RiskGovernor(dry_run=True).check(
            {"strategy_id": getattr(intent, "strategy", ""),
             "proposal_id": getattr(intent, "source_proposal_id", ""), "orders": []},
            RiskLimits())
        return rr["risk_status"] == "APPROVED"

    def _arm(self, intent_id: str) -> bool:
        from jarvis.config import state_path
        import json
        import os
        p = state_path(_ARM_LEDGER)
        if not os.path.exists(p):
            return False
        with open(p) as f:
            rows = [json.loads(ln) for ln in f if ln.strip()]
        return any(r.get("intent_id") == intent_id and r.get("armed") is True for r in rows)

    def _broker(self, broker_provider) -> bool:
        if broker_provider is None:
            return False
        h = broker_provider.health_check()
        d = h.to_dict() if hasattr(h, "to_dict") else h
        return bool(d.get("connected")) and not d.get("stale", True)

    def _market(self, live_provider) -> bool:
        if live_provider is None:
            return False
        h = live_provider.health_check() if hasattr(live_provider, "health_check") else {}
        d = h.to_dict() if hasattr(h, "to_dict") else h
        return bool(d.get("connected")) and not d.get("stale", False)

    def _simulation(self, intent_id: str) -> bool:
        """해당 의도의 시뮬 검증(P7.6)이 PASS인지. PASS 리포트가 하나라도 있어야 함."""
        from jarvis.execution_reconciliation.ledger import read_reports
        reps = [r for r in read_reports() if r.get("intent_id") == intent_id]
        return bool(reps) and any(r.get("status") == "PASS" for r in reps)

    def _reconciliation(self, intent_id: str) -> bool:
        """해당 의도의 검증 리포트 중 FAILED가 없어야 함."""
        from jarvis.execution_reconciliation.ledger import read_reports
        reps = [r for r in read_reports() if r.get("intent_id") == intent_id]
        return bool(reps) and not any(r.get("status") == "FAILED" for r in reps)
