"""Recovery Control Engine (P9.4) — 증거수집·준비도평가·체크리스트·증언. **자동 복구 아님.**

관측 입력(P9.1/P9.2/P9.3/집행경계)을 *데이터로만* 읽어 결정적 체크 수행 → RecoveryReadinessReport
(READY/WARNING/FAILED). Operator 증언(APPROVE_RESTART_REVIEW/REJECT)은 기록만 — **서비스 재시작·
킬스위치 해제·거래 재개·브로커/집행/리스크/권한/레지스트리/포트폴리오/페이퍼 변경 없음.** 권한상승 아님.
injectable 입력으로 테스트 결정성 확보.
"""
from __future__ import annotations

from jarvis.recovery_control import ledger
from jarvis.recovery_control.models import (
    APPROVE_RESTART_REVIEW,
    E_KILL_ACTIVE,
    E_KILL_PENDING,
    E_SAFE_MODE,
    FAILED,
    GENESIS,
    H_CRITICAL,
    H_OFFLINE,
    H_WARNING,
    PASS,
    READY,
    WARNING,
    RecoveryAttestation,
    RecoveryAttestationError,
    RecoveryCheck,
    RecoveryChecklist,
    RecoveryEvidence,
    RecoveryReadinessReport,
    attestation_id,
    checklist_hash,
    checklist_id,
    content_hash,
    evidence_hash,
    evidence_id,
    fold_active_incidents,
    input_digest,
    is_valid_decision,
    overall_readiness,
    readiness_id,
)

_SOURCE_LEDGERS = ["system_health_reports.jsonl", "incidents.jsonl", "escalations.jsonl",
                   "emergency_decisions.jsonl", "recovery_requests.jsonl",
                   "recovery_events.jsonl", "live_execution_responses.jsonl"]


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


def _c(name, category, status, mandatory, detail=""):
    return RecoveryCheck(name=name, category=category, status=status,
                         mandatory=mandatory, detail=detail).to_dict()


class RecoveryControlEngine:
    """복구 관제 엔진. 관측 대상은 읽기전용·관제 원장은 append-only·결정적."""

    # ── 관측 입력 수집(데이터 파일로만) ──
    def _gather(self, health, incidents, escalations, emergency_decisions,
                recovery_requests, recovery_events, live_enabled, live_rows) -> dict:
        health = health if health is not None else ledger.latest_health()
        incidents = incidents if incidents is not None else ledger.read_incident_rows()
        escalations = escalations if escalations is not None else ledger.read_escalation_rows()
        emergency_decisions = (emergency_decisions if emergency_decisions is not None
                               else ledger.read_emergency_decisions())
        recovery_requests = (recovery_requests if recovery_requests is not None
                             else ledger.read_recovery_requests())
        recovery_events = (recovery_events if recovery_events is not None
                           else ledger.read_recovery_events())
        live_rows = live_rows if live_rows is not None else ledger.read_live_execution_rows()
        if live_enabled is None:
            import jarvis.config as _cfg   # 별칭 import — 집행경계 게이트 읽기전용 조회
            live_enabled = _cfg.live_execution_enabled()

        h_overall = (health or {}).get("overall_status", "")
        subs = (health or {}).get("subsystems", []) or []
        sub_statuses = {str(s.get("status", "")) for s in subs}
        crit_inc, any_inc, active_ids = fold_active_incidents(incidents)
        esc_active = any(e.get("incident_id") in active_ids for e in (escalations or []))
        emergency_state = (emergency_decisions[-1].get("emergency_state", "")
                           if emergency_decisions else "")

        return {
            "health_overall": h_overall,
            "health_has_critical": h_overall == H_CRITICAL or H_CRITICAL in sub_statuses,
            "health_has_offline": h_overall == H_OFFLINE or H_OFFLINE in sub_statuses,
            "health_has_warning": h_overall == H_WARNING or H_WARNING in sub_statuses,
            "incident_critical_active": crit_inc,
            "incident_any_active": any_inc,
            "escalation_active": esc_active,
            "emergency_state": emergency_state,
            "kill_latch": emergency_state == E_KILL_ACTIVE,
            "emergency_decision_exists": bool(emergency_decisions),
            "recovery_permission_posture": emergency_state,
            "previous_recovery_attempts": len(recovery_requests) + len(recovery_events),
            "live_enabled": bool(live_enabled),
            "live_records": len(live_rows or []),
        }

    # ── 체크리스트(결정적) ──
    @staticmethod
    def _build_checks(sig: dict) -> list:
        checks = []
        # Health (필수)
        checks.append(_c("HEALTH_NO_CRITICAL", "Health",
                         FAILED if sig["health_has_critical"] else PASS, True,
                         "CRITICAL 서브시스템 없음" if not sig["health_has_critical"]
                         else "CRITICAL 헬스 존재"))
        checks.append(_c("HEALTH_NO_OFFLINE", "Health",
                         FAILED if sig["health_has_offline"] else PASS, True,
                         "OFFLINE 없음" if not sig["health_has_offline"] else "OFFLINE 헬스 존재"))
        checks.append(_c("HEALTH_NO_WARNING", "Health",
                         WARNING if sig["health_has_warning"] else PASS, False,
                         "WARNING 헬스" if sig["health_has_warning"] else "경고 없음"))
        # Incident
        checks.append(_c("INCIDENT_NO_ACTIVE_CRITICAL", "Incident",
                         FAILED if sig["incident_critical_active"] else PASS, True,
                         "활성 CRITICAL 인시던트" if sig["incident_critical_active"]
                         else "활성 CRITICAL 인시던트 없음"))
        checks.append(_c("INCIDENT_RESOLVED", "Incident",
                         WARNING if sig["incident_any_active"] else PASS, False,
                         "미해결 인시던트 존재" if sig["incident_any_active"] else "인시던트 해결됨"))
        checks.append(_c("ESCALATION_CLEAR", "Incident",
                         WARNING if sig["escalation_active"] else PASS, False,
                         "활성 에스컬레이션" if sig["escalation_active"] else "에스컬레이션 없음"))
        # Emergency
        checks.append(_c("EMERGENCY_NOT_KILL_ACTIVE", "Emergency",
                         FAILED if sig["kill_latch"] else PASS, True,
                         "KILL_ACTIVE 래치 — 준비도 차단" if sig["kill_latch"]
                         else f"비상상태 {sig['emergency_state'] or 'NORMAL'}"))
        checks.append(_c("EMERGENCY_STABLE", "Emergency",
                         WARNING if sig["emergency_state"] in (E_KILL_PENDING, E_SAFE_MODE)
                         else PASS, False, f"비상상태 {sig['emergency_state'] or 'NORMAL'}"))
        checks.append(_c("RECOVERY_PERMISSION", "Emergency", PASS, False,
                         f"복구 권한 포스처: {sig['recovery_permission_posture'] or 'NORMAL'}"))
        # Execution boundary (필수)
        checks.append(_c("LIVE_EXECUTION_DISABLED", "ExecutionBoundary",
                         FAILED if sig["live_enabled"] else PASS, True,
                         "라이브 집행 인가 존재 — 경계 위반" if sig["live_enabled"]
                         else "라이브 집행 폐쇄(autonomy<MIN_LIVE)"))
        checks.append(_c("NO_LIVE_EXECUTION_RECORDS", "ExecutionBoundary",
                         WARNING if sig["live_records"] > 0 else PASS, False,
                         f"라이브 집행 응답 {sig['live_records']}건" if sig["live_records"]
                         else "라이브 집행 응답 없음"))
        # Audit
        checks.append(_c("EMERGENCY_DECISION_EXISTS", "Audit",
                         PASS if sig["emergency_decision_exists"] else WARNING, False,
                         "비상 결정 기록 존재" if sig["emergency_decision_exists"]
                         else "비상 결정 기록 없음"))
        checks.append(_c("PREVIOUS_RECOVERY_RECORDED", "Audit", PASS, False,
                         f"이전 복구 시도 {sig['previous_recovery_attempts']}건"))
        return checks

    # ── 준비도 평가(증거+체크리스트+리포트) ──
    def assess(self, now: str = "", *, health=None, incidents=None, escalations=None,
               emergency_decisions=None, recovery_requests=None, recovery_events=None,
               live_enabled=None, live_rows=None, commit: bool = False) -> RecoveryReadinessReport:
        sig = self._gather(health, incidents, escalations, emergency_decisions,
                           recovery_requests, recovery_events, live_enabled, live_rows)
        checks = self._build_checks(sig)
        overall, mand_fail, warns = overall_readiness(checks)

        eh = evidence_hash(sig)
        ch = checklist_hash(checks)

        # Evidence 레코드
        ev_id = evidence_id(eh)
        ev = RecoveryEvidence(evidence_id=ev_id, timestamp=now, observed=sig,
                              sources=list(_SOURCE_LEDGERS), evidence_hash=eh,
                              input_hash=eh, previous_hash=GENESIS).to_dict()
        ev["record_hash"] = content_hash(ev)

        # Checklist 레코드
        cl_id = checklist_id(ch)
        cl = RecoveryChecklist(checklist_id=cl_id, timestamp=now, checks=checks,
                               checklist_hash=ch, input_hash=ch, previous_hash=GENESIS).to_dict()
        cl["record_hash"] = content_hash(cl)

        # Readiness 리포트 (report_hash == record_hash, content_hash 에서 제외되어 순환 없음)
        rid = readiness_id(eh, ch)
        ih = input_digest(eh, ch)
        rep = RecoveryReadinessReport(
            report_id=rid, timestamp=now, overall_status=overall, checks=checks,
            checklist_hash=ch, evidence_hash=eh, mandatory_failures=mand_fail, warnings=warns,
            emergency_state=sig["emergency_state"], input_hash=ih, previous_hash=GENESIS).to_dict()
        rh = content_hash(rep)
        rep["report_hash"] = rh

        if commit:
            if not ledger.evidence_exists(ev_id):
                head = ledger.evidence_head()
                ledger.append_evidence(_seal(ev, head["record_hash"] if head else GENESIS))
            if not ledger.checklist_exists(cl_id):
                head = ledger.checklists_head()
                ledger.append_checklist(_seal(cl, head["record_hash"] if head else GENESIS))
            if not ledger.readiness_exists(rid):
                head = ledger.readiness_head()
                sealed = _seal(rep, head["record_hash"] if head else GENESIS)
                sealed["report_hash"] = sealed["record_hash"]
                ledger.append_readiness(sealed)
        return RecoveryReadinessReport(**rep)

    # ── Operator 증언(기록만 — 권한상승 아님) ──
    def attest(self, operator_id: str, incident_id: str, decision: str, now: str = "", *,
               reason: str = "", report=None, commit: bool = False) -> RecoveryAttestation:
        if not is_valid_decision(decision):
            raise RecoveryAttestationError(f"허용되지 않은 결정: {decision}")
        rep = report.to_dict() if hasattr(report, "to_dict") else report
        if rep is None:
            rep = ledger.readiness_head()
        if not rep or not rep.get("checklist_hash"):
            raise RecoveryAttestationError("증언에는 준비도 체크리스트가 필요(선행 assess 없음)")
        if decision == APPROVE_RESTART_REVIEW and rep.get("overall_status") == FAILED:
            raise RecoveryAttestationError("FAILED 준비도에서는 재시작 검토 승인 불가")

        ch = rep.get("checklist_hash", "")
        eh = rep.get("evidence_hash", "")
        em_state = rep.get("emergency_state", "")
        aid = attestation_id(operator_id, incident_id, decision, ch)
        ih = input_digest(operator_id, incident_id, decision, ch, eh)
        att = RecoveryAttestation(
            attestation_id=aid, timestamp=now, operator_id=operator_id, incident_id=incident_id,
            emergency_state=em_state, checklist_hash=ch, evidence_hash=eh, decision=decision,
            readiness_status=rep.get("overall_status", ""), reason=reason, input_hash=ih,
            previous_hash=GENESIS).to_dict()
        att["record_hash"] = content_hash(att)
        if commit and not ledger.attestation_exists(aid):
            head = ledger.attestations_head()
            ledger.append_attestation(_seal(att, head["record_hash"] if head else GENESIS))
        return RecoveryAttestation(**att)

    # ── 편의 ──
    def check(self, now: str = "", *, commit: bool = False, **kw) -> dict:
        rep = self.assess(now, commit=commit, **kw)
        return {"overall_status": rep.overall_status, "emergency_state": rep.emergency_state,
                "mandatory_failures": rep.mandatory_failures, "warnings": rep.warnings,
                "report": rep.to_dict()}
