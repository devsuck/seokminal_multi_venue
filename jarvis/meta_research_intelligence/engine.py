"""Meta Research Intelligence Engine (P30) — 연구 과정 자체를 관찰·분석. **관찰 전용, 동작 없음.**

**자동 최적화·실행·배포·거래를 하지 않는다.** execution/broker/live_trading/portfolio_execution import·호출 없음.
OBSERVATION ≠ OPTIMIZATION · META ≠ EXECUTION · OPPORTUNITY ≠ APPLIED. 결정적·불변·append-only. 상위 계층은 READ ONLY.
"""
from __future__ import annotations

from jarvis.meta_research_intelligence import ledger
from jarvis.meta_research_intelligence import models as M
from jarvis.meta_research_intelligence.models import (
    GENESIS,
    ArtifactRecord,
    MetaMetricRecord,
    MetaObservationRecord,
    MetaReportRecord,
    MetaSummary,
    OptimizationOpportunityRecord,
    QualityRecord,
    content_hash,
    input_digest,
    ratio,
)

_DISCLAIMER = ("Meta Research Intelligence 데이터 — OBSERVATION ≠ OPTIMIZATION · META ≠ EXECUTION · "
               "OPPORTUNITY ≠ APPLIED. 연구 과정(효율·검증 품질·실패 빈도·속도·지식 재사용) 관찰·기록 전용 — 자동 최적화·"
               "실행·배포·거래·자본 배분 없음.")


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class MetaResearchIntelligenceEngine:
    """메타 연구 지능 엔진. 불변·append-only·결정적. 자동 최적화/실행/배포/거래 권한 없음."""

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

    # ══════════════ record_meta_metric ══════════════
    def record_meta_metric(self, metric_name, value, unit="ratio", dimension="", source_reference="",
                           now="", *, commit=False) -> MetaMetricRecord:
        """메타 지표 기록(불변, is_observation=True). **관찰만.**"""
        seq = len(ledger.metrics_by_name(metric_name))
        mid = M.metric_id(metric_name, seq)
        rec = MetaMetricRecord(
            metric_id=mid, metric_name=metric_name, value=float(value), unit=unit,
            dimension=dimension, source_reference=source_reference, is_observation=True,
            timestamp=now, input_hash=input_digest(metric_name, seq),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.metric_exists, ledger.metrics_head, ledger.append_metric, mid, rec,
                         commit=commit)
        self._artifact(M.ART_METRIC, mid, "", now, commit=commit)
        return MetaMetricRecord(**rec)

    # ══════════════ compute_meta_metrics (READ ONLY, 결정적) ══════════════
    def compute_meta_metrics(self, now="", *, commit=False) -> dict:
        """연구 과정 5개 메타 지표를 상위 계층(READ ONLY)에서 결정적으로 산출. **관찰만 — 자동 최적화 없음.**"""
        cycles = ledger.source_records("autonomous_research")
        completed = sum(1 for c in cycles if c.get("to_state") in ("COMPLETED", "ARCHIVED"))
        checks = ledger.source_records("reliability_checks")
        passed = sum(1 for c in checks if c.get("result") == "PASS")
        incidents = ledger.source_count("reliability_incidents")
        anomalies = ledger.source_count("monitoring")
        retrievals = ledger.source_count("memory_retrievals")
        candidates = ledger.source_count("strategy_generation")
        insights = ledger.source_count("insight_intelligence")
        values = {
            "research_efficiency": ratio(completed, len(cycles)) if cycles else 0.0,
            "validation_quality": ratio(passed, len(checks)) if checks else 0.0,
            "failure_frequency": float(incidents + anomalies),
            "research_velocity": float(candidates + insights),
            "knowledge_reuse": float(retrievals),
        }
        units = {"research_efficiency": "ratio", "validation_quality": "ratio",
                 "failure_frequency": "count", "research_velocity": "count",
                 "knowledge_reuse": "count"}
        out = {}
        for name in M.META_METRIC_NAMES:
            rec = self.record_meta_metric(name, values[name], units[name], name, "meta", now,
                                          commit=commit)
            out[name] = rec.value
        return out

    # ══════════════ assess_quality ══════════════
    def assess_quality(self, subject, dimension, score, assessment="", now="",
                       *, commit=False) -> QualityRecord:
        """연구 품질 평가(불변). **평가·기록만.**"""
        if dimension not in M.QUALITY_DIMENSIONS:
            raise ValueError(f"미지원 dimension {dimension}")
        qid = M.quality_id(subject, dimension)
        rec = QualityRecord(quality_id=qid, subject=subject, dimension=dimension,
                            score=M.clamp01(score), grade=M.classify_quality(score),
                            assessment=assessment, created_at=now,
                            input_hash=input_digest(subject, dimension),
                            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.quality_exists, ledger.quality_head, ledger.append_quality, qid,
                         rec, commit=commit)
        self._artifact(M.ART_QUALITY, qid, "", now, commit=commit)
        return QualityRecord(**rec)

    # ══════════════ detect_opportunity (기록만, 적용 없음) ══════════════
    def detect_opportunity(self, area, description, evidence=None, now="",
                           *, commit=False) -> OptimizationOpportunityRecord:
        """최적화 기회 탐지·기록(불변, is_applied=False). **탐지·기록만 — 자동 적용/최적화 없음.**"""
        if area not in M.OPPORTUNITY_AREAS:
            raise ValueError(f"미지원 area {area}")
        ev = dict(evidence or {})
        score = M.opportunity_priority(ev.get("evidence_count", 0))
        oid = M.opportunity_id(area, description)
        rec = OptimizationOpportunityRecord(
            opportunity_id=oid, area=area, description=description, evidence=ev, priority_score=score,
            is_applied=False, created_at=now, input_hash=input_digest(area, description),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.opportunity_exists, ledger.opportunities_head,
                         ledger.append_opportunity, oid, rec, commit=commit)
        self._artifact(M.ART_OPPORTUNITY, oid, "", now, commit=commit)
        return OptimizationOpportunityRecord(**rec)

    # ══════════════ record_observation ══════════════
    def record_observation(self, aspect, finding, evidence=None, now="",
                           *, commit=False) -> MetaObservationRecord:
        """메타 관찰 기록(불변). **관찰·기록만.**"""
        if aspect not in M.OBSERVATION_ASPECTS:
            raise ValueError(f"미지원 aspect {aspect}")
        oid = M.observation_id(aspect, finding)
        rec = MetaObservationRecord(observation_id=oid, aspect=aspect, finding=finding,
                                    evidence=dict(evidence or {}), created_at=now,
                                    input_hash=input_digest(aspect, finding),
                                    previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.observation_exists, ledger.observations_head,
                         ledger.append_observation, oid, rec, commit=commit)
        return MetaObservationRecord(**rec)

    # ══════════════ generate_report ══════════════
    def generate_report(self, scope="SYSTEM", now="", *, commit=False) -> MetaReportRecord:
        """메타 리포트(지표·품질·기회·관찰 집계 + 메타 지표). **is_binding=False, OBSERVATION ≠ OPTIMIZATION.**"""
        metrics = self.compute_meta_metrics(now)
        quality = ledger.read_quality_records()
        q_dist: dict = {}
        for q in quality:
            q_dist[q.get("grade")] = q_dist.get(q.get("grade"), 0) + 1
        area_dist: dict = {}
        for o in ledger.read_opportunities():
            area_dist[o.get("area")] = area_dist.get(o.get("area"), 0) + 1
        rid = M.report_id(scope, now)
        rec = MetaReportRecord(
            report_id=rid, scope=scope, metric_count=len(ledger.read_meta_metrics()),
            quality_count=len(quality), opportunity_count=len(ledger.read_opportunities()),
            observation_count=len(ledger.read_observations()), meta_metrics=metrics,
            quality_distribution=dict(sorted(q_dist.items())),
            area_distribution=dict(sorted(area_dist.items())), is_binding=False,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(scope, now),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.report_exists, ledger.reports_head, ledger.append_report, rid, rec,
                         commit=commit)
        self._artifact(M.ART_REPORT, rid, "", now, commit=commit)
        return MetaReportRecord(**rec)

    def verify_integrity(self) -> dict:
        from jarvis.meta_research_intelligence.verify import verify_chain
        return verify_chain()

    def summary(self, now="") -> MetaSummary:
        return MetaSummary(
            timestamp=now, metric_count=len(ledger.read_meta_metrics()),
            quality_count=len(ledger.read_quality_records()),
            opportunity_count=len(ledger.read_opportunities()),
            observation_count=len(ledger.read_observations()),
            report_count=len(ledger.read_reports()), artifact_count=len(ledger.read_artifacts()))
