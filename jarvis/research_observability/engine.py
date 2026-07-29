"""Research Observability Engine (P10.18) — 연구 시스템 건강 관찰. **관찰·기록 전용, 조치 없음.**

P9.8~P10.17 연구 생태계를 READ ONLY 로 참조(파일 기반, import 없음)해 건강 기록·지표·모니터링 스냅샷·이상
관찰·활동 타임라인·품질 신호 이력·관측 리포트·모니터링 계보를 남긴다. **복구 실행·연구 객체 수정·strategy
변경·parameter 조정·workflow 재시작·배포 없음.** execution/broker/order/portfolio execution/capital
allocation/live trading/permission/risk controller import·호출 없음. OBSERVATION ≠ ACTION · DETECTION ≠
CORRECTION · WARNING ≠ INTERVENTION · MONITORING ≠ EXECUTION. 상위 파일은 읽기만. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.research_observability import ledger
from jarvis.research_observability.models import (
    ACKNOWLEDGED,
    ANOMALY_CATEGORIES,
    ARCHIVED,
    ART_ACTIVITY,
    ART_ANOMALY,
    ART_HEALTH,
    ART_LAYER,
    ART_METRIC,
    ART_QUALITY,
    ART_REPORT,
    ART_SNAPSHOT,
    CLEARED,
    GENESIS,
    HEALTH_STATES,
    METRIC_TYPES,
    OBSERVED,
    UNKNOWN,
    ActivityEvent,
    AnomalyEvent,
    HealthRecord,
    IllegalTransition,
    ImmutableHealthError,
    ImmutableMetricError,
    InvalidAnomalyCategory,
    InvalidHealthStatus,
    InvalidMetricType,
    MetricRecord,
    ObservabilityArtifact,
    ObservabilityReport,
    ObservabilitySummary,
    ObservationSnapshot,
    QualitySignal,
    UnknownAnomaly,
    activity_id as _activity_id,
    anomaly_event_id,
    anomaly_id as _anomaly_id,
    artifact_id as _artifact_id,
    can_transition_anomaly,
    content_hash,
    detect_cycle,
    health_id as _health_id,
    health_score,
    health_status,
    input_digest,
    metric_id as _metric_id,
    metrics_hash as _metrics_hash,
    quality_id as _quality_id,
    report_id as _report_id,
    snapshot_hash as _snapshot_hash,
    snapshot_id as _snapshot_id,
)

_DISCLAIMER = ("연구 관측 데이터 — OBSERVATION ≠ ACTION · DETECTION ≠ CORRECTION · WARNING ≠ "
               "INTERVENTION · MONITORING ≠ EXECUTION. 복구/수정/재시작/배포/실행 아님.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchObservabilityEngine:
    """연구 관측 엔진. 불변·append-only·결정적. 실행/복구/수정/재시작/배포 권한 없음."""

    # ── 아티팩트 계보(내부) ──
    def _record_artifact(self, artifact_type: str, ref_id: str, parent_artifact: str,
                         now: str, *, commit: bool) -> dict:
        aid = _artifact_id(artifact_type, ref_id)
        rec = ObservabilityArtifact(
            artifact_id=aid, artifact_type=artifact_type, ref_id=ref_id,
            parent_artifact=parent_artifact, created_at=now,
            input_hash=input_digest(artifact_type, ref_id), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def _ensure_layer_artifact(self, source_layer: str, now: str, *, commit: bool) -> str:
        """소스 레이어 계보 노드(루트) 보장. 반환: 레이어 아티팩트 id."""
        return self._record_artifact(ART_LAYER, source_layer, "", now, commit=commit)["artifact_id"]

    # ── Metric Registry (불변) ──
    def register_metric(self, metric_type: str, value: float, source_reference: str = "",
                       epoch: str = "", now: str = "", *, commit: bool = False) -> MetricRecord:
        """연구 지표를 불변 기록. metric_type 은 정의된 유형만 허용. **관찰·기록만.**"""
        if metric_type not in METRIC_TYPES:
            raise InvalidMetricType(f"미등록 지표 유형 {metric_type}")
        mid = _metric_id(metric_type, source_reference, epoch)
        existing = ledger.get_metric(mid)
        if existing is not None:
            if abs(float(existing.get("value", 0.0)) - round(float(value), 8)) > 1e-9:
                raise ImmutableMetricError(f"{mid} 지표 불변 — 변경 불가")
            return MetricRecord(**{k: v for k, v in existing.items()
                                   if k in MetricRecord.__dataclass_fields__})
        rec = MetricRecord(
            metric_id=mid, metric_type=metric_type, value=round(float(value), 8),
            source_reference=source_reference, epoch=epoch, timestamp=now, created_at=now,
            input_hash=input_digest(metric_type, source_reference, epoch),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.metric_exists(mid):
            head = ledger.metrics_head()
            ledger.append_metric(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = ""
        if source_reference:
            layer = source_reference.split(":")[0]
            if ledger.artifact_exists(_artifact_id(ART_LAYER, layer)):
                parent = _artifact_id(ART_LAYER, layer)
        self._record_artifact(ART_METRIC, mid, parent, now, commit=commit)
        return MetricRecord(**rec)

    # ── Health Registry (불변) ──
    def record_health(self, source_layer: str, status: str = "", metrics: dict | None = None,
                     epoch: str = "", now: str = "", *, commit: bool = False) -> HealthRecord:
        """연구 계층 건강을 불변 기록. status 미지정 시 지표로부터 파생. **관찰·기록만.**"""
        m = dict(metrics or {})
        st = status or (health_status(m) if m else UNKNOWN)
        if st not in HEALTH_STATES:
            raise InvalidHealthStatus(f"미등록 건강 상태 {st}")
        hid = _health_id(source_layer, epoch)
        mh = _metrics_hash(m)
        existing = ledger.get_health(hid)
        if existing is not None:
            if existing.get("metrics_hash") != mh or existing.get("status") != st:
                raise ImmutableHealthError(f"{hid} 건강 기록 불변 — 변경 불가")
            return HealthRecord(**{k: v for k, v in existing.items()
                                   if k in HealthRecord.__dataclass_fields__})
        self._ensure_layer_artifact(source_layer, now, commit=commit)
        rec = HealthRecord(
            health_id=hid, source_layer=source_layer, status=st, metrics=m, metrics_hash=mh,
            health_score=health_score(m), epoch=epoch, timestamp=now, created_at=now,
            input_hash=input_digest(source_layer, epoch), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.health_exists(hid):
            head = ledger.health_head()
            ledger.append_health(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_HEALTH, hid, _artifact_id(ART_LAYER, source_layer), now,
                              commit=commit)
        return HealthRecord(**rec)

    # ── Observation Snapshot (불변·결정적) ──
    def create_snapshot(self, name: str, epoch: str = "", collected_metrics: list | None = None,
                       health_summary: dict | None = None, now: str = "",
                       *, commit: bool = False) -> ObservationSnapshot:
        """수집된 지표·건강 요약을 결정적 스냅샷으로 고정. 동일 (name, epoch) → 동일 스냅샷."""
        cm = sorted(collected_metrics or [])
        hs = dict(health_summary or {})
        sid = _snapshot_id(name, epoch)
        existing = ledger.get_snapshot(sid)
        if existing is not None:
            return ObservationSnapshot(**{k: v for k, v in existing.items()
                                          if k in ObservationSnapshot.__dataclass_fields__})
        sh = _snapshot_hash(cm, hs)
        rec = ObservationSnapshot(
            snapshot_id=sid, name=name, epoch=epoch, collected_metrics=cm, health_summary=hs,
            metric_count=len(cm), snapshot_hash=sh, created_at=now,
            input_hash=input_digest(name, epoch), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.snapshot_exists(sid):
            head = ledger.snapshots_head()
            ledger.append_snapshot(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = ""
        for mref in cm:
            cand = _artifact_id(ART_METRIC, mref)
            if ledger.artifact_exists(cand):
                parent = cand
                break
        self._record_artifact(ART_SNAPSHOT, sid, parent, now, commit=commit)
        return ObservationSnapshot(**rec)

    # ── Anomaly Registry (이벤트 소싱, 관찰 상태 추적) ──
    def anomaly_state(self, anomaly_id: str) -> str:
        evs = ledger.anomaly_events_for(anomaly_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _anomaly_meta(self, anomaly_id: str) -> dict | None:
        evs = ledger.anomaly_events_for(anomaly_id)
        return evs[0] if evs else None

    def _emit_anomaly_event(self, meta: dict, frm: str, to: str, now: str,
                            *, commit: bool) -> dict:
        if not can_transition_anomaly(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(anomaly)")
        aid = meta["anomaly_id"]
        eid = anomaly_event_id(aid, frm, to)
        rec = AnomalyEvent(
            event_id=eid, anomaly_id=aid, source=meta["source"], category=meta["category"],
            severity=meta["severity"], evidence=meta["evidence"], from_state=frm, to_state=to,
            status=to, epoch=meta["epoch"], created_at=now, input_hash=input_digest(aid, frm, to),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.anomaly_event_exists(eid):
            head = ledger.anomalies_head()
            ledger.append_anomaly_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def record_anomaly(self, source: str, category: str, severity: str = "MEDIUM",
                      evidence: list | None = None, epoch: str = "", now: str = "",
                      *, commit: bool = False) -> AnomalyEvent:
        """이상 징후를 관찰 기록(OBSERVED). category 는 정의된 범주만 허용. **자동 대응 없음.**"""
        if category not in ANOMALY_CATEGORIES:
            raise InvalidAnomalyCategory(f"미등록 이상 범주 {category}")
        aid = _anomaly_id(source, category, epoch)
        existing = ledger.anomaly_events_for(aid)
        if existing:
            return AnomalyEvent(**existing[-1])
        meta = {"anomaly_id": aid, "source": source, "category": category, "severity": severity,
                "evidence": list(evidence or []), "epoch": epoch}
        rec = self._emit_anomaly_event(meta, "", OBSERVED, now, commit=commit)
        parent = ""
        for at in (ART_HEALTH, ART_METRIC, ART_SNAPSHOT, ART_LAYER):
            cand = _artifact_id(at, source)
            if ledger.artifact_exists(cand):
                parent = cand
                break
        self._record_artifact(ART_ANOMALY, aid, parent, now, commit=commit)
        return AnomalyEvent(**rec)

    def transition_anomaly(self, anomaly_id: str, to: str, now: str = "", *,
                           commit: bool = False) -> dict:
        meta = self._anomaly_meta(anomaly_id)
        if meta is None:
            raise UnknownAnomaly(f"미존재 이상 {anomaly_id}")
        return self._emit_anomaly_event(meta, self.anomaly_state(anomaly_id), to, now,
                                        commit=commit)

    def clear_anomaly(self, anomaly_id: str, now: str = "", *, commit: bool = False) -> dict:
        """OBSERVED→ACKNOWLEDGED→CLEARED. **관찰 상태 기록일 뿐 자동 조치/복구 없음.**"""
        meta = self._anomaly_meta(anomaly_id)
        if meta is None:
            raise UnknownAnomaly(f"미존재 이상 {anomaly_id}")
        cur = self.anomaly_state(anomaly_id)
        if cur == OBSERVED:
            self._emit_anomaly_event(meta, OBSERVED, ACKNOWLEDGED, now, commit=commit)
        self._emit_anomaly_event(meta, ACKNOWLEDGED, CLEARED, now, commit=commit)
        return {"anomaly_id": anomaly_id, "state": self.anomaly_state(anomaly_id)}

    # ── Activity Timeline ──
    def track_activity(self, scope: str, activity_type: str, reference: str, detail: str = "",
                      now: str = "", *, commit: bool = False) -> ActivityEvent:
        """연구 활동 이벤트를 타임라인에 기록. **관찰·기록만.**"""
        tid = _activity_id(scope, activity_type, reference)
        rec = ActivityEvent(
            activity_id=tid, scope=scope, activity_type=activity_type, reference=reference,
            detail=detail, timestamp=now, created_at=now,
            input_hash=input_digest(scope, activity_type, reference),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.activity_exists(tid):
            head = ledger.activity_head()
            ledger.append_activity(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_ACTIVITY, tid, "", now, commit=commit)
        return ActivityEvent(**rec)

    # ── Quality Signal History ──
    def record_quality_signal(self, source_reference: str, metric_type: str, value: float,
                            epoch: str = "", interpretation: str = "", now: str = "",
                            *, commit: bool = False) -> QualitySignal:
        """품질 신호를 이력에 기록(추세 관찰용). **관찰·기록만.**"""
        qid = _quality_id(source_reference + ":" + metric_type, epoch)
        rec = QualitySignal(
            quality_id=qid, source_reference=source_reference, metric_type=metric_type,
            value=round(float(value), 8), epoch=epoch, interpretation=interpretation,
            created_at=now, input_hash=input_digest(source_reference, metric_type, epoch),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.quality_exists(qid):
            head = ledger.quality_head()
            ledger.append_quality(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_QUALITY, qid, "", now, commit=commit)
        return QualitySignal(**rec)

    # ── 분석 프레임워크 ──
    def analyze(self, metrics: dict) -> dict:
        """건강 지표 → SCORE/STATUS. **OBSERVATION ≠ ACTION — 조치/복구 신호 아님.**"""
        return {"health_score": health_score(metrics), "health_status": health_status(metrics)}

    def failure_frequency(self) -> dict:
        """실패율 지표 집계(정보용)."""
        vals = [float(m.get("value", 0.0)) for m in ledger.read_metrics()
                if m.get("metric_type") == "failure_rate"]
        avg = round(sum(vals) / len(vals), 8) if vals else 0.0
        return {"samples": len(vals), "avg_failure_rate": avg}

    def quality_trend(self, source_reference: str) -> dict:
        """소스별 품질 신호 추세(첫→마지막 델타, 정보용)."""
        rows = ledger.quality_for(source_reference)
        if len(rows) < 2:
            return {"source_reference": source_reference, "samples": len(rows), "delta": 0.0}
        delta = round(float(rows[-1].get("value", 0.0)) - float(rows[0].get("value", 0.0)), 8)
        return {"source_reference": source_reference, "samples": len(rows), "delta": delta,
                "note": "서술적 추세 — 자동 조치 없음"}

    def degradation_indicators(self) -> list:
        """열화 신호 목록(DEGRADED 건강 + HIGH/CRITICAL 미해소 이상). **정보용 — 개입 없음.**"""
        out: list = []
        for h in ledger.read_health():
            if h.get("status") == "DEGRADED":
                out.append(f"degraded_health:{h.get('source_layer')}")
        for a in ledger.distinct_anomalies():
            st = self.anomaly_state(a.get("anomaly_id"))
            if a.get("severity") in ("HIGH", "CRITICAL") and st not in ("CLEARED", "ARCHIVED"):
                out.append(f"open_anomaly:{a.get('category')}:{a.get('source')}")
        return sorted(set(out))

    # ── 계보 검증 ──
    def verify_lineage(self) -> dict:
        """모니터링 계보(아티팩트 parent 체인): dangling parent·순환 탐지. **읽기 전용.**"""
        issues: list = []
        arts = ledger.read_artifacts()
        ids = {a.get("artifact_id") for a in arts}
        edges: list = []
        for a in arts:
            parent = a.get("parent_artifact")
            if parent:
                if parent not in ids:
                    issues.append(f"dangling:{a.get('artifact_id')}->{parent}")
                edges.append((a.get("artifact_id"), parent))
        cyc = detect_cycle(edges)
        if cyc:
            issues.append("lineage_cycle:" + "->".join(cyc))
        return {"ok": not issues, "issues": sorted(set(issues)), "n_artifacts": len(arts)}

    def trace_lineage(self, artifact_ref: str) -> list:
        by_id = {a.get("artifact_id"): a for a in ledger.read_artifacts()}
        out: list = []
        seen: set = set()
        cur = by_id.get(artifact_ref)
        while cur:
            parent = cur.get("parent_artifact")
            if not parent or parent in seen:
                break
            seen.add(parent)
            out.append(parent)
            cur = by_id.get(parent)
        return out

    # ── Observability Report ──
    def generate_report(self, scope: str = "GLOBAL", metrics: dict | None = None, now: str = "",
                       *, commit: bool = False) -> ObservabilityReport:
        m = dict(metrics or {})
        mets = ledger.read_metrics()
        mt_dist: dict = {}
        for mr in mets:
            mt_dist[mr.get("metric_type")] = mt_dist.get(mr.get("metric_type"), 0) + 1
        healths = ledger.read_health()
        hs_dist: dict = {}
        for h in healths:
            hs_dist[h.get("status")] = hs_dist.get(h.get("status"), 0) + 1
        anoms = ledger.distinct_anomalies()
        sev_dist: dict = {}
        ast_dist: dict = {}
        for a in anoms:
            sev_dist[a.get("severity")] = sev_dist.get(a.get("severity"), 0) + 1
            st = self.anomaly_state(a.get("anomaly_id"))
            ast_dist[st] = ast_dist.get(st, 0) + 1
        rid = _report_id(scope)
        rec = ObservabilityReport(
            report_id=rid, scope=scope, health_score=health_score(m), health_status=health_status(m),
            metric_count=len(mets), metric_type_distribution=dict(sorted(mt_dist.items())),
            health_record_count=len(healths),
            health_status_distribution=dict(sorted(hs_dist.items())),
            snapshot_count=len(ledger.read_snapshots()), anomaly_count=len(anoms),
            anomaly_severity_distribution=dict(sorted(sev_dist.items())),
            anomaly_state_distribution=dict(sorted(ast_dist.items())),
            activity_count=len(ledger.read_activity()),
            quality_signal_count=len(ledger.read_quality()),
            degradation_indicators=self.degradation_indicators(), metrics=m,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(scope),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_REPORT, rid, "", now, commit=commit)
        return ObservabilityReport(**rec)

    # ── 상위 레이어 READ ONLY 조회 ──
    def list_source_objects(self, layer: str, limit: int = 0) -> list:
        spec = ledger.SOURCE_LEDGERS.get(layer)
        if not spec:
            return []
        filename, id_field = spec
        seen: set = set()
        out: list = []
        for r in ledger.read_source(filename):
            ref = r.get(id_field)
            if ref and ref not in seen:
                seen.add(ref)
                out.append(f"{layer}:{ref}")
            if limit and len(out) >= limit:
                break
        return out

    # ── Summary ──
    def summary(self, now: str = "") -> ObservabilitySummary:
        mets = ledger.read_metrics()
        mt_dist: dict = {}
        for mr in mets:
            mt_dist[mr.get("metric_type")] = mt_dist.get(mr.get("metric_type"), 0) + 1
        healths = ledger.read_health()
        hs_dist: dict = {}
        for h in healths:
            hs_dist[h.get("status")] = hs_dist.get(h.get("status"), 0) + 1
        anoms = ledger.distinct_anomalies()
        ast_dist: dict = {}
        for a in anoms:
            st = self.anomaly_state(a.get("anomaly_id"))
            ast_dist[st] = ast_dist.get(st, 0) + 1
        return ObservabilitySummary(
            timestamp=now, metric_count=len(mets),
            metric_type_distribution=dict(sorted(mt_dist.items())),
            health_record_count=len(healths),
            health_status_distribution=dict(sorted(hs_dist.items())),
            snapshot_count=len(ledger.read_snapshots()), anomaly_count=len(anoms),
            anomaly_state_distribution=dict(sorted(ast_dist.items())),
            activity_count=len(ledger.read_activity()),
            quality_signal_count=len(ledger.read_quality()),
            report_count=len(ledger.read_reports()))
