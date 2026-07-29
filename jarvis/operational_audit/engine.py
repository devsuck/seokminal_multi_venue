"""Operational Audit Engine (P9.6) — P9.1~P9.5 원장 감사 → 발견·컴플라이언스. **감사 전용.**

소스 원장을 *데이터로만* 읽어 AuditEvent·OperatorAction·ConfigurationSnapshot 을 자체 append-only
체인에 남기고, 결정적 규칙으로 AuditFinding(INFO/WARNING/CRITICAL) 및 ComplianceReport 를 만든다.
**운영 제어권 없음: 집행/브로커/주문/킬스위치/복구실행/권한변경 없음.** 결정적·재현가능.
"""
from __future__ import annotations

import datetime as _dt

from jarvis.operational_audit import ledger, verify
from jarvis.operational_audit.models import (
    CRITICAL,
    GENESIS,
    INFO,
    WARNING,
    AuditEvent,
    AuditFinding,
    ComplianceReport,
    ConfigurationSnapshot,
    OperatorAction,
    audit_event_id,
    compliance_score,
    content_hash,
    finding_id,
    input_digest,
    operator_action_id,
    report_id,
    snapshot_id,
)

_ACTIVE_INCIDENT = {"OPEN", "ACKNOWLEDGED", "MITIGATING"}
_INCIDENT_STALE_SECONDS = 24 * 3600.0

# (소스cfg, category, event_type, severity_field)
_EVENT_SOURCES = [
    (ledger.SRC_HEALTH, "health", "health_state", "overall_status"),
    (ledger.SRC_ALERTS, "operations", "alert_created", "severity"),
    (ledger.SRC_INCIDENTS, "operations", "incident_lifecycle", "severity"),
    (ledger.SRC_ESCALATIONS, "operations", "escalation", "severity"),
    (ledger.SRC_EMERGENCY, "emergency", "emergency_decision", "emergency_state"),
    (ledger.SRC_RECOVERY_REQUESTS, "emergency", "recovery_request", ""),
    (ledger.SRC_RECOVERY_APPROVALS, "emergency", "recovery_approval", ""),
    (ledger.SRC_RECOVERY_EVENTS, "emergency", "recovery_event", "outcome"),
    (ledger.SRC_READINESS, "recovery", "recovery_readiness", "overall_status"),
    (ledger.SRC_ATTESTATIONS, "recovery", "operator_attestation", "decision"),
    (ledger.SRC_CONSOLE_ACCESS, "console", "console_access", ""),
]


def _parse(ts: str):
    try:
        return _dt.datetime.fromisoformat((ts or "").replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class OperationalAuditEngine:
    """운영 감사 엔진. 소스는 읽기전용·감사 원장은 append-only·결정적."""

    # ── 1. 감사 이벤트 수집 ──
    def collect_events(self, *, commit: bool = False) -> list[AuditEvent]:
        events: list[AuditEvent] = []
        for cfg, category, etype, sev_field in _EVENT_SOURCES:
            filename, id_field = cfg[0], cfg[1]
            for r in ledger.read_source(cfg):
                sid = str(r.get(id_field, ""))
                sev = str(r.get(sev_field, "")) if sev_field else ""
                detail = self._event_detail(etype, r)
                eid = audit_event_id(filename, sid)
                rec = AuditEvent(event_id=eid, timestamp=str(r.get("timestamp", "")),
                                 category=category, event_type=etype, subject_id=sid,
                                 severity=sev, detail=detail, source_ledger=filename,
                                 input_hash=input_digest(filename, sid),
                                 previous_hash=GENESIS).to_dict()
                rec["record_hash"] = content_hash(rec)
                events.append(AuditEvent(**rec))
        events.sort(key=lambda e: (e.timestamp or "", e.source_ledger, e.event_id))
        if commit:
            for e in events:
                if not ledger.audit_event_exists(e.event_id):
                    head = ledger.audit_events_head()
                    ledger.append_audit_event(
                        _seal(e.to_dict(), head["record_hash"] if head else GENESIS))
        return events

    @staticmethod
    def _event_detail(etype: str, r: dict) -> str:
        if etype == "incident_lifecycle":
            return f"{r.get('incident_id', '')} {r.get('from_state', '') or 'GENESIS'}->{r.get('to_state', '')}"
        if etype == "emergency_decision":
            return f"{r.get('previous_state', '') or 'NONE'}->{r.get('emergency_state', '')}"
        if etype == "recovery_approval":
            return "approved" if r.get("approved") else "rejected"
        if etype == "operator_attestation":
            return f"{r.get('operator_id', '')} {r.get('decision', '')}"
        if etype == "health_state":
            return f"score={r.get('health_score')}"
        return ""

    # ── 2. 운영자 행위 기록 ──
    def collect_operator_actions(self, *, commit: bool = False) -> list[OperatorAction]:
        actions: list[OperatorAction] = []

        def add(filename, sid, operator, action, target, decision):
            aid = operator_action_id(filename, sid)
            rec = OperatorAction(action_id=aid, timestamp="", operator_id=operator,
                                 action=action, target_id=target, decision=decision,
                                 source_ledger=filename,
                                 input_hash=input_digest(filename, sid),
                                 previous_hash=GENESIS).to_dict()
            return rec, aid

        rows = []
        for r in ledger.read_source(ledger.SRC_RECOVERY_REQUESTS):
            rec, aid = add(ledger.SRC_RECOVERY_REQUESTS[0], r.get("request_id", ""),
                           r.get("requested_by", ""), "recovery_request",
                           r.get("from_state", ""), "")
            rec["timestamp"] = str(r.get("timestamp", ""))
            rows.append((rec, aid))
        for r in ledger.read_source(ledger.SRC_RECOVERY_APPROVALS):
            rec, aid = add(ledger.SRC_RECOVERY_APPROVALS[0], r.get("approval_id", ""),
                           r.get("approver", ""), "recovery_approval",
                           r.get("request_id", ""),
                           "approved" if r.get("approved") else "rejected")
            rec["timestamp"] = str(r.get("timestamp", ""))
            rows.append((rec, aid))
        for r in ledger.read_source(ledger.SRC_ATTESTATIONS):
            rec, aid = add(ledger.SRC_ATTESTATIONS[0], r.get("attestation_id", ""),
                           r.get("operator_id", ""), "attestation",
                           r.get("incident_id", ""), r.get("decision", ""))
            rec["timestamp"] = str(r.get("timestamp", ""))
            rows.append((rec, aid))

        rows.sort(key=lambda x: (x[0]["timestamp"] or "", x[1]))
        for rec, _aid in rows:
            rec["record_hash"] = content_hash(rec)
            actions.append(OperatorAction(**rec))
        if commit:
            for a in actions:
                if not ledger.operator_action_exists(a.action_id):
                    head = ledger.operator_actions_head()
                    ledger.append_operator_action(
                        _seal(a.to_dict(), head["record_hash"] if head else GENESIS))
        return actions

    # ── 3. 설정 스냅샷 ──
    def config_snapshot(self, now: str = "", *, commit: bool = False) -> ConfigurationSnapshot:
        import jarvis.config as _cfg
        try:
            from jarvis.permissions.policy import FORBIDDEN
            forbidden_count = len(FORBIDDEN)
        except Exception:  # noqa: BLE001
            forbidden_count = -1
        conf = {"autonomy_level": _cfg.AUTONOMY_LEVEL, "min_live_level": _cfg.MIN_LIVE_LEVEL,
                "live_enabled": _cfg.live_execution_enabled(), "forbidden_count": forbidden_count}
        ih = input_digest(conf["autonomy_level"], conf["min_live_level"],
                          conf["live_enabled"], forbidden_count)
        sid = snapshot_id(ih)
        rec = ConfigurationSnapshot(
            snapshot_id=sid, timestamp=now, autonomy_level=conf["autonomy_level"],
            min_live_level=conf["min_live_level"], live_enabled=conf["live_enabled"],
            forbidden_count=forbidden_count, config=conf, input_hash=ih,
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.config_snapshot_exists(sid):
            head = ledger.config_snapshots_head()
            ledger.append_config_snapshot(_seal(rec, head["record_hash"] if head else GENESIS))
        return ConfigurationSnapshot(**rec)

    # ── 4. 감사 발견(결정적 규칙) ──
    def build_findings(self, now: str = "", *, source_chains: dict | None = None) -> list[AuditFinding]:
        findings: list[AuditFinding] = []
        source_chains = source_chains if source_chains is not None else verify.verify_source_chains()

        # Rule A: KILL_ACTIVE 후 복구 기록 없음 → WARNING
        emergencies = ledger.read_source(ledger.SRC_EMERGENCY)
        kills = [d for d in emergencies if d.get("emergency_state") == "KILL_ACTIVE"]
        if kills:
            last_kill = kills[-1]
            kt = _parse(last_kill.get("timestamp", ""))
            recovery_ts = []
            for cfg in (ledger.SRC_RECOVERY_REQUESTS, ledger.SRC_RECOVERY_EVENTS,
                        ledger.SRC_READINESS):
                for r in ledger.read_source(cfg):
                    recovery_ts.append(_parse(r.get("timestamp", "")))
            has_recovery = any(t and kt and t >= kt for t in recovery_ts)
            if not has_recovery:
                findings.append(AuditFinding(
                    finding_id=finding_id("kill_active_no_recovery",
                                          last_kill.get("decision_id", "")),
                    severity=WARNING, rule="kill_active_no_recovery",
                    subject=last_kill.get("decision_id", ""),
                    detail="KILL_ACTIVE 이후 복구 요청/이벤트/준비도 기록 없음"))

        # Rule B: 인시던트 OPEN 장기 지속 → WARNING
        latest_inc: dict = {}
        for r in ledger.read_source(ledger.SRC_INCIDENTS):
            latest_inc[r.get("incident_id")] = r
        n_now = _parse(now)
        for inc_id, r in sorted(latest_inc.items(), key=lambda kv: str(kv[0])):
            if r.get("to_state") in _ACTIVE_INCIDENT:
                lt = _parse(r.get("timestamp", ""))
                if n_now and lt and (n_now - lt).total_seconds() > _INCIDENT_STALE_SECONDS:
                    age = int((n_now - lt).total_seconds())
                    findings.append(AuditFinding(
                        finding_id=finding_id("incident_open_long", str(inc_id)),
                        severity=WARNING, rule="incident_open_long", subject=str(inc_id),
                        detail=f"활성 인시던트 {age}s 지속(>{int(_INCIDENT_STALE_SECONDS)}s)"))

        # Rule C: 실패한 복구 승인 → INFO
        for r in ledger.read_source(ledger.SRC_RECOVERY_APPROVALS):
            if r.get("approved") is False:
                findings.append(AuditFinding(
                    finding_id=finding_id("failed_recovery_approval", r.get("approval_id", "")),
                    severity=INFO, rule="failed_recovery_approval",
                    subject=r.get("approval_id", ""), detail="복구 승인 반려"))
        for r in ledger.read_source(ledger.SRC_RECOVERY_EVENTS):
            if r.get("outcome") == "rejected":
                findings.append(AuditFinding(
                    finding_id=finding_id("failed_recovery_approval", r.get("event_id", "")),
                    severity=INFO, rule="failed_recovery_approval",
                    subject=r.get("event_id", ""), detail="복구 이벤트 반려"))

        # Rule D: 해시 체인 손상 → CRITICAL
        for filename, res in sorted(source_chains.items()):
            if not res["ok"]:
                findings.append(AuditFinding(
                    finding_id=finding_id("hash_chain_broken", filename),
                    severity=CRITICAL, rule="hash_chain_broken", subject=filename,
                    detail=f"체인 손상: {res['reason']}"))

        # 중복 제거 + 결정적 정렬
        uniq: dict = {}
        for f in findings:
            uniq[f.finding_id] = f
        return sorted(uniq.values(), key=lambda f: f.sort_key())

    # ── 5. 컴플라이언스 리포트 ──
    def audit(self, now: str = "", *, commit: bool = False) -> dict:
        events = self.collect_events(commit=commit)
        actions = self.collect_operator_actions(commit=commit)
        cfg_snap = self.config_snapshot(now, commit=commit)
        source_chains = verify.verify_source_chains()
        findings = self.build_findings(now, source_chains=source_chains)

        crit = sum(1 for f in findings if f.severity == CRITICAL)
        warn = sum(1 for f in findings if f.severity == WARNING)
        info = sum(1 for f in findings if f.severity == INFO)
        chain_status = "intact" if all(r["ok"] for r in source_chains.values()) else "broken"
        score = compliance_score(crit, warn, info)

        ts = [e.timestamp for e in events if e.timestamp]
        period = {"start": min(ts) if ts else None, "end": max(ts) if ts else None}

        ih = input_digest([e.event_id for e in events], [f.finding_id for f in findings],
                          chain_status, score)
        rid = report_id(ih)
        rep = ComplianceReport(
            report_id=rid, timestamp=now, audit_period=period, event_count=len(events),
            critical_findings=crit, warning_findings=warn, info_findings=info,
            chain_status=chain_status, compliance_score=score,
            findings=[f.to_dict() for f in findings], input_hash=ih,
            previous_hash=GENESIS).to_dict()
        rep["record_hash"] = content_hash(rep)
        if commit and not ledger.compliance_report_exists(rid):
            head = ledger.compliance_reports_head()
            ledger.append_compliance_report(_seal(rep, head["record_hash"] if head else GENESIS))

        return {"report": ComplianceReport(**rep), "events": events, "actions": actions,
                "config_snapshot": cfg_snap, "findings": findings,
                "source_chains": source_chains}
