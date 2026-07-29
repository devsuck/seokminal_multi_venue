"""Emergency Engine (P9.3) — 관측 입력 → EmergencyDecision. **킬스위치 결정만, 작동 아님.**

입력(모두 데이터 파일로만 관측): P9.1 SystemHealthReport · P8.5 ExecutionRiskReport ·
P9.2 Incident/Escalation. 출력: EmergencyDecision(비상 상태). Recovery 는 자동 금지 —
Operator 승인 흐름(request→approve/reject)만. **Gateway/Broker/Order Cancel/ARM/실제 Kill
Switch 호출 없음.** 결정적·append-only·해시체인. injectable 입력으로 테스트 결정성 확보.
"""
from __future__ import annotations

from jarvis.emergency import ledger
from jarvis.emergency.models import (
    GENESIS,
    KILL_ACTIVE,
    NORMAL,
    RECOVERED,
    RECOVERY_PENDING,
    EmergencyDecision,
    RecoveryApproval,
    RecoveryEvent,
    RecoveryNotPermitted,
    RecoveryRequest,
    content_hash,
    decision_id,
    fold_active_incidents,
    grade,
    input_digest,
    reconcile,
    recovery_approval_id,
    recovery_event_id,
    recovery_request_id,
)


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class EmergencyEngine:
    """비상 대응 엔진. 관측 대상은 읽기전용·비상 원장은 append-only·결정적."""

    # ── 현재 비상 상태(결정 체인의 마지막) ──
    @staticmethod
    def current_state() -> str:
        head = ledger.decisions_head()
        return head["emergency_state"] if head else NORMAL

    # ── 관측 입력 수집(데이터 파일로만) ──
    def _gather(self, health, risk, incidents, escalations) -> dict:
        health = health if health is not None else ledger.latest_health()
        risk = risk if risk is not None else ledger.latest_risk()
        incidents = incidents if incidents is not None else ledger.read_incident_rows()
        escalations = escalations if escalations is not None else ledger.read_escalation_rows()

        health_status = (health or {}).get("overall_status", "")
        risk_status = (risk or {}).get("overall_status", "")
        risk_warn_count = len((risk or {}).get("warnings", []) or [])

        critical_inc, warning_inc, active_ids = fold_active_incidents(incidents)
        escalation_active = any(e.get("incident_id") in active_ids for e in (escalations or []))

        return {"health_status": health_status, "risk_status": risk_status,
                "risk_warn_count": risk_warn_count, "critical_incident": critical_inc,
                "warning_incident": warning_inc, "escalation_active": escalation_active}

    # ── 비상 판정 ──
    def assess(self, *, health=None, risk=None, incidents=None, escalations=None,
               now: str = "", commit: bool = False) -> EmergencyDecision:
        sig = self._gather(health, risk, incidents, escalations)
        graded, reasons = grade(sig["health_status"], sig["risk_status"],
                                sig["risk_warn_count"], sig["critical_incident"],
                                sig["warning_incident"], sig["escalation_active"])
        cur = self.current_state()
        new_state = reconcile(cur, graded)
        if new_state != graded:
            reasons = reasons + [f"reconciled_from_graded:{graded}"]

        ih = input_digest(sig["health_status"], sig["risk_status"], sig["risk_warn_count"],
                          sig["critical_incident"], sig["warning_incident"],
                          sig["escalation_active"], cur)
        did = decision_id(ih, now, "assess")
        rec = EmergencyDecision(
            decision_id=did, timestamp=now, emergency_state=new_state, previous_state=cur,
            source="assess", health_status=sig["health_status"], risk_status=sig["risk_status"],
            critical_incident=sig["critical_incident"], escalation_active=sig["escalation_active"],
            reasons=reasons, input_hash=ih, previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.decision_exists(did):
            head = ledger.decisions_head()
            rec = _seal(rec, head["record_hash"] if head else GENESIS)
            ledger.append_decision(rec)
        return EmergencyDecision(**rec)

    def _append_decision(self, state: str, previous: str, source: str, now: str,
                         *, reasons: list, commit: bool) -> dict:
        ih = input_digest(state, previous, source, now)
        did = decision_id(ih, now, source)
        rec = EmergencyDecision(decision_id=did, timestamp=now, emergency_state=state,
                                previous_state=previous, source=source, reasons=reasons,
                                input_hash=ih, previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.decision_exists(did):
            head = ledger.decisions_head()
            rec = _seal(rec, head["record_hash"] if head else GENESIS)
            ledger.append_decision(rec)
        return rec

    # ── Recovery(자동 금지 — Operator 전용) ──
    def request_recovery(self, requested_by: str, now: str, *, reason: str = "",
                         commit: bool = False) -> dict:
        """KILL_ACTIVE 에서만 복구 요청 가능 → RECOVERY_PENDING. 그 외 상태면 차단."""
        cur = self.current_state()
        if cur != KILL_ACTIVE:
            raise RecoveryNotPermitted(f"복구 요청은 KILL_ACTIVE 에서만 가능(현재 {cur})")
        rid = recovery_request_id(requested_by, now)
        ih = input_digest(requested_by, cur, reason)
        req = RecoveryRequest(request_id=rid, timestamp=now, requested_by=requested_by,
                              from_state=cur, reason=reason, input_hash=ih,
                              previous_hash=GENESIS).to_dict()
        req["record_hash"] = content_hash(req)
        if commit and not ledger.recovery_request_exists(rid):
            head = ledger.recovery_requests_head()
            req = _seal(req, head["record_hash"] if head else GENESIS)
            ledger.append_recovery_request(req)
        # 상태 전이 KILL_ACTIVE → RECOVERY_PENDING(결정 체인 기록)
        self._append_decision(RECOVERY_PENDING, cur, "recovery_request", now,
                              reasons=[f"recovery_requested_by:{requested_by}"], commit=commit)
        return req

    def approve_recovery(self, request_id: str, approver: str, now: str, *,
                         approved: bool, note: str = "", commit: bool = False) -> dict:
        """RECOVERY_PENDING 에서만 승인/반려 가능. 승인→RECOVERED, 반려→KILL_ACTIVE(재래치)."""
        cur = self.current_state()
        if cur != RECOVERY_PENDING:
            raise RecoveryNotPermitted(f"복구 승인은 RECOVERY_PENDING 에서만 가능(현재 {cur})")
        aid = recovery_approval_id(request_id, approver, now)
        ih = input_digest(request_id, approver, approved, note)
        appr = RecoveryApproval(approval_id=aid, timestamp=now, request_id=request_id,
                                approver=approver, approved=bool(approved), note=note,
                                input_hash=ih, previous_hash=GENESIS).to_dict()
        appr["record_hash"] = content_hash(appr)
        if commit and not ledger.recovery_approval_exists(aid):
            head = ledger.recovery_approvals_head()
            appr = _seal(appr, head["record_hash"] if head else GENESIS)
            ledger.append_recovery_approval(appr)

        to_state = RECOVERED if approved else KILL_ACTIVE
        outcome = "approved" if approved else "rejected"
        eid = recovery_event_id(request_id, cur, to_state, now)
        eih = input_digest(request_id, cur, to_state, outcome)
        ev = RecoveryEvent(event_id=eid, timestamp=now, request_id=request_id,
                           from_state=cur, to_state=to_state, outcome=outcome,
                           input_hash=eih, previous_hash=GENESIS).to_dict()
        ev["record_hash"] = content_hash(ev)
        if commit and not ledger.recovery_event_exists(eid):
            head = ledger.recovery_events_head()
            ev = _seal(ev, head["record_hash"] if head else GENESIS)
            ledger.append_recovery_event(ev)
        # 상태 전이 기록(결정 체인)
        self._append_decision(to_state, cur, "recovery_approval", now,
                              reasons=[f"recovery_{outcome}_by:{approver}"], commit=commit)
        return appr

    # ── 편의: 관측 → 판정 한 사이클 ──
    def check(self, *, health=None, risk=None, incidents=None, escalations=None,
              now: str = "", commit: bool = False) -> dict:
        d = self.assess(health=health, risk=risk, incidents=incidents,
                        escalations=escalations, now=now, commit=commit)
        return {"emergency_state": d.emergency_state, "previous_state": d.previous_state,
                "reasons": d.reasons, "decision": d.to_dict()}
