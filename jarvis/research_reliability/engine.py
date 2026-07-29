"""Research Reliability Engine (P24) — 연구 인프라 신뢰성 기록·검증·분석. **기록 전용, 동작 없음.**

**실행 복구 시스템이 아니다.** 거래 시스템 재시작·프로덕션 수정·자동 배포·권한 변경·전략 실행·모델 자동 수정·파일 자동
변경·설정 자동 변경을 하지 않는다. execution/broker/live_trading/portfolio_execution import·호출 없음. RECORD ≠
REPAIR · INCIDENT ≠ EXECUTION · RECOVERY = RESEARCH-PROCESS RECOVERY. 결정적·불변·append-only·이벤트 소싱.
상위 계층(P10~P23)은 READ ONLY.
"""
from __future__ import annotations

from jarvis.research_reliability import ledger
from jarvis.research_reliability import models as M
from jarvis.research_reliability.models import (
    GENESIS,
    ArtifactRecord,
    IllegalIncidentTransition,
    IllegalPostmortemTransition,
    IncidentEventRecord,
    IntegrityCheckRecord,
    PostmortemEventRecord,
    RecoveryEventRecord,
    RecoveryPlanRecord,
    ReliabilityMetricRecord,
    ReliabilityReportRecord,
    ReliabilitySummary,
    ReviewerRequired,
    UnknownEntityError,
    content_hash,
    input_digest,
    ratio,
    value_hash,
)

_DISCLAIMER = ("Research Reliability Engineering 데이터 — RECORD ≠ REPAIR · INCIDENT ≠ EXECUTION · "
               "RECOVERY = RESEARCH-PROCESS RECOVERY(≠ LIVE SYSTEM RECOVERY). 연구 신뢰성 기록·검증·분석 전용 — "
               "거래 시스템 재시작·프로덕션 수정·자동 배포·권한 변경·전략 실행·모델 자동 수정 없음.")


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchReliabilityEngine:
    """연구 신뢰성 엔진. 불변·append-only·이벤트 소싱·결정적. 실행/복구실행/배포/승인 권한 없음."""

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

    # ══════════════ 장애 생애주기(event-sourced) ══════════════
    def _incident_event(self, inc, source_layer, severity, category, description, frm, to, note,
                        now, *, commit):
        seq = len(ledger.incident_events(inc))
        eid = M.incident_event_id(inc, to, seq)
        rec = IncidentEventRecord(
            incident_event_id=eid, incident_id=inc, source_layer=source_layer, severity=severity,
            category=category, description=description, from_state=frm, to_state=to, note=note,
            detected_at=now, input_hash=input_digest(inc, to, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.incident_event_exists, ledger.incidents_head,
                         ledger.append_incident_event, eid, rec, commit=commit)
        return IncidentEventRecord(**rec)

    def incident_state(self, inc) -> str | None:
        evs = ledger.incident_events(inc)
        return evs[-1].get("to_state") if evs else None

    def _incident_meta(self, inc) -> dict:
        evs = ledger.incident_events(inc)
        if not evs:
            raise UnknownEntityError(f"미등록 장애 {inc}")
        g = evs[0]
        return {"source_layer": g.get("source_layer"), "severity": g.get("severity"),
                "category": g.get("category"), "description": g.get("description"),
                "state": evs[-1].get("to_state")}

    def _incident_transition(self, inc, to, note, now, *, commit):
        m = self._incident_meta(inc)
        frm = m["state"]
        if not M.can_incident_transition(frm, to):
            raise IllegalIncidentTransition(f"장애 {inc} {frm}→{to} 불가")
        return self._incident_event(inc, m["source_layer"], m["severity"], m["category"],
                                    m["description"], frm, to, note, now, commit=commit)

    def register_incident(self, source_layer, category, description, severity="MEDIUM", now="",
                          *, commit=False) -> IncidentEventRecord:
        """장애 기록(genesis OPEN, 이벤트 소싱). **기록만 — 복구 실행 없음.**"""
        if category not in M.INCIDENT_CATEGORIES:
            raise ValueError(f"미지원 category {category}")
        if severity not in M.SEVERITIES:
            raise ValueError(f"미지원 severity {severity}")
        inc = M.incident_id(source_layer, category, description)
        evs = ledger.incident_events(inc)
        if evs:
            return IncidentEventRecord(**{k: v for k, v in evs[0].items()
                                          if k in IncidentEventRecord.__dataclass_fields__})
        ev = self._incident_event(inc, source_layer, severity, category, description, GENESIS,
                                  M.I_OPEN, "opened", now, commit=commit)
        self._artifact(M.ART_INCIDENT, inc, "", now, commit=commit)
        return ev

    def analyze_incident(self, inc, note="analyzing", now="", *, commit=False):
        return self._incident_transition(inc, M.I_ANALYZING, note, now, commit=commit)

    def mark_recovery_planned(self, inc, note="recovery planned", now="", *, commit=False):
        return self._incident_transition(inc, M.I_RECOVERY_PLANNED, note, now, commit=commit)

    def resolve_incident(self, inc, note="resolved", now="", *, commit=False):
        return self._incident_transition(inc, M.I_RESOLVED, note, now, commit=commit)

    def archive_incident(self, inc, note="archived", now="", *, commit=False):
        return self._incident_transition(inc, M.I_ARCHIVED, note, now, commit=commit)

    # ══════════════ create_recovery_plan (자동 실행 없음) ══════════════
    def create_recovery_plan(self, inc, steps, owner, now="", *, commit=False) -> RecoveryPlanRecord:
        """복구 계획 기록(불변). **자동 실행 없음(auto_execute=False) — 사람이 수행.**"""
        self._incident_meta(inc)  # 존재 검증
        seq = len(ledger.plans_for(inc))
        pid = M.plan_id(inc, seq)
        rec = RecoveryPlanRecord(
            plan_id=pid, incident_id=inc, steps=list(steps), owner=owner, auto_execute=False,
            created_at=now, input_hash=input_digest(inc, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.plan_exists, ledger.plans_head, ledger.append_plan, pid, rec,
                         commit=commit)
        self._artifact(M.ART_PLAN, pid, M.artifact_id(M.ART_INCIDENT, inc), now, commit=commit)
        return RecoveryPlanRecord(**rec)

    # ══════════════ record_recovery_event ══════════════
    def record_recovery_event(self, inc, action, result="RECORDED", detail="", now="",
                              *, commit=False) -> RecoveryEventRecord:
        """복구 시도 기록(불변). result ∈ {RECORDED, VERIFIED, FAILED}. **기록만 — 실행 없음.**"""
        self._incident_meta(inc)  # 존재 검증
        if result not in M.RECOVERY_RESULTS:
            raise ValueError(f"미지원 recovery result {result}")
        seq = len(ledger.recovery_events_for(inc))
        eid = M.recovery_event_id(inc, action, seq)
        rec = RecoveryEventRecord(
            event_id=eid, incident_id=inc, action=action, result=result, detail=detail, timestamp=now,
            input_hash=input_digest(inc, action, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.recovery_event_exists, ledger.recovery_events_head,
                         ledger.append_recovery_event, eid, rec, commit=commit)
        return RecoveryEventRecord(**rec)

    # ══════════════ run_integrity_check ══════════════
    def run_integrity_check(self, target_layer, check_type, result="PASS", evidence=None, now="",
                            *, commit=False) -> IntegrityCheckRecord:
        """무결성 검사 기록(불변). type ∈ HASH/LINEAGE/SCHEMA/REPLAY. **검증·기록만.**"""
        if check_type not in M.INTEGRITY_CHECK_TYPES:
            raise ValueError(f"미지원 check_type {check_type}")
        if result not in M.CHECK_RESULTS:
            raise ValueError(f"미지원 check result {result}")
        seq = len([r for r in ledger.read_integrity_checks()
                   if r.get("target_layer") == target_layer and r.get("check_type") == check_type])
        cid = M.integrity_check_id(target_layer, check_type, seq)
        rec = IntegrityCheckRecord(
            check_id=cid, target_layer=target_layer, check_type=check_type, result=result,
            evidence=dict(evidence or {}), checked_at=now,
            input_hash=input_digest(target_layer, check_type, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.check_exists, ledger.checks_head, ledger.append_check, cid, rec,
                         commit=commit)
        return IntegrityCheckRecord(**rec)

    def scan_upstream_integrity(self, now="", *, commit=False) -> list:
        """상위 원장 존재를 READ ONLY 스캔 → 부재는 FAIL(HASH_CHECK) 기록. **탐지·기록만.**"""
        out = []
        for layer in sorted(ledger.SOURCE_LAYERS):
            present = ledger.source_present(layer)
            out.append(self.run_integrity_check(
                layer, "HASH_CHECK", "PASS" if present else "FAIL",
                {"present": present, "count": ledger.source_count(layer), "read_only": True},
                now, commit=commit))
        return out

    # ══════════════ calculate_reliability_metrics (관찰만) ══════════════
    def _resolution_distance(self) -> list:
        """장애별 OPEN→RESOLVED 이벤트 거리(결정적 관찰 프록시, wall-clock 아님)."""
        dists = []
        for inc in ledger.incident_ids():
            evs = ledger.incident_events(inc)
            resolved_at = next((i for i, e in enumerate(evs)
                                if e.get("to_state") == M.I_RESOLVED), None)
            if resolved_at is not None:
                dists.append(resolved_at)  # genesis(OPEN)=0 부터의 전이 수
        return dists

    def calculate_reliability_metrics(self, now="", *, commit=False) -> dict:
        """6개 신뢰성 지표 산출(결정적·관찰만). **자동 결정 없음.** commit 시 지표 원장에 기록."""
        incidents = ledger.incident_ids()
        checks = ledger.read_integrity_checks()
        failed_checks = [c for c in checks if c.get("result") == "FAIL"]
        states = {inc: self.incident_state(inc) for inc in incidents}
        resolved = [inc for inc, st in states.items() if st in (M.I_RESOLVED, M.I_ARCHIVED)]
        dists = self._resolution_distance()
        values = {
            "incident_frequency": float(len(incidents)),
            "mean_resolution_time": round(sum(dists) / len(dists), 6) if dists else 0.0,
            "failed_validation_rate": ratio(len(failed_checks), len(checks)),
            "ledger_integrity_score": self._ledger_integrity_score(),
            "lineage_health_score": self._lineage_health_score(),
            "research_availability_score": (ratio(len(resolved), len(incidents))
                                            if incidents else 1.0),
        }
        units = {"incident_frequency": "count", "mean_resolution_time": "transitions",
                 "failed_validation_rate": "ratio", "ledger_integrity_score": "ratio",
                 "lineage_health_score": "ratio", "research_availability_score": "ratio"}
        out = {}
        for name in M.RELIABILITY_METRICS:
            rec = self._record_metric(name, values[name], units[name], now, commit=commit)
            out[name] = rec.value
        return out

    def _record_metric(self, metric_name, value, unit, now, *, commit) -> ReliabilityMetricRecord:
        seq = len([r for r in ledger.read_reliability_metrics()
                   if r.get("metric_name") == metric_name])
        mid = M.reliability_metric_id(metric_name, seq)
        rec = ReliabilityMetricRecord(
            metric_id=mid, metric_name=metric_name, value=float(value), unit=unit,
            source_reference="reliability", is_observation=True, timestamp=now,
            input_hash=input_digest(metric_name, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.metric_exists, ledger.metrics_head, ledger.append_metric, mid, rec,
                         commit=commit)
        return ReliabilityMetricRecord(**rec)

    def _ledger_integrity_score(self) -> float:
        from jarvis.research_reliability.verify import verify_ledger
        total = len(ledger.ALL_LEDGERS)
        intact = sum(1 for which in ledger.ALL_LEDGERS if verify_ledger(which)["ok"])
        return ratio(intact, total)

    def _lineage_health_score(self) -> float:
        from jarvis.research_reliability.verify import lineage_integrity
        arts = ledger.read_artifacts()
        issues = len(lineage_integrity()["issues"])
        if not arts:
            return 1.0
        return round(max(0.0, 1.0 - issues / len(arts)), 6)

    # ══════════════ 포스트모템 생애주기(event-sourced, 사람 검토 필수) ══════════════
    def _postmortem_event(self, pm, inc, root_cause, impact, lesson, frm, to, reviewer, note,
                          now, *, commit):
        seq = len(ledger.postmortem_events(pm))
        eid = M.postmortem_event_id(pm, to, seq)
        rec = PostmortemEventRecord(
            postmortem_event_id=eid, postmortem_id=pm, incident_id=inc, root_cause=root_cause,
            impact=impact, lesson=lesson, from_state=frm, to_state=to, reviewer=reviewer, note=note,
            created_at=now, input_hash=input_digest(pm, to, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.postmortem_event_exists, ledger.postmortems_head,
                         ledger.append_postmortem_event, eid, rec, commit=commit)
        return PostmortemEventRecord(**rec)

    def postmortem_state(self, pm) -> str | None:
        evs = ledger.postmortem_events(pm)
        return evs[-1].get("to_state") if evs else None

    def _postmortem_meta(self, pm) -> dict:
        evs = ledger.postmortem_events(pm)
        if not evs:
            raise UnknownEntityError(f"미등록 포스트모템 {pm}")
        g = evs[0]
        return {"incident_id": g.get("incident_id"), "root_cause": g.get("root_cause"),
                "impact": g.get("impact"), "lesson": g.get("lesson"),
                "state": evs[-1].get("to_state")}

    def create_postmortem(self, inc, root_cause, impact, lesson, now="",
                          *, commit=False) -> PostmortemEventRecord:
        """포스트모템 기록(genesis DRAFT, 이벤트 소싱). **기록만 — 자동 확정 없음.**"""
        self._incident_meta(inc)  # 존재 검증
        pm = M.postmortem_id(inc)
        evs = ledger.postmortem_events(pm)
        if evs:
            return PostmortemEventRecord(**{k: v for k, v in evs[0].items()
                                            if k in PostmortemEventRecord.__dataclass_fields__})
        ev = self._postmortem_event(pm, inc, root_cause, impact, lesson, GENESIS, M.P_DRAFT, "", "draft",
                                    now, commit=commit)
        self._artifact(M.ART_POSTMORTEM, pm, M.artifact_id(M.ART_INCIDENT, inc), now, commit=commit)
        return ev

    def review_postmortem(self, pm, reviewer, note="reviewed", now="", *, commit=False):
        """포스트모템 검토(DRAFT→REVIEWED). 검토자 필수."""
        if not reviewer:
            raise ReviewerRequired("포스트모템 검토는 reviewer 필수")
        m = self._postmortem_meta(pm)
        frm = m["state"]
        if not M.can_postmortem_transition(frm, M.P_REVIEWED):
            raise IllegalPostmortemTransition(f"포스트모템 {pm} {frm}→REVIEWED 불가")
        return self._postmortem_event(pm, m["incident_id"], m["root_cause"], m["impact"], m["lesson"],
                                      frm, M.P_REVIEWED, reviewer, note, now, commit=commit)

    def record_postmortem(self, pm, reviewer, note="recorded", now="", *, commit=False):
        """포스트모템 확정(REVIEWED→RECORDED). **사람 검토(reviewer) 필수 — 자동 확정 금지.**"""
        if not reviewer:
            raise ReviewerRequired("포스트모템 확정은 reviewer 필수")
        m = self._postmortem_meta(pm)
        frm = m["state"]
        if not M.can_postmortem_transition(frm, M.P_RECORDED):
            raise IllegalPostmortemTransition(f"포스트모템 {pm} {frm}→RECORDED 불가")
        return self._postmortem_event(pm, m["incident_id"], m["root_cause"], m["impact"], m["lesson"],
                                      frm, M.P_RECORDED, reviewer, note, now, commit=commit)

    # ══════════════ generate_report ══════════════
    def generate_report(self, scope="SYSTEM", now="", *, commit=False) -> ReliabilityReportRecord:
        """신뢰성 리포트(장애·복구·무결성·포스트모템·지표 집계). **is_binding=False, RECORD ≠ REPAIR.**"""
        incidents = ledger.incident_ids()
        states = {inc: self.incident_state(inc) for inc in incidents}
        metas = {inc: self._incident_meta(inc) for inc in incidents}
        checks = ledger.read_integrity_checks()
        sev_dist: dict = {}
        cat_dist: dict = {}
        for inc in incidents:
            sev_dist[metas[inc]["severity"]] = sev_dist.get(metas[inc]["severity"], 0) + 1
            cat_dist[metas[inc]["category"]] = cat_dist.get(metas[inc]["category"], 0) + 1
        metrics = self.calculate_reliability_metrics(now)
        rid = M.report_id(scope, now)
        rec = ReliabilityReportRecord(
            report_id=rid, scope=scope, incident_count=len(incidents),
            open_incident_count=sum(1 for st in states.values()
                                    if st in (M.I_OPEN, M.I_ANALYZING, M.I_RECOVERY_PLANNED)),
            resolved_incident_count=sum(1 for st in states.values()
                                        if st in (M.I_RESOLVED, M.I_ARCHIVED)),
            recovery_plan_count=len(ledger.read_recovery_plans()),
            recovery_event_count=len(ledger.read_recovery_events()),
            integrity_check_count=len(checks),
            failed_check_count=sum(1 for c in checks if c.get("result") == "FAIL"),
            postmortem_count=len(ledger.postmortem_ids()),
            severity_distribution=dict(sorted(sev_dist.items())),
            category_distribution=dict(sorted(cat_dist.items())),
            reliability_metrics=metrics, is_binding=False, disclaimer=_DISCLAIMER, created_at=now,
            input_hash=input_digest(scope, now), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.report_exists, ledger.reports_head, ledger.append_report, rid, rec,
                         commit=commit)
        self._artifact(M.ART_REPORT, rid, "", now, commit=commit)
        return ReliabilityReportRecord(**rec)

    # ══════════════ verify / 조회 / summary ══════════════
    def verify_integrity(self) -> dict:
        from jarvis.research_reliability.verify import verify_chain
        return verify_chain()

    def list_incidents(self) -> list:
        return ledger.incident_ids()

    def incidents_in_state(self, state) -> list:
        return sorted(i for i in ledger.incident_ids() if self.incident_state(i) == state)

    def list_postmortems(self) -> list:
        return ledger.postmortem_ids()

    def summary(self, now="") -> ReliabilitySummary:
        return ReliabilitySummary(
            timestamp=now, incident_event_count=len(ledger.read_incident_events()),
            incident_count=len(ledger.incident_ids()),
            recovery_plan_count=len(ledger.read_recovery_plans()),
            recovery_event_count=len(ledger.read_recovery_events()),
            integrity_check_count=len(ledger.read_integrity_checks()),
            reliability_metric_count=len(ledger.read_reliability_metrics()),
            postmortem_event_count=len(ledger.read_postmortem_events()),
            postmortem_count=len(ledger.postmortem_ids()),
            report_count=len(ledger.read_reports()), artifact_count=len(ledger.read_artifacts()))
