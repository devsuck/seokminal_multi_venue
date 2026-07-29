"""Autonomous Research Control Plane Engine (P12.10) — 연구 시스템 관찰·분석·기록. **관찰·분석·기록 전용.**

**자동 복구·배포·결정을 하지 않는다.** execution/broker/portfolio/risk/permission/deployment/live import·호출 없음.
OBSERVE ≠ EXECUTION · MONITOR ≠ CONTROL · ANOMALY ≠ RECOVERY. 결정적·불변·append-only·이벤트 소싱.
"""
from __future__ import annotations

from jarvis.research_control import ledger
from jarvis.research_control.models import (
    ART_SNAPSHOT,
    ART_STATE,
    GENESIS,
    S_ANALYZED,
    S_ARCHIVED,
    S_INITIALIZED,
    S_OBSERVED,
    S_REPORTED,
    AlertRecord,
    ArtifactRecord,
    ControlSummary,
    HealthRecord,
    IllegalControlTransition,
    ImmutableStateError,
    MetricRecord,
    ResearchEventRecord,
    SnapshotRecord,
    StateEventRecord,
    SystemReportRecord,
    UnknownStateError,
    alert_id as _alert_id,
    artifact_id as _artifact_id,
    can_transition,
    classify_health,
    content_hash,
    event_id as _event_id,
    health_id as _health_id,
    input_digest,
    metric_id as _metric_id,
    report_id as _report_id,
    severity_for,
    snapshot_id as _snapshot_id,
    state_event_id as _state_event_id,
    state_id as _state_id,
)

_DISCLAIMER = ("Autonomous Research Control Plane 데이터 — OBSERVE ≠ EXECUTION · MONITOR ≠ CONTROL · "
               "ANOMALY ≠ RECOVERY. 연구 시스템 관찰·분석·기록 전용 — 자동 복구·배포·결정·거래 없음.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class AutonomousResearchControlPlaneEngine:
    """자율 연구 제어 평면 엔진. 불변·append-only·이벤트 소싱·결정적. 복구/배포/결정/거래 권한 없음."""

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

    # ══════════════ 상태 레지스트리 생애주기(event-sourced) ══════════════
    def _state_event(self, state: str, name: str, kind: str, frm: str, to: str, note: str,
                  now: str, *, commit: bool) -> StateEventRecord:
        seq = len(ledger.state_events(state))
        eid = _state_event_id(state, to, seq)
        rec = StateEventRecord(state_event_id=eid, state_id=state, name=name, kind=kind,
                               from_state=frm, to_state=to, note=note, occurred_at=now,
                               input_hash=input_digest(state, to, seq),
                               previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.state_event_exists(eid):
            head = ledger.states_head()
            ledger.append_state_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return StateEventRecord(**rec)

    def _meta(self, state: str) -> dict:
        evs = ledger.state_events(state)
        if not evs:
            raise UnknownStateError(f"미등록 상태 {state}")
        g = evs[0]
        return {"state_id": state, "name": g.get("name"), "kind": g.get("kind"),
                "state": evs[-1].get("to_state")}

    def current_state(self, state: str) -> str | None:
        evs = ledger.state_events(state)
        return evs[-1].get("to_state") if evs else None

    def _require_state(self, state: str) -> str:
        st = self.current_state(state)
        if st is None:
            raise UnknownStateError(f"미등록 상태 {state}")
        return st

    def _transition(self, state: str, to: str, note: str, now: str,
                  *, commit: bool) -> StateEventRecord:
        frm = self._require_state(state)
        if not can_transition(frm, to):
            raise IllegalControlTransition(f"{state} {frm}→{to} 불가")
        m = self._meta(state)
        return self._state_event(state, m["name"], m["kind"], frm, to, note, now, commit=commit)

    # ══════════════ initialize_state (Research State Registry) ══════════════
    def initialize_state(self, name: str, kind: str = "SYSTEM", now: str = "",
                      *, commit: bool = False) -> StateEventRecord:
        """관찰 대상 상태 등록(genesis INITIALIZED). **관찰 대상 선언만.**"""
        sid = _state_id(name)
        evs = ledger.state_events(sid)
        if evs:
            g = evs[0]
            if g.get("kind") != kind:
                raise ImmutableStateError(f"{sid} 상태 불변 — 변경 불가")
            return StateEventRecord(**{k: v for k, v in g.items()
                                       if k in StateEventRecord.__dataclass_fields__})
        ev = self._state_event(sid, name, kind, GENESIS, S_INITIALIZED, "initialized", now,
                               commit=commit)
        self._artifact(ART_STATE, sid, "", now, commit=commit)
        return ev

    # ══════════════ collect_state (Research Events, →OBSERVED) ══════════════
    def collect_state(self, state: str, kind: str = "OBSERVATION", source_layer: str = "",
                   source_ref: str = "", note: str = "", now: str = "",
                   *, commit: bool = False) -> ResearchEventRecord:
        """연구 이벤트 관찰·기록(불변) + INITIALIZED/OBSERVED→OBSERVED. **관찰 기록만 — 실행 아님.**"""
        st = self._require_state(state)
        if st == S_ARCHIVED:
            raise IllegalControlTransition(f"{state} ARCHIVED — 관찰 종료(불변)")
        if st in (S_INITIALIZED, S_OBSERVED):
            self._transition(state, S_OBSERVED, "observed", now, commit=commit)
        seq = len(ledger.state_records(state))
        eid = _event_id(state, kind, seq)
        rec = ResearchEventRecord(event_id=eid, state_id=state, kind=kind, source_layer=source_layer,
                                  source_ref=source_ref, note=note, recorded_at=now,
                                  input_hash=input_digest(state, kind, seq),
                                  previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.event_exists(eid):
            head = ledger.events_head()
            ledger.append_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return ResearchEventRecord(**rec)

    # ══════════════ collect_health (Health Monitoring) ══════════════
    def collect_health(self, state: str, score: float, note: str = "", now: str = "",
                    *, commit: bool = False) -> HealthRecord:
        """헬스 관찰·기록(불변). 점수→등급 결정적 라벨. **관찰만 — 복구 아님.**"""
        st = self._require_state(state)
        if st in (S_INITIALIZED, S_OBSERVED):
            self._transition(state, S_OBSERVED, "observed", now, commit=commit)
        seq = len(ledger.state_health(state))
        hid = _health_id(state, seq)
        level = classify_health(score)
        rec = HealthRecord(health_id=hid, state_id=state, score=float(score), level=level, note=note,
                           recorded_at=now, input_hash=input_digest(state, seq),
                           previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.health_exists(hid):
            head = ledger.health_head()
            ledger.append_health(_seal(rec, head["record_hash"] if head else GENESIS))
        return HealthRecord(**rec)

    # ══════════════ collect_metric (Metrics) ══════════════
    def collect_metric(self, state: str, key: str, value: float, unit: str = "", now: str = "",
                    *, commit: bool = False) -> MetricRecord:
        """지표 관찰·기록(불변). **관찰만.**"""
        self._require_state(state)
        seq = len(ledger.state_metrics(state))
        mid = _metric_id(state, key, seq)
        rec = MetricRecord(metric_id=mid, state_id=state, key=key, value=float(value), unit=unit,
                           recorded_at=now, input_hash=input_digest(state, key, seq),
                           previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.metric_exists(mid):
            head = ledger.metrics_head()
            ledger.append_metric(_seal(rec, head["record_hash"] if head else GENESIS))
        return MetricRecord(**rec)

    # ══════════════ detect_anomaly (Anomaly Alerts, →ANALYZED) ══════════════
    def detect_anomaly(self, state: str, now: str = "", *, commit: bool = False) -> list:
        """최신 헬스 등급 기반 이상 탐지(결정적). 이상 시 알림 **기록만** — 자동 복구·조치 없음.

        OBSERVED→ANALYZED 전이(관찰 후 분석). AlertRecord.is_actionable=False 고정.
        """
        st = self._require_state(state)
        if st == S_OBSERVED:
            self._transition(state, S_ANALYZED, "analyzed", now, commit=commit)
        health = ledger.state_health(state)
        alerts: list = []
        if not health:
            return alerts
        latest = health[-1]
        level = latest.get("level")
        if level in ("DEGRADED", "CRITICAL", "UNKNOWN"):
            code = f"HEALTH_{level}"
            seq = len(ledger.state_alerts(state))
            aid = _alert_id(state, code, seq)
            rec = AlertRecord(alert_id=aid, state_id=state, code=code, severity=severity_for(level),
                              detail=f"latest health level={level} score={latest.get('score')}",
                              is_actionable=False, recorded_at=now,
                              input_hash=input_digest(state, code, seq),
                              previous_hash=GENESIS).to_dict()
            rec["record_hash"] = content_hash(rec)
            if commit and not ledger.alert_exists(aid):
                head = ledger.alerts_head()
                ledger.append_alert(_seal(rec, head["record_hash"] if head else GENESIS))
            alerts.append(AlertRecord(**rec))
        return alerts

    # ══════════════ generate_system_report (System Reports, →REPORTED) ══════════════
    def generate_system_report(self, state: str, scope: str = "STATE", now: str = "",
                            *, commit: bool = False) -> SystemReportRecord:
        """시스템 상태 리포트(관찰·분석 집계). **is_binding=False, 관찰·모니터링만.**"""
        st = self._require_state(state)
        if st == S_ANALYZED:
            self._transition(state, S_REPORTED, "reported", now, commit=commit)
        events = ledger.state_records(state)
        health = ledger.state_health(state)
        metrics = ledger.state_metrics(state)
        alerts = ledger.state_alerts(state)
        sev_dist: dict = {}
        for a in alerts:
            sev_dist[a.get("severity")] = sev_dist.get(a.get("severity"), 0) + 1
        latest_health = health[-1].get("level") if health else "UNKNOWN"
        rid = _report_id(state, scope, now)
        rec = SystemReportRecord(
            report_id=rid, state_id=state, scope=scope, event_count=len(events),
            health_count=len(health), metric_count=len(metrics), alert_count=len(alerts),
            latest_health=latest_health, state_status=self.current_state(state),
            severity_distribution=dict(sorted(sev_dist.items())), is_binding=False,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(state, scope, now),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        return SystemReportRecord(**rec)

    def archive_state(self, state: str, now: str = "", *, commit: bool = False) -> StateEventRecord:
        """상태 보관(REPORTED→ARCHIVED). **상태 기록만.**"""
        return self._transition(state, S_ARCHIVED, "archived", now, commit=commit)

    # ══════════════ create_snapshot (결정적 관찰 집계) ══════════════
    def create_snapshot(self, now: str = "", *, commit: bool = False) -> SnapshotRecord:
        """전체 원장의 결정적 스냅샷(관찰 집계). is_binding=False. **관찰만 — 상태 변경 없음.**

        commit 시 스냅샷 아티팩트만 계보에 기록(원장 상태는 불변).
        """
        dist: dict = {}
        for sid in ledger.state_ids():
            cur = self.current_state(sid)
            dist[cur] = dist.get(cur, 0) + 1
        snap = SnapshotRecord(
            snapshot_id=_snapshot_id(now), timestamp=now, state_count=len(ledger.state_ids()),
            state_event_count=len(ledger.read_state_events()), event_count=len(ledger.read_events()),
            health_count=len(ledger.read_health()), metric_count=len(ledger.read_metrics()),
            alert_count=len(ledger.read_alerts()), report_count=len(ledger.read_reports()),
            artifact_count=len(ledger.read_artifacts()), state_distribution=dict(sorted(dist.items())),
            is_binding=False)
        if commit:
            self._artifact(ART_SNAPSHOT, snap.snapshot_id, "", now, commit=commit)
        return snap

    # ══════════════ verify_integrity ══════════════
    def verify_integrity(self) -> dict:
        from jarvis.research_control.verify import verify_chain
        return verify_chain()

    # ══════════════ 조회 편의 ══════════════
    def list_states(self) -> list:
        return ledger.state_ids()

    def states_in(self, state: str) -> list:
        return sorted(s for s in ledger.state_ids() if self.current_state(s) == state)

    def state_meta(self, state: str) -> dict:
        return self._meta(state)

    # ══════════════ Summary ══════════════
    def summary(self, now: str = "") -> ControlSummary:
        return ControlSummary(
            timestamp=now, state_event_count=len(ledger.read_state_events()),
            event_count=len(ledger.read_events()), health_count=len(ledger.read_health()),
            metric_count=len(ledger.read_metrics()), alert_count=len(ledger.read_alerts()),
            report_count=len(ledger.read_reports()), artifact_count=len(ledger.read_artifacts()))
