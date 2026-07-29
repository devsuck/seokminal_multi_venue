"""Research Compliance Engine (P10.19) — 연구 산출물 거버넌스 기준 준수 관찰·기록. **분석·기록 전용.**

P9.8~P10.18 연구 생태계를 READ ONLY 로 참조(파일 기반, import 없음)해 규칙·점검·증거·검토·위반·시정 권고·
감사 리포트·컴플라이언스 계보를 남긴다. **위반 자동 수정·연구 산출물 수정·배포 승인·permission 변경·실행
상태 변경 없음.** execution/broker/order/portfolio execution/capital allocation/live trading/permission/
risk controller import·호출 없음. COMPLIANCE CHECK ≠ APPROVAL · VIOLATION DETECTION ≠ CORRECTION ·
RECOMMENDATION ≠ ACTION · AUDIT RESULT ≠ DEPLOYMENT PERMISSION. 상위 파일은 읽기만. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.research_compliance import ledger
from jarvis.research_compliance.models import (
    ARCHIVED,
    ART_CHECK,
    ART_EVIDENCE,
    ART_OBJECT,
    ART_RECOMMENDATION,
    ART_REPORT,
    ART_REVIEW,
    ART_RULE,
    ART_VIOLATION,
    CHECK_RESULTS,
    DETECTED,
    GENESIS,
    PRIORITIES,
    RESOLVED,
    REVIEWED,
    REVIEW_DECISIONS,
    RULE_CATEGORIES,
    AuditReport,
    ComplianceArtifact,
    ComplianceCheck,
    ComplianceRule,
    ComplianceSummary,
    EvidenceRecord,
    IllegalTransition,
    ImmutableCheckError,
    ImmutableEvidenceError,
    ImmutableRuleError,
    InvalidCheckResult,
    InvalidReviewDecision,
    InvalidRuleCategory,
    InvalidViolationCategory,
    MissingReviewer,
    RemediationRecommendation,
    ReviewRecord,
    UnknownRule,
    UnknownViolation,
    ViolationEvent,
    artifact_id as _artifact_id,
    can_transition_violation,
    check_id as _check_id,
    checksum as _checksum,
    compliance_score,
    compliance_status,
    content_hash,
    derive_result,
    detect_cycle,
    evidence_id as _evidence_id,
    input_digest,
    metadata_hash as _metadata_hash,
    recommendation_id as _recommendation_id,
    report_id as _report_id,
    review_id as _review_id,
    rule_id as _rule_id,
    violation_event_id,
    violation_id as _violation_id,
)

_DISCLAIMER = ("연구 컴플라이언스 데이터 — COMPLIANCE CHECK ≠ APPROVAL · VIOLATION DETECTION ≠ "
               "CORRECTION · RECOMMENDATION ≠ ACTION · AUDIT RESULT ≠ DEPLOYMENT PERMISSION. "
               "자동수정/승인/배포/실행 아님.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchComplianceEngine:
    """연구 컴플라이언스 엔진. 불변·append-only·결정적. 실행/수정/승인/배포/permission 변경 권한 없음."""

    # ── 아티팩트 계보(내부) ──
    def _record_artifact(self, artifact_type: str, ref_id: str, parent_artifact: str,
                         now: str, *, commit: bool) -> dict:
        aid = _artifact_id(artifact_type, ref_id)
        rec = ComplianceArtifact(
            artifact_id=aid, artifact_type=artifact_type, ref_id=ref_id,
            parent_artifact=parent_artifact, created_at=now,
            input_hash=input_digest(artifact_type, ref_id), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def _ensure_object_artifact(self, source_reference: str, now: str, *, commit: bool) -> str:
        """연구 객체(계보 루트) 노드 보장. 반환: 객체 아티팩트 id."""
        return self._record_artifact(ART_OBJECT, source_reference, "", now,
                                     commit=commit)["artifact_id"]

    # ── Compliance Rule Registry (불변) ──
    def register_rule(self, category: str, description: str, severity: str = "MEDIUM",
                     version: str = "1.0", metadata: dict | None = None, now: str = "",
                     *, commit: bool = False) -> ComplianceRule:
        """컴플라이언스 규칙 등록. category 검증·버전 불변. 동일 id·상이 metadata → 불변 위반."""
        if category not in RULE_CATEGORIES:
            raise InvalidRuleCategory(f"미등록 규칙 범주 {category}")
        rid = _rule_id(category, description, version)
        mh = _metadata_hash({"severity": severity, "metadata": dict(metadata or {})})
        existing = ledger.get_rule(rid)
        if existing is not None:
            if existing.get("metadata_hash") != mh:
                raise ImmutableRuleError(f"{rid} 규칙 불변 — 변경 불가")
            return ComplianceRule(**{k: v for k, v in existing.items()
                                     if k in ComplianceRule.__dataclass_fields__})
        rec = ComplianceRule(
            rule_id=rid, category=category, description=description, severity=severity,
            version=version, metadata_hash=mh, created_at=now,
            input_hash=input_digest(category, description, version),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.rule_exists(rid):
            head = ledger.rules_head()
            ledger.append_rule(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_RULE, rid, "", now, commit=commit)
        return ComplianceRule(**rec)

    # ── Evidence Registry (불변) ──
    def register_evidence(self, source: str, artifact_reference: str, payload=None,
                        checksum: str = "", epoch: str = "", now: str = "",
                        *, commit: bool = False) -> EvidenceRecord:
        """증거 기록 등록(불변). checksum 미지정 시 payload 로부터 결정적 계산. 동일 id·상이 checksum → 불변."""
        cs = checksum or _checksum(payload if payload is not None else artifact_reference)
        eid = _evidence_id(source, artifact_reference)
        existing = ledger.get_evidence(eid)
        if existing is not None:
            if existing.get("checksum") != cs:
                raise ImmutableEvidenceError(f"{eid} 증거 불변 — 변경 불가")
            return EvidenceRecord(**{k: v for k, v in existing.items()
                                     if k in EvidenceRecord.__dataclass_fields__})
        rec = EvidenceRecord(
            evidence_id=eid, source=source, artifact_reference=artifact_reference, checksum=cs,
            epoch=epoch, timestamp=now, created_at=now,
            input_hash=input_digest(source, artifact_reference), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.evidence_exists(eid):
            head = ledger.evidence_head()
            ledger.append_evidence(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = _artifact_id(ART_OBJECT, source) if ledger.artifact_exists(
            _artifact_id(ART_OBJECT, source)) else ""
        self._record_artifact(ART_EVIDENCE, eid, parent, now, commit=commit)
        return EvidenceRecord(**rec)

    # ── Compliance Check (불변) ──
    def run_check(self, rule_id: str, source_reference: str, result: str | None = None,
                evidence_reference: str = "", checklist: dict | None = None, now: str = "",
                *, commit: bool = False) -> ComplianceCheck:
        """규칙에 대한 점검 실행·기록. result 미지정 시 checklist 로부터 파생. **점검 기록 — 승인 아님.**"""
        if not ledger.rule_exists(rule_id):
            raise UnknownRule(f"미존재 규칙 {rule_id}")
        cl = dict(checklist or {})
        res = result if result is not None else derive_result(cl)
        if res not in CHECK_RESULTS:
            raise InvalidCheckResult(f"유효하지 않은 점검 결과 {res}")
        cid = _check_id(rule_id, source_reference)
        existing = ledger.get_check(cid)
        if existing is not None:
            if existing.get("result") != res:
                raise ImmutableCheckError(f"{cid} 점검 불변 — 변경 불가")
            return ComplianceCheck(**{k: v for k, v in existing.items()
                                      if k in ComplianceCheck.__dataclass_fields__})
        rec = ComplianceCheck(
            check_id=cid, rule_id=rule_id, source_reference=source_reference, result=res,
            evidence_reference=evidence_reference, checklist=cl, created_at=now,
            input_hash=input_digest(rule_id, source_reference), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.check_exists(cid):
            head = ledger.checks_head()
            ledger.append_check(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = _artifact_id(ART_RULE, rule_id) if ledger.artifact_exists(
            _artifact_id(ART_RULE, rule_id)) else ""
        self._record_artifact(ART_CHECK, cid, parent, now, commit=commit)
        return ComplianceCheck(**rec)

    # ── 컴플라이언스 프레임워크 편의 점검(결정적, 기록만) ──
    def check_completeness(self, rule_id: str, source_reference: str, facts: dict, now: str = "",
                         *, commit: bool = False) -> ComplianceCheck:
        """연구 완결성: hypothesis/dataset_reference/experiment_lineage 존재 여부."""
        from jarvis.research_compliance.models import COMPLETENESS_REQUIREMENTS
        cl = {k: bool((facts or {}).get(k)) for k in COMPLETENESS_REQUIREMENTS}
        return self.run_check(rule_id, source_reference, None, "", cl, now, commit=commit)

    def check_validation(self, rule_id: str, source_reference: str, facts: dict, now: str = "",
                       *, commit: bool = False) -> ComplianceCheck:
        """검증: out_of_sample/robustness/reproducibility 증거 여부."""
        from jarvis.research_compliance.models import VALIDATION_REQUIREMENTS
        cl = {k: bool((facts or {}).get(k)) for k in VALIDATION_REQUIREMENTS}
        return self.run_check(rule_id, source_reference, None, "", cl, now, commit=commit)

    def check_integrity(self, rule_id: str, source_reference: str, facts: dict, now: str = "",
                      *, commit: bool = False) -> ComplianceCheck:
        """무결성: immutable_artifact/lineage_continuity/evidence_present 여부."""
        from jarvis.research_compliance.models import INTEGRITY_REQUIREMENTS
        cl = {k: bool((facts or {}).get(k)) for k in INTEGRITY_REQUIREMENTS}
        return self.run_check(rule_id, source_reference, None, "", cl, now, commit=commit)

    # ── Review Record (불변) ──
    def create_review(self, reviewer: str, target_reference: str, decision: str, notes: str = "",
                    now: str = "", *, commit: bool = False) -> ReviewRecord:
        """컴플라이언스 검토 기록. reviewer 필수·decision 검증. **검토 기록 — 자동 승인/배포 아님.**"""
        if not reviewer:
            raise MissingReviewer("검토자(reviewer) 필수")
        if decision not in REVIEW_DECISIONS:
            raise InvalidReviewDecision(f"유효하지 않은 검토 결정 {decision}")
        rvid = _review_id(reviewer, target_reference)
        existing = ledger.get_review(rvid)
        if existing is not None:
            return ReviewRecord(**{k: v for k, v in existing.items()
                                   if k in ReviewRecord.__dataclass_fields__})
        rec = ReviewRecord(
            review_id=rvid, reviewer=reviewer, target_reference=target_reference,
            decision=decision, notes=notes, created_at=now,
            input_hash=input_digest(reviewer, target_reference), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.review_exists(rvid):
            head = ledger.reviews_head()
            ledger.append_review(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = ""
        for at in (ART_CHECK, ART_VIOLATION, ART_EVIDENCE, ART_OBJECT):
            cand = _artifact_id(at, target_reference)
            if ledger.artifact_exists(cand):
                parent = cand
                break
        self._record_artifact(ART_REVIEW, rvid, parent, now, commit=commit)
        return ReviewRecord(**rec)

    # ── Violation Registry (이벤트 소싱) ──
    def violation_state(self, violation_id: str) -> str:
        evs = ledger.violation_events_for(violation_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _violation_meta(self, violation_id: str) -> dict | None:
        evs = ledger.violation_events_for(violation_id)
        return evs[0] if evs else None

    def _emit_violation_event(self, meta: dict, frm: str, to: str, now: str,
                              *, commit: bool) -> dict:
        if not can_transition_violation(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(violation)")
        vid = meta["violation_id"]
        eid = violation_event_id(vid, frm, to)
        rec = ViolationEvent(
            event_id=eid, violation_id=vid, category=meta["category"], severity=meta["severity"],
            source=meta["source"], evidence=meta["evidence"], from_state=frm, to_state=to,
            status=to, created_at=now, input_hash=input_digest(vid, frm, to),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.violation_event_exists(eid):
            head = ledger.violations_head()
            ledger.append_violation_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def record_violation(self, category: str, source: str, severity: str = "MEDIUM",
                       evidence: list | None = None, now: str = "",
                       *, commit: bool = False) -> ViolationEvent:
        """컴플라이언스 위반을 기록(DETECTED). category 검증. **탐지 기록 — 자동 시정 없음.**"""
        if category not in RULE_CATEGORIES:
            raise InvalidViolationCategory(f"미등록 위반 범주 {category}")
        vid = _violation_id(category, source)
        existing = ledger.violation_events_for(vid)
        if existing:
            return ViolationEvent(**existing[-1])
        meta = {"violation_id": vid, "category": category, "severity": severity, "source": source,
                "evidence": list(evidence or [])}
        rec = self._emit_violation_event(meta, "", DETECTED, now, commit=commit)
        parent = ""
        for at in (ART_CHECK, ART_OBJECT):
            cand = _artifact_id(at, source)
            if ledger.artifact_exists(cand):
                parent = cand
                break
        self._record_artifact(ART_VIOLATION, vid, parent, now, commit=commit)
        return ViolationEvent(**rec)

    def transition_violation(self, violation_id: str, to: str, now: str = "", *,
                             commit: bool = False) -> dict:
        meta = self._violation_meta(violation_id)
        if meta is None:
            raise UnknownViolation(f"미존재 위반 {violation_id}")
        return self._emit_violation_event(meta, self.violation_state(violation_id), to, now,
                                          commit=commit)

    def resolve_violation(self, violation_id: str, now: str = "", *, commit: bool = False) -> dict:
        """DETECTED→REVIEWED→RESOLVED. **해소는 기록 전용 — 자동 수정 없음.**"""
        meta = self._violation_meta(violation_id)
        if meta is None:
            raise UnknownViolation(f"미존재 위반 {violation_id}")
        cur = self.violation_state(violation_id)
        if cur == DETECTED:
            self._emit_violation_event(meta, DETECTED, REVIEWED, now, commit=commit)
        self._emit_violation_event(meta, REVIEWED, RESOLVED, now, commit=commit)
        return {"violation_id": violation_id, "state": self.violation_state(violation_id),
                "note": "기록 전용 — 자동 수정/배포 아님"}

    # ── Remediation Recommendation (불변) ──
    def create_recommendation(self, target_violation: str, action_description: str,
                            rationale: str = "", priority: str = "MEDIUM",
                            supporting_evidence: list | None = None, now: str = "",
                            *, commit: bool = False) -> RemediationRecommendation:
        """시정 권고 기록. **RECOMMENDATION ≠ ACTION — 자동 적용/시정 없음.**"""
        rid = _recommendation_id(target_violation, action_description)
        for r in ledger.read_recommendations():
            if r.get("recommendation_id") == rid:
                return RemediationRecommendation(**{k: v for k, v in r.items()
                                                    if k in RemediationRecommendation.__dataclass_fields__})
        rec = RemediationRecommendation(
            recommendation_id=rid, target_violation=target_violation,
            action_description=action_description, rationale=rationale, priority=priority,
            supporting_evidence=list(supporting_evidence or []), created_at=now,
            input_hash=input_digest(target_violation, action_description),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.recommendation_exists(rid):
            head = ledger.recommendations_head()
            ledger.append_recommendation(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = _artifact_id(ART_VIOLATION, target_violation) if ledger.artifact_exists(
            _artifact_id(ART_VIOLATION, target_violation)) else ""
        self._record_artifact(ART_RECOMMENDATION, rid, parent, now, commit=commit)
        return RemediationRecommendation(**rec)

    # ── 분석 프레임워크 ──
    def analyze(self, metrics: dict) -> dict:
        """컴플라이언스 지표 → SCORE/STATUS. **COMPLIANCE CHECK ≠ APPROVAL — 승인 신호 아님.**"""
        return {"compliance_score": compliance_score(metrics),
                "compliance_status": compliance_status(metrics)}

    def integrity_findings(self) -> list:
        """무결성 지적: FAIL 점검·미해소 위반·dangling 증거 참조. **지적 기록 — 개입 없음.**"""
        out: list = []
        for c in ledger.read_checks():
            if c.get("result") == "FAIL":
                out.append(f"failed_check:{c.get('rule_id')}:{c.get('source_reference')}")
        for v in ledger.distinct_violations():
            st = self.violation_state(v.get("violation_id"))
            if st not in ("RESOLVED", "ARCHIVED"):
                out.append(f"open_violation:{v.get('category')}:{v.get('source')}")
        return sorted(set(out))

    # ── 계보 검증 ──
    def verify_lineage(self) -> dict:
        """컴플라이언스 계보(아티팩트 parent 체인): dangling parent·순환 탐지. **읽기 전용.**"""
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

    # ── Audit Report ──
    def generate_report(self, scope: str = "GLOBAL", metrics: dict | None = None, now: str = "",
                       *, commit: bool = False) -> AuditReport:
        m = dict(metrics or {})
        rules = ledger.read_rules()
        rc_dist: dict = {}
        for r in rules:
            rc_dist[r.get("category")] = rc_dist.get(r.get("category"), 0) + 1
        checks = ledger.read_checks()
        res_dist: dict = {}
        for c in checks:
            res_dist[c.get("result")] = res_dist.get(c.get("result"), 0) + 1
        reviews = ledger.read_reviews()
        rvd_dist: dict = {}
        for rv in reviews:
            rvd_dist[rv.get("decision")] = rvd_dist.get(rv.get("decision"), 0) + 1
        viols = ledger.distinct_violations()
        vst_dist: dict = {}
        vsev_dist: dict = {}
        for v in viols:
            st = self.violation_state(v.get("violation_id"))
            vst_dist[st] = vst_dist.get(st, 0) + 1
            vsev_dist[v.get("severity")] = vsev_dist.get(v.get("severity"), 0) + 1
        rid = _report_id(scope)
        rec = AuditReport(
            report_id=rid, scope=scope, rule_count=len(rules),
            rule_category_distribution=dict(sorted(rc_dist.items())), check_count=len(checks),
            check_result_distribution=dict(sorted(res_dist.items())),
            evidence_count=len(ledger.read_evidence()), review_count=len(reviews),
            review_decision_distribution=dict(sorted(rvd_dist.items())), violation_count=len(viols),
            violation_state_distribution=dict(sorted(vst_dist.items())),
            violation_severity_distribution=dict(sorted(vsev_dist.items())),
            recommendation_count=len(ledger.read_recommendations()),
            integrity_findings=self.integrity_findings(), metrics=m,
            compliance_score=compliance_score(m), compliance_status=compliance_status(m),
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(scope),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_REPORT, rid, "", now, commit=commit)
        return AuditReport(**rec)

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
    def summary(self, now: str = "") -> ComplianceSummary:
        rules = ledger.read_rules()
        rc_dist: dict = {}
        for r in rules:
            rc_dist[r.get("category")] = rc_dist.get(r.get("category"), 0) + 1
        checks = ledger.read_checks()
        res_dist: dict = {}
        for c in checks:
            res_dist[c.get("result")] = res_dist.get(c.get("result"), 0) + 1
        reviews = ledger.read_reviews()
        rvd_dist: dict = {}
        for rv in reviews:
            rvd_dist[rv.get("decision")] = rvd_dist.get(rv.get("decision"), 0) + 1
        viols = ledger.distinct_violations()
        vst_dist: dict = {}
        for v in viols:
            st = self.violation_state(v.get("violation_id"))
            vst_dist[st] = vst_dist.get(st, 0) + 1
        return ComplianceSummary(
            timestamp=now, rule_count=len(rules),
            rule_category_distribution=dict(sorted(rc_dist.items())), check_count=len(checks),
            check_result_distribution=dict(sorted(res_dist.items())),
            evidence_count=len(ledger.read_evidence()), review_count=len(reviews),
            review_decision_distribution=dict(sorted(rvd_dist.items())), violation_count=len(viols),
            violation_state_distribution=dict(sorted(vst_dist.items())),
            recommendation_count=len(ledger.read_recommendations()),
            report_count=len(ledger.read_reports()))
