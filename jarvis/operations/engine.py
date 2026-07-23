"""Operations Engine (P9.2) — 헬스 관측 → Alert → Incident → Escalation → Ack → Resolution.

**관제 전용.** P9.1 SystemHealthReport 를 *데이터로만* 읽어(집행 코드 import 없음) 관제 레코드를
append-only 로 남긴다. **주문/집행/브로커/킬스위치/상태변경 없음.** 결정적·해시체인.

Alert 규칙: 비정상 서브시스템 상태 → severity 매핑(WARNING→WARNING, CRITICAL→CRITICAL,
OFFLINE→ERROR, UNKNOWN→INFO). Incident: 동일 alert_key 가 persist_threshold 회 이상 지속 →
활성 인시던트 없으면 생성(상태머신). Escalation: CRITICAL 인시던트가 escalation_minutes 이상
지속 → EscalationRecord(레코드만 — 이메일/Slack/Webhook/SMS 발송 없음).
"""
from __future__ import annotations

import datetime as _dt

from jarvis.operations import ledger
from jarvis.operations.models import (
    _ACTIVE_INCIDENT_STATES,
    Acknowledgement,
    Alert,
    CRITICAL,
    Escalation,
    GENESIS,
    IllegalTransition,
    IncidentEvent,
    OPEN,
    RESOLVED,
    Resolution,
    ack_id,
    alert_id,
    alert_key,
    can_transition,
    content_hash,
    escalation_id,
    fold_incident_state,
    incident_event_id,
    incident_id,
    input_digest,
    is_incident_severity,
    resolution_id,
    severity_of_status,
)


def _parse(ts: str):
    try:
        return _dt.datetime.fromisoformat((ts or "").replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _seal(rec: dict, previous_hash: str) -> dict:
    """previous_hash 를 채우고 record_hash(콘텐츠 해시)를 봉인. record_hash 는 previous_hash 와
    무관(콘텐츠만) → 체인 위치가 바뀌어도 콘텐츠 무결성은 독립 검증된다."""
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class OperationsEngine:
    """관제 엔진. 읽기전용(관측 대상)·append-only(관제 원장)·결정적."""

    def __init__(self, *, persist_threshold: int = 2, escalation_minutes: float = 15.0):
        self.persist_threshold = max(1, int(persist_threshold))
        self.escalation_minutes = float(escalation_minutes)

    # ── 헬스 리포트 로드(P9.1 원장을 데이터로만) ──
    @staticmethod
    def _latest_report() -> dict:
        try:
            from jarvis.system_health.ledger import last_report
            return last_report() or {}
        except Exception:  # noqa: BLE001 — 관측 로드 실패는 빈 리포트로 흡수
            return {}

    # ── Alert 생성 ──
    def derive_alerts(self, report, now: str = "", *, commit: bool = False) -> list[Alert]:
        report = report.to_dict() if hasattr(report, "to_dict") else dict(report or {})
        rid = report.get("report_id", "")
        subsystems = report.get("subsystems", [])

        built: list[dict] = []
        # 서브시스템별 알림(결정적 순서 유지)
        for p in subsystems:
            status = p.get("status", "")
            sev = severity_of_status(status)
            if sev is None:                      # HEALTHY/DEGRADED → 알림 없음
                continue
            built.append(self._alert_dict(p.get("name", "?"), sev, status, rid, now,
                                          message=str(p.get("detail", ""))))
        # 전체(overall) 알림 — source="system"
        overall = report.get("overall_status", "")
        osev = severity_of_status(overall)
        if osev is not None:
            built.append(self._alert_dict("system", osev, overall, rid, now,
                                          message=f"overall_status={overall}"))

        out: list[dict] = []
        for rec in built:
            if commit and not ledger.alert_exists(rec["alert_id"]):
                head = ledger.alerts_head()
                prev = head["record_hash"] if head else GENESIS
                rec = _seal(rec, prev)
                ledger.append_alert(rec)
            out.append(rec)
        return [Alert(**r) for r in out]

    @staticmethod
    def _alert_dict(source: str, severity: str, status: str, rid: str, now: str,
                    *, message: str) -> dict:
        aid = alert_id(source, severity, rid, now)
        akey = alert_key(source, severity)
        ih = input_digest(source, severity, status, rid)
        rec = Alert(alert_id=aid, timestamp=now, source=source, severity=severity,
                    health_status=status, alert_key=akey, report_id=rid, message=message,
                    input_hash=ih, previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        return rec

    # ── Incident 생성(지속 시) ──
    def _maybe_open_incident(self, a_key: str, severity: str, now: str,
                             *, commit: bool) -> dict | None:
        if not is_incident_severity(severity):
            return None
        if ledger.count_alerts_by_key(a_key) < self.persist_threshold:
            return None
        if ledger.active_incident_for_key(a_key, _ACTIVE_INCIDENT_STATES) is not None:
            return None                          # 이미 활성 인시던트 존재 → dedup
        return self._transition(incident_id(a_key, now), a_key, severity, "", OPEN, now,
                                reason="alert_persisted", actor="system", commit=commit)

    def _transition(self, inc_id: str, a_key: str, severity: str, from_state: str,
                    to_state: str, now: str, *, reason: str, actor: str,
                    commit: bool) -> dict:
        if not can_transition(from_state, to_state):
            raise IllegalTransition(f"{from_state or 'GENESIS'} -> {to_state} 차단")
        ev_id = incident_event_id(inc_id, from_state, to_state, now)
        ih = input_digest(inc_id, from_state, to_state, now)
        rec = IncidentEvent(event_id=ev_id, incident_id=inc_id, timestamp=now,
                            alert_key=a_key, severity=severity, from_state=from_state,
                            to_state=to_state, reason=reason, actor=actor, input_hash=ih,
                            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.incident_event_exists(inc_id, from_state, to_state):
            head = ledger.incidents_head()
            prev = head["record_hash"] if head else GENESIS
            rec = _seal(rec, prev)
            ledger.append_incident(rec)
        return rec

    def transition(self, incident_id_: str, to_state: str, now: str, *,
                   reason: str = "", actor: str = "operator", commit: bool = False) -> dict:
        """운영자 주도 상태 전이(가드 강제). 차단 전이는 IllegalTransition."""
        events = ledger.incident_events(incident_id_)
        cur = fold_incident_state(events)
        a_key = events[-1]["alert_key"] if events else ""
        sev = events[-1]["severity"] if events else ""
        return self._transition(incident_id_, a_key, sev, cur, to_state, now,
                                reason=reason, actor=actor, commit=commit)

    def _safe_advance(self, incident_id_: str, to_state: str, now: str, *,
                      reason: str, actor: str, commit: bool) -> dict | None:
        """멱등 전이: 이미 목표 상태거나 도달 불가면 no-op(예외 없음). ack/resolve 용."""
        events = ledger.incident_events(incident_id_)
        cur = fold_incident_state(events)
        if cur == to_state or not can_transition(cur, to_state):
            return None
        a_key = events[-1]["alert_key"] if events else ""
        sev = events[-1]["severity"] if events else ""
        return self._transition(incident_id_, a_key, sev, cur, to_state, now,
                                reason=reason, actor=actor, commit=commit)

    # ── Acknowledgement ──
    def acknowledge(self, incident_id_: str, operator: str, now: str, *,
                    note: str = "", commit: bool = False) -> dict:
        """Operator ACK. incidents 원장에 OPEN→ACKNOWLEDGED 전이(멱등) + acknowledgements 원장 기록."""
        self._safe_advance(incident_id_, "ACKNOWLEDGED", now, reason="operator_ack",
                           actor=operator, commit=commit)
        aid = ack_id(incident_id_, operator, now)
        ih = input_digest(incident_id_, operator, note)
        rec = Acknowledgement(ack_id=aid, timestamp=now, incident_id=incident_id_,
                              operator=operator, note=note, input_hash=ih,
                              previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.ack_exists(aid):
            head = ledger.acks_head()
            prev = head["record_hash"] if head else GENESIS
            rec = _seal(rec, prev)
            ledger.append_ack(rec)
        return rec

    # ── Escalation(레코드만 — 실제 발송 없음) ──
    def _maybe_escalate(self, inc_id: str, now: str, *, commit: bool) -> dict | None:
        events = ledger.incident_events(inc_id)
        if not events:
            return None
        state = fold_incident_state(events)
        if state not in _ACTIVE_INCIDENT_STATES:
            return None
        sev = events[-1]["severity"]
        if sev != CRITICAL:
            return None
        opened = _parse(events[0]["timestamp"])
        cur = _parse(now)
        if not opened or not cur:
            return None
        duration = (cur - opened).total_seconds()
        if duration < self.escalation_minutes * 60.0:
            return None
        if ledger.escalation_count(inc_id) > 0:      # 이미 에스컬레이션됨 → 재발송 없음
            return None
        level = 1
        eid = escalation_id(inc_id, level, now)
        ih = input_digest(inc_id, level, sev)
        rec = Escalation(escalation_id=eid, timestamp=now, incident_id=inc_id,
                         alert_key=events[-1]["alert_key"], severity=sev, level=level,
                         duration_seconds=round(duration, 3),
                         reason=f"critical_persisted_{int(duration)}s",
                         channels_notified=[],              # 발송 없음 — 항상 빈 목록
                         input_hash=ih, previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.escalation_exists(eid):
            head = ledger.escalations_head()
            prev = head["record_hash"] if head else GENESIS
            rec = _seal(rec, prev)
            ledger.append_escalation(rec)
        return rec

    # ── Resolution ──
    def resolve(self, incident_id_: str, resolved_by: str, now: str, *,
                resolution: str = "fixed", note: str = "", commit: bool = False) -> dict:
        """Incident 종료 기록. incidents 원장에 →RESOLVED 전이(멱등) + resolution 원장 기록."""
        self._safe_advance(incident_id_, "RESOLVED", now, reason="operator_resolve",
                           actor=resolved_by, commit=commit)
        rsid = resolution_id(incident_id_, now)
        ih = input_digest(incident_id_, resolution, note)
        rec = Resolution(resolution_id=rsid, timestamp=now, incident_id=incident_id_,
                         resolved_by=resolved_by, resolution=resolution, note=note,
                         input_hash=ih, previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.resolution_exists(rsid):
            head = ledger.resolutions_head()
            prev = head["record_hash"] if head else GENESIS
            rec = _seal(rec, prev)
            ledger.append_resolution(rec)
        return rec

    def close(self, incident_id_: str, now: str, *, actor: str = "operator",
              commit: bool = False) -> dict:
        return self.transition(incident_id_, "CLOSED", now, reason="closed", actor=actor,
                               commit=commit)

    # ── 한 번의 관제 사이클(alert→incident→escalation) ──
    def process(self, report=None, now: str = "", *, commit: bool = False) -> dict:
        if report is None:
            report = self._latest_report()
        alerts = self.derive_alerts(report, now, commit=commit)

        incidents_opened: list[dict] = []
        seen_keys: set = set()
        for a in alerts:
            if a.alert_key in seen_keys:
                continue
            seen_keys.add(a.alert_key)
            inc = self._maybe_open_incident(a.alert_key, a.severity, now, commit=commit)
            if inc is not None:
                incidents_opened.append(inc)

        escalations: list[dict] = []
        # 활성 인시던트(방금 연 것 + 기존) 중 CRITICAL 지속분 에스컬레이션
        active_ids = {r["incident_id"] for r in ledger.read_incidents()
                      if fold_incident_state(ledger.incident_events(r["incident_id"]))
                      in _ACTIVE_INCIDENT_STATES}
        for inc_id in sorted(active_ids):
            esc = self._maybe_escalate(inc_id, now, commit=commit)
            if esc is not None:
                escalations.append(esc)

        return {
            "report_id": report.get("report_id", "") if isinstance(report, dict) else "",
            "now": now,
            "alerts": [a.to_dict() for a in alerts],
            "incidents_opened": incidents_opened,
            "escalations": escalations,
        }
