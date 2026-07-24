"""Research Monitoring Engine (P23) — 연구 생태계 건강·품질·활동·무결성 관찰·기록. **관찰 전용, 동작 없음.**

**거래·에이전트 제어·워크플로 수정·권한 변경·전략 승인·모델 배포·자본 배분을 하지 않는다.** execution/broker/
live_portfolio/permission_control import·호출 없음. OBSERVE ≠ CONTROL · HEALTH ≠ APPROVAL. 결정적·불변·append-
only·이벤트 소싱. 상위 계층은 READ ONLY.
"""
from __future__ import annotations

from jarvis.research_monitoring import ledger
from jarvis.research_monitoring import models as M
from jarvis.research_monitoring.models import (
    GENESIS,
    ActivityEventRecord,
    AnomalyRecord,
    ArtifactRecord,
    HealthCheckRecord,
    IllegalSessionTransition,
    ImmutableSessionError,
    MonitoringMetricRecord,
    MonitoringSummary,
    ObservabilityReportRecord,
    ObservationRecord,
    SessionEventRecord,
    SnapshotRecord,
    UnknownEntityError,
    content_hash,
    input_digest,
    value_hash,
)

_DISCLAIMER = ("Research Monitoring & Observability 데이터 — OBSERVE ≠ CONTROL · HEALTH ≠ APPROVAL · "
               "HEALTH ≠ DEPLOYMENT PERMISSION. 연구 생태계 건강·품질·활동·무결성 관찰·기록 전용 — 거래·에이전트 제어·"
               "워크플로 수정·권한 변경·전략 승인·모델 배포·자본 배분 없음.")


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchMonitoringEngine:
    """연구 모니터링 엔진. 불변·append-only·이벤트 소싱·결정적. 실행/제어/배포/승인 권한 없음."""

    def _emit(self, exists_fn, head_fn, append_fn, rid, rec, *, commit) -> dict:
        rec = dict(rec)
        rec["record_hash"] = content_hash(rec)
        if commit and not exists_fn(rid):
            head = head_fn()
            append_fn(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def _artifact(self, atype, ref, parent, now, *, commit) -> ArtifactRecord:
        aid = M.artifact_id(atype, ref)
        rec = ArtifactRecord(artifact_id=aid, artifact_type=atype, ref_id=ref, parent_artifact=parent,
                             created_at=now, input_hash=input_digest(atype, ref),
                             previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.artifact_exists, ledger.artifacts_head, ledger.append_artifact,
                         aid, rec, commit=commit)
        return ArtifactRecord(**rec)

    # ══════════════ 모니터링 세션 생애주기(event-sourced) ══════════════
    def _session_event(self, sess, name, frm, to, note, now, *, commit):
        seq = len(ledger.session_events(sess))
        eid = M.session_event_id(sess, to, seq)
        rec = SessionEventRecord(session_event_id=eid, session_id=sess, name=name, from_state=frm,
                                 to_state=to, note=note, occurred_at=now,
                                 input_hash=input_digest(sess, to, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.session_event_exists, ledger.sessions_head,
                         ledger.append_session_event, eid, rec, commit=commit)
        return SessionEventRecord(**rec)

    def session_state(self, sess) -> str | None:
        evs = ledger.session_events(sess)
        return evs[-1].get("to_state") if evs else None

    def _require_session(self, sess) -> str:
        st = self.session_state(sess)
        if st is None:
            raise UnknownEntityError(f"미등록 세션 {sess}")
        return st

    def _session_meta(self, sess) -> dict:
        evs = ledger.session_events(sess)
        if not evs:
            raise UnknownEntityError(f"미등록 세션 {sess}")
        return {"name": evs[0].get("name"), "state": evs[-1].get("to_state")}

    def _session_transition(self, sess, to, note, now, *, commit):
        frm = self._require_session(sess)
        if not M.can_session_transition(frm, to):
            raise IllegalSessionTransition(f"세션 {sess} {frm}→{to} 불가")
        m = self._session_meta(sess)
        return self._session_event(sess, m["name"], frm, to, note, now, commit=commit)

    def create_session(self, name, now="", *, commit=False) -> SessionEventRecord:
        """모니터링 세션 생성(genesis CREATED)."""
        sess = M.session_id(name)
        evs = ledger.session_events(sess)
        if evs:
            return SessionEventRecord(**{k: v for k, v in evs[0].items()
                                         if k in SessionEventRecord.__dataclass_fields__})
        ev = self._session_event(sess, name, GENESIS, M.S_CREATED, "created", now, commit=commit)
        self._artifact(M.ART_SESSION, sess, "", now, commit=commit)
        return ev

    def start_collecting(self, sess, now="", *, commit=False):
        return self._session_transition(sess, M.S_COLLECTING, "collecting", now, commit=commit)

    def analyze_session(self, sess, now="", *, commit=False):
        return self._session_transition(sess, M.S_ANALYZED, "analyzed", now, commit=commit)

    def snapshot_session(self, sess, now="", *, commit=False):
        return self._session_transition(sess, M.S_SNAPSHOTTED, "snapshotted", now, commit=commit)

    def archive_session(self, sess, now="", *, commit=False):
        return self._session_transition(sess, M.S_ARCHIVED, "archived", now, commit=commit)

    # ══════════════ register_metric ══════════════
    def register_metric(self, metric_name, value, metric_type="GAUGE", source_layer="",
                        source_reference="", now="", *, commit=False) -> MonitoringMetricRecord:
        """모니터링 지표 기록(불변). **측정만.**"""
        if metric_type not in M.METRIC_TYPES:
            raise ValueError(f"미지원 metric_type {metric_type}")
        seq = len(ledger.metrics_by_name(metric_name))
        mid = M.metric_id(metric_name, source_reference, seq)
        rec = MonitoringMetricRecord(
            metric_id=mid, metric_name=metric_name, metric_type=metric_type, source_layer=source_layer,
            source_reference=source_reference, value=float(value),
            hash=value_hash(metric_name, value, source_reference), timestamp=now,
            input_hash=input_digest(metric_name, source_reference, seq),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.metric_exists, ledger.metrics_head, ledger.append_metric, mid, rec,
                         commit=commit)
        return MonitoringMetricRecord(**rec)

    # ══════════════ record_health_check ══════════════
    def record_health_check(self, component, score, metrics=None, now="",
                            *, commit=False) -> HealthCheckRecord:
        """구성요소 헬스 체크(불변). 점수→상태 결정적 라벨. **관찰만 — 승인 아님.**"""
        seq = len(ledger.component_health(component))
        hid = M.health_id(component, seq)
        status = M.classify_health(score)
        rec = HealthCheckRecord(health_id=hid, component=component, status=status,
                                metrics=dict(metrics or {}), score=float(score), checked_at=now,
                                input_hash=input_digest(component, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.health_exists, ledger.health_head, ledger.append_health, hid, rec,
                         commit=commit)
        return HealthCheckRecord(**rec)

    def evaluate_system_health(self, now="", *, commit=False) -> dict:
        """연구 시스템 종합 건강 = 구성요소별 최신 헬스 점수 집계(결정적). **상태만.**"""
        latest: dict = {}
        for h in ledger.read_health_checks():
            latest[h.get("component")] = h.get("score", 0.0)
        return M.aggregate_health(latest)

    # ══════════════ observe_pipeline / record_observation ══════════════
    def record_observation(self, source, event_type, metadata=None, now="",
                           *, commit=False) -> ObservationRecord:
        """관찰 기록(불변). **관찰만.**"""
        seq = len(ledger.read_observations())
        oid = M.observation_id(source, event_type, seq)
        rec = ObservationRecord(observation_id=oid, source=source, event_type=event_type,
                                metadata=dict(metadata or {}), timestamp=now,
                                input_hash=input_digest(source, event_type, seq),
                                previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.observation_exists, ledger.observations_head,
                         ledger.append_observation, oid, rec, commit=commit)
        return ObservationRecord(**rec)

    def record_activity(self, source_layer, activity_type, count=0, detail="", now="",
                        *, commit=False) -> ActivityEventRecord:
        """활동 이벤트 기록(불변). **추적만.**"""
        seq = len([r for r in ledger.read_activity_events()
                   if r.get("source_layer") == source_layer
                   and r.get("activity_type") == activity_type])
        aid = M.activity_event_id(source_layer, activity_type, seq)
        rec = ActivityEventRecord(activity_event_id=aid, source_layer=source_layer,
                                  activity_type=activity_type, count=int(count), detail=detail,
                                  timestamp=now, input_hash=input_digest(source_layer, activity_type, seq),
                                  previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.activity_exists, ledger.activity_head, ledger.append_activity, aid,
                         rec, commit=commit)
        return ActivityEventRecord(**rec)

    def observe_pipeline(self, source_layer, source_reference="", now="", *, commit=False) -> dict:
        """상위 계층(READ ONLY)에서 활동량을 관찰 → 관찰·활동·지표 기록. **읽기만·기록만.**"""
        count = ledger.source_count(source_layer)
        obs = self.record_observation(source_layer, "PIPELINE_OBSERVED",
                                      {"source_reference": source_reference, "count": count,
                                       "read_only": True}, now, commit=commit)
        act = self.record_activity(source_layer, "RECORD_COUNT", count, source_reference, now,
                                   commit=commit)
        metric = self.register_metric(f"activity:{source_layer}", count, "COUNTER", source_layer,
                                      source_reference, now, commit=commit)
        return {"observation": obs.to_dict(), "activity": act.to_dict(), "metric": metric.to_dict(),
                "count": count}

    # ══════════════ detect_anomaly (규칙 기반 탐지·기록만) ══════════════
    def detect_anomaly(self, rule, source_reference, severity="LOW", description="", now="",
                       *, commit=False) -> AnomalyRecord:
        """규칙 기반 이상 기록(불변). **탐지·기록만 — 자동 조치 없음(is_actionable=False).**"""
        if rule not in M.ANOMALY_RULES:
            raise ValueError(f"미지원 anomaly rule {rule}")
        if severity not in M.SEVERITIES:
            raise ValueError(f"미지원 severity {severity}")
        seq = len([r for r in ledger.read_anomalies()
                   if r.get("rule") == rule and r.get("source_reference") == source_reference])
        aid = M.anomaly_id(rule, source_reference, seq)
        rec = AnomalyRecord(anomaly_id=aid, rule=rule, source_reference=source_reference,
                            severity=severity, description=description, is_actionable=False,
                            detected_at=now, input_hash=input_digest(rule, source_reference, seq),
                            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.anomaly_exists, ledger.anomalies_head, ledger.append_anomaly, aid,
                         rec, commit=commit)
        return AnomalyRecord(**rec)

    def scan_missing_upstream(self, now="", *, commit=False) -> list:
        """모니터 대상 원장 부재(MISSING_UPSTREAM_LEDGER) 스캔 → 이상 기록. **탐지만.**"""
        out = []
        for layer in sorted(ledger.SOURCE_LAYERS):
            if not ledger.source_present(layer):
                out.append(self.detect_anomaly("MISSING_UPSTREAM_LEDGER", layer, "MEDIUM",
                                               f"upstream ledger absent: {layer}", now, commit=commit))
        return out

    # ══════════════ create_snapshot (결정적) ══════════════
    def create_snapshot(self, scope="SYSTEM", now="", *, commit=False) -> SnapshotRecord:
        """전체 모니터링 결정적 스냅샷. is_binding=False. **관찰 집계만 — 상태 변경 없음.**"""
        metrics = ledger.read_metrics()
        metrics_fp = value_hash([(m.get("metric_name"), m.get("value"), m.get("source_reference"))
                                 for m in metrics])
        state_fp = value_hash({"metrics": len(metrics), "health": len(ledger.read_health_checks()),
                               "anomalies": len(ledger.read_anomalies()),
                               "observations": len(ledger.read_observations()),
                               "sources": ledger.all_source_counts()})
        sid = M.snapshot_id(scope, now)
        rec = SnapshotRecord(
            snapshot_id=sid, scope=scope, metrics_hash=metrics_fp, system_state_hash=state_fp,
            metric_count=len(metrics), health_count=len(ledger.read_health_checks()),
            anomaly_count=len(ledger.read_anomalies()),
            observation_count=len(ledger.read_observations()), is_binding=False, created_at=now,
            input_hash=input_digest(scope, now), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.snapshot_exists, ledger.snapshots_head, ledger.append_snapshot, sid,
                         rec, commit=commit)
        self._artifact(M.ART_SNAPSHOT, sid, "", now, commit=commit)
        return SnapshotRecord(**rec)

    # ══════════════ generate_report ══════════════
    def generate_report(self, scope="SYSTEM", now="", *, commit=False) -> ObservabilityReportRecord:
        """관측성 리포트(건강·지표·이상·활동 집계). **is_binding=False, HEALTH ≠ APPROVAL.**"""
        health = self.evaluate_system_health(now)
        anomalies = ledger.read_anomalies()
        sev_dist: dict = {}
        for a in anomalies:
            sev_dist[a.get("severity")] = sev_dist.get(a.get("severity"), 0) + 1
        rid = M.report_id(scope, now)
        rec = ObservabilityReportRecord(
            report_id=rid, scope=scope, overall_health=health["status"], health_score=health["score"],
            metric_count=len(ledger.read_metrics()), health_check_count=len(ledger.read_health_checks()),
            anomaly_count=len(anomalies), anomaly_severity_distribution=dict(sorted(sev_dist.items())),
            activity_count=len(ledger.read_activity_events()), is_binding=False, disclaimer=_DISCLAIMER,
            created_at=now, input_hash=input_digest(scope, now), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.report_exists, ledger.reports_head, ledger.append_report, rid, rec,
                         commit=commit)
        self._artifact(M.ART_REPORT, rid, "", now, commit=commit)
        return ObservabilityReportRecord(**rec)

    # ══════════════ verify / 조회 / summary ══════════════
    def verify_integrity(self) -> dict:
        from jarvis.research_monitoring.verify import verify_chain
        return verify_chain()

    def list_sessions(self) -> list:
        return ledger.session_ids()

    def sessions_in_state(self, state) -> list:
        return sorted(s for s in ledger.session_ids() if self.session_state(s) == state)

    def summary(self, now="") -> MonitoringSummary:
        return MonitoringSummary(
            timestamp=now, session_event_count=len(ledger.read_session_events()),
            metric_count=len(ledger.read_metrics()), health_check_count=len(ledger.read_health_checks()),
            observation_count=len(ledger.read_observations()),
            activity_count=len(ledger.read_activity_events()), anomaly_count=len(ledger.read_anomalies()),
            snapshot_count=len(ledger.read_snapshots()), report_count=len(ledger.read_reports()),
            artifact_count=len(ledger.read_artifacts()))
