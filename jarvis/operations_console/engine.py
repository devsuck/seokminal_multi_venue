"""Operations Console Engine (P9.5) — 읽기전용 집계·대시보드·타임라인. **제어 없음.**

P9.1~P9.4 원장을 JSONL 로만 읽어 OperationsSnapshot·TimelineEvent·DashboardView 를 만든다.
**명령 실행·서비스 재시작·상태변경·킬스위치·복구 실행·주문·브로커 없음.** 순수 함수적 집계(원장
쓰기 없음). 결정적(동일 데이터 → 동일 산출). CLI 렌더도 순수 텍스트 변환.
"""
from __future__ import annotations

from jarvis.operations_console import ledger, verify
from jarvis.operations_console.models import (
    NO_DATA,
    S_ALERT,
    S_EMERGENCY,
    S_ESCALATION,
    S_HEALTH,
    S_INCIDENT,
    S_RECOVERY,
    DashboardView,
    OperationsSnapshot,
    TimelineEvent,
)

_ACTIVE_INCIDENT = {"OPEN", "ACKNOWLEDGED", "MITIGATING"}


class OperationsConsole:
    """운영 관제 콘솔. **읽기전용 집계기** — 원장 쓰기/상태변경 없음."""

    # ── 요약 집계 ──
    def health_summary(self) -> dict:
        reps = ledger.read_health()
        if not reps:
            return {"overall_status": NO_DATA, "health_score": None, "total": 0,
                    "healthy": 0, "unhealthy": 0, "degraded": []}
        h = reps[-1]
        summ = h.get("summary", {}) or {}
        return {"overall_status": h.get("overall_status", NO_DATA),
                "health_score": h.get("health_score"),
                "total": summ.get("total", 0), "healthy": summ.get("healthy", 0),
                "unhealthy": summ.get("unhealthy", 0), "degraded": summ.get("degraded", [])}

    def alert_summary(self) -> dict:
        alerts = ledger.read_alerts()
        dist = {"INFO": 0, "WARNING": 0, "ERROR": 0, "CRITICAL": 0}
        for a in alerts:
            s = a.get("severity")
            if s in dist:
                dist[s] += 1
        dist["total"] = len(alerts)
        return dist

    def _fold_incidents(self) -> dict:
        latest: dict = {}
        for r in ledger.read_incidents():
            latest[r.get("incident_id")] = r
        return latest

    def incident_summary(self) -> dict:
        latest = self._fold_incidents()
        crit = warn = active = 0
        for r in latest.values():
            if r.get("to_state") in _ACTIVE_INCIDENT:
                active += 1
                if r.get("severity") == "CRITICAL":
                    crit += 1
                else:
                    warn += 1
        return {"CRITICAL": crit, "WARNING": warn, "active_total": active,
                "tracked_total": len(latest)}

    def emergency_state(self) -> str:
        reps = ledger.read_emergency()
        return reps[-1].get("emergency_state", NO_DATA) if reps else NO_DATA

    def recovery_status(self) -> dict:
        reps = ledger.read_readiness()
        atts = ledger.read_attestations()
        ev_n = len(ledger.read_evidence())
        last_att = atts[-1] if atts else None
        if not reps:
            return {"readiness": NO_DATA, "failed_checks": [], "warnings": [],
                    "evidence_count": ev_n,
                    "latest_attestation": (None if not last_att else
                                           {"operator_id": last_att.get("operator_id"),
                                            "decision": last_att.get("decision"),
                                            "timestamp": last_att.get("timestamp")})}
        r = reps[-1]
        return {"readiness": r.get("overall_status", NO_DATA),
                "failed_checks": r.get("mandatory_failures", []),
                "warnings": r.get("warnings", []),
                "evidence_count": ev_n,
                "latest_attestation": (None if not last_att else
                                       {"operator_id": last_att.get("operator_id"),
                                        "decision": last_att.get("decision"),
                                        "timestamp": last_att.get("timestamp")})}

    def audit_status(self) -> dict:
        v = verify.verify_all()
        latest_hashes = {name: res.get("latest_hash") for name, res in v["ledgers"].items()}
        return {"ok": v["ok"], "total_records": v["n"], "ledgers": v["ledgers"],
                "latest_hashes": latest_hashes}

    # ── 스냅샷 ──
    def snapshot(self, now: str = "") -> OperationsSnapshot:
        return OperationsSnapshot(
            timestamp=now, health_summary=self.health_summary(),
            alert_summary=self.alert_summary(), incident_summary=self.incident_summary(),
            emergency_state=self.emergency_state(), recovery_status=self.recovery_status(),
            audit_status=self.audit_status())

    # ── 타임라인(다중 소스 집계·시간 정렬·중복 방지) ──
    def timeline(self) -> list[TimelineEvent]:
        events: list[TimelineEvent] = []
        seen: set = set()

        def add(ev: TimelineEvent):
            if ev.event_id in seen:
                return
            seen.add(ev.event_id)
            events.append(ev)

        for h in ledger.read_health():
            add(TimelineEvent(f"{S_HEALTH}:{h.get('report_id', '')}", S_HEALTH,
                              h.get("overall_status", ""), h.get("timestamp", ""),
                              f"health {h.get('overall_status', '')} score={h.get('health_score')}"))
        for a in ledger.read_alerts():
            add(TimelineEvent(f"{S_ALERT}:{a.get('alert_id', '')}", S_ALERT,
                              a.get("severity", ""), a.get("timestamp", ""),
                              f"alert {a.get('source', '')} {a.get('severity', '')}"))
        for r in ledger.read_incidents():
            add(TimelineEvent(f"{S_INCIDENT}:{r.get('event_id', '')}", S_INCIDENT,
                              r.get("severity", ""), r.get("timestamp", ""),
                              f"incident {r.get('incident_id', '')} "
                              f"{r.get('from_state', '') or 'GENESIS'}->{r.get('to_state', '')}"))
        for e in ledger.read_escalations():
            add(TimelineEvent(f"{S_ESCALATION}:{e.get('escalation_id', '')}", S_ESCALATION,
                              e.get("severity", ""), e.get("timestamp", ""),
                              f"escalation {e.get('incident_id', '')} L{e.get('level', '')}"))
        for d in ledger.read_emergency():
            add(TimelineEvent(f"{S_EMERGENCY}:{d.get('decision_id', '')}", S_EMERGENCY,
                              d.get("emergency_state", ""), d.get("timestamp", ""),
                              f"emergency {d.get('previous_state', '') or 'NONE'}"
                              f"->{d.get('emergency_state', '')}"))
        for r in ledger.read_readiness():
            add(TimelineEvent(f"{S_RECOVERY}:readiness:{r.get('report_id', '')}", S_RECOVERY,
                              r.get("overall_status", ""), r.get("timestamp", ""),
                              f"readiness {r.get('overall_status', '')}"))
        for a in ledger.read_attestations():
            add(TimelineEvent(f"{S_RECOVERY}:attest:{a.get('attestation_id', '')}", S_RECOVERY,
                              a.get("decision", ""), a.get("timestamp", ""),
                              f"attestation {a.get('operator_id', '')} {a.get('decision', '')}"))

        events.sort(key=lambda ev: ev.sort_key())
        return events

    # ── 패널 ──
    def system_overview(self) -> dict:
        hs = self.health_summary()
        isum = self.incident_summary()
        return {"overall_health": hs["overall_status"], "health_score": hs["health_score"],
                "unhealthy_subsystems": hs["unhealthy"], "degraded": hs["degraded"],
                "active_incidents": isum["active_total"],
                "incident_critical": isum["CRITICAL"], "incident_warning": isum["WARNING"],
                "emergency_state": self.emergency_state(),
                "recovery_readiness": self.recovery_status()["readiness"]}

    def emergency_panel(self) -> dict:
        reps = ledger.read_emergency()
        last = reps[-1] if reps else {}
        return {"emergency_state": last.get("emergency_state", NO_DATA),
                "previous_state": last.get("previous_state", ""),
                "kill_latch": last.get("emergency_state") == "KILL_ACTIVE",
                "source": last.get("source", ""), "reasons": last.get("reasons", []),
                "read_only": True}

    def recovery_panel(self) -> dict:
        rs = self.recovery_status()
        return {"readiness": rs["readiness"], "failed_checks": rs["failed_checks"],
                "warnings": rs["warnings"], "evidence_count": rs["evidence_count"],
                "latest_attestation": rs["latest_attestation"], "read_only": True}

    def audit_panel(self) -> dict:
        a = self.audit_status()
        return {"chain_ok": a["ok"], "total_records": a["total_records"],
                "latest_hashes": a["latest_hashes"],
                "ledgers": {k: {"ok": v["ok"], "n": v["n"], "reason": v["reason"]}
                            for k, v in a["ledgers"].items()}}

    # ── 대시보드 ──
    def dashboard(self, now: str = "") -> DashboardView:
        return DashboardView(
            timestamp=now, snapshot=self.snapshot(now).to_dict(),
            system_overview=self.system_overview(), emergency_panel=self.emergency_panel(),
            recovery_panel=self.recovery_panel(), audit_panel=self.audit_panel(),
            timeline=[e.to_dict() for e in self.timeline()])


def render_dashboard(view: DashboardView) -> str:
    """DashboardView → 순수 텍스트(제어 요소 없음)."""
    so = view.system_overview
    ep = view.emergency_panel
    rp = view.recovery_panel
    ap = view.audit_panel
    lines = []
    lines.append("System:")
    lines.append(f" {so.get('overall_health', NO_DATA)}"
                 + (f" (score {so.get('health_score')})" if so.get("health_score") is not None else ""))
    lines.append(f" unhealthy subsystems: {so.get('unhealthy_subsystems', 0)}")
    lines.append("")
    lines.append("Incidents:")
    lines.append(f" CRITICAL:{so.get('incident_critical', 0)}")
    lines.append(f" WARNING:{so.get('incident_warning', 0)}")
    lines.append("")
    lines.append("Emergency:")
    lines.append(f" {ep.get('emergency_state', NO_DATA)}"
                 + ("  [KILL LATCH]" if ep.get("kill_latch") else ""))
    lines.append("")
    lines.append("Recovery:")
    lines.append(f" {rp.get('readiness', NO_DATA)}")
    if rp.get("failed_checks"):
        lines.append(f" failed: {', '.join(rp['failed_checks'])}")
    lines.append("")
    lines.append("Audit:")
    lines.append(f" chain: {'OK' if ap.get('chain_ok') else 'BROKEN'} "
                 f"({ap.get('total_records', 0)} records)")
    lines.append("")
    lines.append("(read-only view — no controls)")
    return "\n".join(lines)
