"""Observability Engine (P17) — 모니터·측정·분석·보고. **관찰 전용, 동작 실행 없음.**

**거래·주문·배포·자동 복구·자동 결정·자동 승인을 하지 않는다.** execution/broker/portfolio/permission/deployment/
live import·호출 없음. OBSERVE ≠ EXECUTE · ALERT ≠ REMEDIATION. 결정적·불변·append-only·이벤트 소싱.
"""
from __future__ import annotations

from jarvis.observability import ledger
from jarvis.observability.models import (
    ART_DASHBOARD,
    ART_TARGET,
    GENESIS,
    H_DEGRADED,
    H_FAILED,
    H_RECOVERED,
    H_UNKNOWN,
    AlertRecord,
    ArtifactRecord,
    AuditObservationRecord,
    AvailabilityRecord,
    DashboardRecord,
    HealthEventRecord,
    IllegalHealthTransition,
    ImmutableTargetError,
    MetricRecord,
    ObservabilitySummary,
    ObservationRecord,
    PerfSnapshotRecord,
    UnknownTargetError,
    alert_id as _alert_id,
    artifact_id as _artifact_id,
    audit_obs_id as _audit_obs_id,
    availability_id as _availability_id,
    can_transition,
    content_hash,
    dashboard_id as _dashboard_id,
    health_event_id as _health_event_id,
    input_digest,
    metric_id as _metric_id,
    observation_id as _observation_id,
    perf_id as _perf_id,
    severity_for_health,
    target_id as _target_id,
)

_DISCLAIMER = ("Observability & Operations Intelligence 데이터 — OBSERVE ≠ EXECUTE · MONITOR ≠ CONTROL · "
               "ALERT ≠ REMEDIATION. 모니터·측정·분석·기록 전용 — 거래·주문·배포·자동 복구·자동 결정·자동 승인 없음.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ObservabilityEngine:
    """운영 인텔리전스 엔진. 불변·append-only·이벤트 소싱·결정적. 실행/복구/배포/결정 권한 없음."""

    # ══════════════ 아티팩트 계보(내부) ══════════════
    def _artifact(self, atype: str, ref: str, parent: str, now: str,
                *, commit: bool) -> ArtifactRecord:
        aid = _artifact_id(atype, ref)
        rec = ArtifactRecord(artifact_id=aid, artifact_type=atype, ref_id=ref,
                             parent_artifact=parent, created_at=now,
                             input_hash=input_digest(atype, ref), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return ArtifactRecord(**rec)

    # ══════════════ 건강 생애주기(event-sourced) ══════════════
    def _health_event(self, target: str, name: str, kind: str, frm: str, to: str, note: str,
                   now: str, *, commit: bool) -> HealthEventRecord:
        seq = len(ledger.target_events(target))
        eid = _health_event_id(target, to, seq)
        rec = HealthEventRecord(health_event_id=eid, target_id=target, name=name, kind=kind,
                                from_state=frm, to_state=to, note=note, occurred_at=now,
                                input_hash=input_digest(target, to, seq),
                                previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.health_event_exists(eid):
            head = ledger.health_head()
            ledger.append_health_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return HealthEventRecord(**rec)

    def _meta(self, target: str) -> dict:
        evs = ledger.target_events(target)
        if not evs:
            raise UnknownTargetError(f"미등록 대상 {target}")
        g = evs[0]
        return {"target_id": target, "name": g.get("name"), "kind": g.get("kind"),
                "state": evs[-1].get("to_state")}

    def current_health(self, target: str) -> str | None:
        evs = ledger.target_events(target)
        return evs[-1].get("to_state") if evs else None

    def _require_target(self, target: str) -> str:
        st = self.current_health(target)
        if st is None:
            raise UnknownTargetError(f"미등록 대상 {target}")
        return st

    # ══════════════ register_target ══════════════
    def register_target(self, name: str, kind: str = "RESEARCH_LAYER", now: str = "",
                     *, commit: bool = False) -> HealthEventRecord:
        """모니터 대상 등록(genesis UNKNOWN). **관찰 대상 선언만.**"""
        tid = _target_id(name)
        evs = ledger.target_events(tid)
        if evs:
            g = evs[0]
            if g.get("kind") != kind:
                raise ImmutableTargetError(f"{tid} 대상 불변 — 변경 불가")
            return HealthEventRecord(**{k: v for k, v in g.items()
                                        if k in HealthEventRecord.__dataclass_fields__})
        ev = self._health_event(tid, name, kind, GENESIS, H_UNKNOWN, "registered", now, commit=commit)
        self._artifact(ART_TARGET, tid, "", now, commit=commit)
        return ev

    # ══════════════ observe_health (전이 검증) ══════════════
    def observe_health(self, target: str, to_state: str, note: str = "", now: str = "",
                    *, commit: bool = False) -> HealthEventRecord:
        """건강 상태 전이 관찰(불변). 유효하지 않은 전이는 차단. **관찰·기록만 — 복구 아님.**"""
        frm = self._require_target(target)
        if not can_transition(frm, to_state):
            raise IllegalHealthTransition(f"{target} {frm}→{to_state} 불가")
        m = self._meta(target)
        return self._health_event(target, m["name"], m["kind"], frm, to_state, note, now,
                                  commit=commit)

    # ══════════════ record_metric ══════════════
    def record_metric(self, key: str, value: float, unit: str = "", target: str = "",
                   metadata: dict | None = None, now: str = "",
                   *, commit: bool = False) -> MetricRecord:
        """시스템/파이프라인 지표 기록(불변). **측정만.**"""
        seq = len(ledger.metrics_by_key(key))
        mid = _metric_id(key, target, seq)
        rec = MetricRecord(metric_id=mid, key=key, target_id=target, value=float(value), unit=unit,
                           metadata=dict(metadata or {}), recorded_at=now,
                           input_hash=input_digest(key, target, seq),
                           previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.metric_exists(mid):
            head = ledger.metrics_head()
            ledger.append_metric(_seal(rec, head["record_hash"] if head else GENESIS))
        return MetricRecord(**rec)

    def collect_source_metrics(self, now: str = "", *, commit: bool = False) -> list:
        """모든 모니터 대상의 레코드 수를 READ ONLY 로 읽어 지표로 기록. **읽기만·기록만.**"""
        out = []
        for target, count in ledger.all_target_counts().items():
            out.append(self.record_metric(f"source_count:{target}", count, "records", target,
                                          {"read_only": True}, now, commit=commit))
        return out

    # ══════════════ record_observation (데이터 품질/무결성) ══════════════
    def record_observation(self, code: str, subject: str, detail: str = "",
                        metadata: dict | None = None, now: str = "",
                        *, commit: bool = False) -> ObservationRecord:
        """데이터 품질·무결성 관찰 기록(불변). **관찰만.**"""
        seq = len(ledger.read_observations())
        oid = _observation_id(code, subject, seq)
        rec = ObservationRecord(observation_id=oid, code=code, subject=subject, detail=detail,
                                metadata=dict(metadata or {}), recorded_at=now,
                                input_hash=input_digest(code, subject, seq),
                                previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.observation_exists(oid):
            head = ledger.observations_head()
            ledger.append_observation(_seal(rec, head["record_hash"] if head else GENESIS))
        return ObservationRecord(**rec)

    def check_data_quality(self, records: list, *, id_field: str = "record_hash",
                        parent_field: str | None = None, now: str = "",
                        subject: str = "dataset", commit: bool = False) -> list:
        """레코드 집합 데이터 품질 점검 → 관찰 기록(중복 아티팩트·dangling 참조·무결성). **관찰만.**"""
        obs = []
        # 중복 ID
        seen: set = set()
        dups: set = set()
        for r in records:
            rid = r.get(id_field)
            if rid in seen:
                dups.add(rid)
            seen.add(rid)
        if dups:
            obs.append(self.record_observation("DUPLICATE_ARTIFACT", subject,
                                               f"{len(dups)} duplicate ids", {"count": len(dups)},
                                               now, commit=commit))
        # dangling 참조
        if parent_field:
            ids = {r.get(id_field) for r in records}
            dangling = [r for r in records
                        if r.get(parent_field) and r.get(parent_field) not in ids]
            if dangling:
                obs.append(self.record_observation("INVALID_REFERENCE", subject,
                                                   f"{len(dangling)} dangling refs",
                                                   {"count": len(dangling)}, now, commit=commit))
        # 빈 데이터
        if not records:
            obs.append(self.record_observation("MISSING_DATA", subject, "no records", {}, now,
                                               commit=commit))
        return obs

    # ══════════════ record_performance ══════════════
    def record_performance(self, name: str, duration: float, unit: str = "s",
                        metadata: dict | None = None, now: str = "",
                        *, commit: bool = False) -> PerfSnapshotRecord:
        """성능(처리·테스트·연구·시뮬·리포트) 스냅샷 기록(불변). **측정만.**"""
        seq = len(ledger.read_perf())
        pid = _perf_id(name, seq)
        rec = PerfSnapshotRecord(perf_id=pid, name=name, duration=float(duration), unit=unit,
                                 metadata=dict(metadata or {}), recorded_at=now,
                                 input_hash=input_digest(name, seq),
                                 previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.perf_exists(pid):
            head = ledger.perf_head()
            ledger.append_perf(_seal(rec, head["record_hash"] if head else GENESIS))
        return PerfSnapshotRecord(**rec)

    # ══════════════ record_availability ══════════════
    def record_availability(self, target: str, available: bool, detail: str = "", now: str = "",
                         *, commit: bool = False) -> AvailabilityRecord:
        """대상 가용성 기록(불변). **관찰만.**"""
        self._require_target(target)
        seq = len([r for r in ledger.read_availability() if r.get("target_id") == target])
        aid = _availability_id(target, seq)
        rec = AvailabilityRecord(availability_id=aid, target_id=target, available=bool(available),
                                 detail=detail, recorded_at=now, input_hash=input_digest(target, seq),
                                 previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.availability_exists(aid):
            head = ledger.availability_head()
            ledger.append_availability(_seal(rec, head["record_hash"] if head else GENESIS))
        return AvailabilityRecord(**rec)

    # ══════════════ record_audit_observation ══════════════
    def record_audit_observation(self, subject: str, observation: str,
                              metadata: dict | None = None, now: str = "",
                              *, commit: bool = False) -> AuditObservationRecord:
        """감사 가시성 관찰 기록(불변). **관찰만.**"""
        seq = len(ledger.read_audit())
        aid = _audit_obs_id(subject, seq)
        rec = AuditObservationRecord(audit_obs_id=aid, subject=subject, observation=observation,
                                     metadata=dict(metadata or {}), recorded_at=now,
                                     input_hash=input_digest(subject, seq),
                                     previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.audit_exists(aid):
            head = ledger.audit_head()
            ledger.append_audit(_seal(rec, head["record_hash"] if head else GENESIS))
        return AuditObservationRecord(**rec)

    # ══════════════ raise_alert (기록 전용) ══════════════
    def raise_alert(self, alert_type: str, severity: str, subject: str, detail: str = "",
                 metadata: dict | None = None, now: str = "",
                 *, commit: bool = False) -> AlertRecord:
        """알림 기록(불변). **is_actionable=False — 자동 복구·재시작·배포 없음.**"""
        seq = len([r for r in ledger.read_alerts() if r.get("alert_type") == alert_type])
        aid = _alert_id(alert_type, subject, seq)
        rec = AlertRecord(alert_id=aid, alert_type=alert_type, severity=severity, subject=subject,
                          detail=detail, is_actionable=False, metadata=dict(metadata or {}),
                          recorded_at=now, input_hash=input_digest(alert_type, subject, seq),
                          previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.alert_exists(aid):
            head = ledger.alerts_head()
            ledger.append_alert(_seal(rec, head["record_hash"] if head else GENESIS))
        return AlertRecord(**rec)

    def alert_on_health(self, target: str, now: str = "", *, commit: bool = False):
        """현재 건강이 DEGRADED/FAILED 면 알림 기록(기록 전용). 정상이면 None."""
        state = self._require_target(target)
        if state in (H_FAILED, H_DEGRADED):
            atype = "PIPELINE_FAILURE" if state == H_FAILED else "PERFORMANCE_DEGRADATION"
            return self.raise_alert(atype, severity_for_health(state), target,
                                    f"health={state}", {"health": state}, now, commit=commit)
        return None

    # ══════════════ 대시보드 데이터(비구속) ══════════════
    def _dashboard(self, kind: str, payload: dict, now: str) -> DashboardRecord:
        return DashboardRecord(dashboard_id=_dashboard_id(kind, now), kind=kind, payload=payload,
                               is_binding=False, generated_at=now)

    def system_overview(self, now: str = "") -> DashboardRecord:
        s = self.summary(now)
        health = {t: self.current_health(t) for t in ledger.target_ids()}
        return self._dashboard("SYSTEM_OVERVIEW", {"summary": s.to_dict(),
                               "targets": dict(sorted(health.items())),
                               "source_counts": ledger.all_target_counts(),
                               "disclaimer": _DISCLAIMER}, now)

    def pipeline_overview(self, now: str = "") -> DashboardRecord:
        counts = ledger.all_target_counts()
        return self._dashboard("PIPELINE_OVERVIEW", {"source_counts": counts,
                               "target_count": len(counts)}, now)

    def health_timeline(self, target: str, now: str = "") -> DashboardRecord:
        evs = ledger.target_events(target)
        return self._dashboard("HEALTH_TIMELINE", {"target": target,
                               "states": [e.get("to_state") for e in evs]}, now)

    def failure_timeline(self, now: str = "") -> DashboardRecord:
        fails = [{"alert_type": a.get("alert_type"), "subject": a.get("subject"),
                  "severity": a.get("severity")} for a in ledger.read_alerts()]
        return self._dashboard("FAILURE_TIMELINE", {"alerts": fails, "count": len(fails)}, now)

    def integrity_summary(self, now: str = "") -> DashboardRecord:
        obs = ledger.read_observations()
        dist: dict = {}
        for o in obs:
            dist[o.get("code")] = dist.get(o.get("code"), 0) + 1
        return self._dashboard("INTEGRITY_SUMMARY", {"observation_count": len(obs),
                               "by_code": dict(sorted(dist.items()))}, now)

    def security_summary(self, now: str = "") -> DashboardRecord:
        sec_alerts = [a for a in ledger.read_alerts() if a.get("alert_type") == "SECURITY_ISSUE"]
        return self._dashboard("SECURITY_SUMMARY", {"security_alert_count": len(sec_alerts)}, now)

    def performance_summary(self, now: str = "") -> DashboardRecord:
        perf = ledger.read_perf()
        by_name: dict = {}
        for p in perf:
            by_name.setdefault(p.get("name"), []).append(p.get("duration", 0.0))
        agg = {n: {"count": len(v), "total": round(sum(v), 9),
                   "avg": round(sum(v) / len(v), 9) if v else 0.0}
               for n, v in sorted(by_name.items())}
        return self._dashboard("PERFORMANCE_SUMMARY", {"perf_count": len(perf), "by_name": agg}, now)

    # ══════════════ verify / 조회 / summary ══════════════
    def verify_integrity(self) -> dict:
        from jarvis.observability.verify import verify_chain
        return verify_chain()

    def list_targets(self) -> list:
        return ledger.target_ids()

    def targets_in_health(self, state: str) -> list:
        return sorted(t for t in ledger.target_ids() if self.current_health(t) == state)

    def target_meta(self, target: str) -> dict:
        return self._meta(target)

    def summary(self, now: str = "") -> ObservabilitySummary:
        return ObservabilitySummary(
            timestamp=now, health_event_count=len(ledger.read_health_events()),
            metric_count=len(ledger.read_metrics()), observation_count=len(ledger.read_observations()),
            alert_count=len(ledger.read_alerts()), perf_count=len(ledger.read_perf()),
            availability_count=len(ledger.read_availability()), audit_count=len(ledger.read_audit()),
            artifact_count=len(ledger.read_artifacts()))
