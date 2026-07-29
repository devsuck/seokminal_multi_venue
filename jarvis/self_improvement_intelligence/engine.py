"""Research Self-Improvement Engine (P10.13) — 연구 과정 최적화 분석. **분석·제안·기록 전용.**

P10.2~P10.12 연구 이력을 READ ONLY 로 소비해 워크플로·병목·개선 기회·프로세스 권고·템플릿 진화·개선
증거를 남긴다. **연구 과정 분석·제안만 수행한다.** execution/broker/portfolio/risk execution/permission/
capital allocation import·호출 없음. research strategy/model/signal 수정·실험 자동 선택·deploy 없음.
IMPROVEMENT SUGGESTION ≠ ACTION · RESEARCH RECOMMENDATION ≠ APPROVAL · INSIGHT ≠ EXECUTION. ACCEPTED 는
사람 인지(acknowledgement)일 뿐 자동 변경 없음. 상위 파일은 읽기만. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.self_improvement_intelligence import ledger
from jarvis.self_improvement_intelligence.models import (
    ACCEPTED,
    ANALYZED,
    ARCHIVED,
    ART_BOTTLENECK,
    ART_EDGE,
    ART_EVIDENCE,
    ART_OPPORTUNITY,
    ART_RECOMMENDATION,
    ART_REPORT,
    ART_SOURCE,
    ART_TEMPLATE,
    ART_WORKFLOW,
    CREATED,
    EDGE_TYPES,
    GENESIS,
    IDENTIFIED,
    NODE_TYPES,
    REVIEWED,
    BottleneckRecord,
    IllegalTransition,
    ImmutableBottleneckError,
    ImmutableOpportunityError,
    ImmutableTemplateError,
    ImmutableWorkflowError,
    ImprovementArtifact,
    ImprovementEvidence,
    ImprovementReport,
    ImprovementSummary,
    InvalidImprovementLink,
    OpportunityEvent,
    RecommendationEvent,
    TemplateEvolution,
    UnknownOpportunity,
    UnknownRecommendation,
    UnknownWorkflow,
    WorkflowPattern,
    artifact_id as _artifact_id,
    bottleneck_id as _bottleneck_id,
    can_transition_opportunity,
    can_transition_recommendation,
    content_hash,
    detect_cycle,
    edge_id as _edge_id,
    evidence_id as _evidence_id,
    improvement_confidence,
    improvement_score,
    input_digest,
    metadata_hash as _metadata_hash,
    opportunity_event_id,
    opportunity_id as _opportunity_id,
    recommendation_event_id,
    recommendation_id as _recommendation_id,
    report_id as _report_id,
    template_id as _template_id,
    workflow_diff,
    workflow_id as _workflow_id,
)

_DISCLAIMER = ("연구 개선 분석 — IMPROVEMENT SUGGESTION ≠ ACTION · RESEARCH RECOMMENDATION ≠ "
               "APPROVAL · INSIGHT ≠ EXECUTION. AUTO_FIX/AUTO_APPLY/DEPLOY 아님.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchSelfImprovementEngine:
    """연구 자기개선 분석 엔진. 불변·append-only·결정적. 실행/거래/배포/수정/선택 권한 없음."""

    # ── 아티팩트 계보(내부) ──
    def _record_artifact(self, artifact_type: str, ref_id: str, parent_artifact: str,
                         now: str, *, commit: bool, from_ref: str = "", to_ref: str = "",
                         edge_type: str = "") -> dict:
        aid = _artifact_id(artifact_type, ref_id)
        rec = ImprovementArtifact(
            artifact_id=aid, artifact_type=artifact_type, ref_id=ref_id,
            parent_artifact=parent_artifact, from_ref=from_ref, to_ref=to_ref,
            edge_type=edge_type, created_at=now, input_hash=input_digest(artifact_type, ref_id),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    # ── Workflow Pattern (불변) ──
    def register_workflow(self, name: str, steps: list, source_reference: str = "",
                          execution_history: list | None = None, metadata: dict | None = None,
                          now: str = "", *, commit: bool = False) -> WorkflowPattern:
        wid = _workflow_id(name, source_reference)
        mh = _metadata_hash({"steps": list(steps or []), "metadata": dict(metadata or {})})
        for w in ledger.read_workflows():
            if w.get("workflow_id") == wid:
                if w.get("metadata_hash") != mh:
                    raise ImmutableWorkflowError(f"{wid} 워크플로 불변 — 변경 불가")
                return WorkflowPattern(**{k: v for k, v in w.items()
                                          if k in WorkflowPattern.__dataclass_fields__})
        rec = WorkflowPattern(
            workflow_id=wid, name=name, steps=list(steps or []),
            source_reference=source_reference, execution_history=list(execution_history or []),
            metadata_hash=mh, created_at=now, input_hash=input_digest(name, source_reference),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.workflow_exists(wid):
            head = ledger.workflows_head()
            ledger.append_workflow(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_SOURCE, source_reference or f"wf:{wid}", "", now, commit=commit)
        self._record_artifact(ART_WORKFLOW, wid,
                              _artifact_id(ART_SOURCE, source_reference or f"wf:{wid}"), now,
                              commit=commit)
        return WorkflowPattern(**rec)

    def compare_workflows(self, workflow_a: str, workflow_b: str) -> dict:
        """두 워크플로 단계 차이(서술적). **자동 선택 없음.**"""
        wa = ledger.get_workflow(workflow_a)
        wb = ledger.get_workflow(workflow_b)
        if wa is None:
            raise UnknownWorkflow(f"미존재 워크플로 {workflow_a}")
        if wb is None:
            raise UnknownWorkflow(f"미존재 워크플로 {workflow_b}")
        return {"workflow_a": workflow_a, "workflow_b": workflow_b,
                "diff": workflow_diff(wa.get("steps", []), wb.get("steps", [])),
                "note": "서술적 비교만 — 자동 선택/적용 없음"}

    # ── Bottleneck Record (불변) ──
    def analyze_bottleneck(self, bottleneck_type: str, frequency: int = 1, impact: str = "MEDIUM",
                           evidence: list | None = None, now: str = "",
                           *, commit: bool = False) -> BottleneckRecord:
        bid = _bottleneck_id(bottleneck_type, impact)
        mh = _metadata_hash({"frequency": int(frequency), "evidence": list(evidence or [])})
        for b in ledger.read_bottlenecks():
            if b.get("bottleneck_id") == bid:
                if b.get("metadata_hash") != mh:
                    raise ImmutableBottleneckError(f"{bid} 병목 불변 — 변경 불가")
                return BottleneckRecord(**{k: v for k, v in b.items()
                                           if k in BottleneckRecord.__dataclass_fields__})
        rec = BottleneckRecord(
            bottleneck_id=bid, bottleneck_type=bottleneck_type, frequency=int(frequency),
            impact=impact, evidence=list(evidence or []), metadata_hash=mh, created_at=now,
            input_hash=input_digest(bottleneck_type, impact), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.bottleneck_exists(bid):
            head = ledger.bottlenecks_head()
            ledger.append_bottleneck(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_BOTTLENECK, bid, "", now, commit=commit)
        return BottleneckRecord(**rec)

    # ── Improvement Opportunity (이벤트 소싱) ──
    def opportunity_state(self, opportunity_id: str) -> str:
        evs = ledger.opportunity_events_for(opportunity_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _opportunity_meta(self, opportunity_id: str) -> dict | None:
        evs = ledger.opportunity_events_for(opportunity_id)
        return evs[0] if evs else None

    def _emit_opportunity_event(self, meta: dict, frm: str, to: str, now: str,
                                *, commit: bool) -> dict:
        if not can_transition_opportunity(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(opportunity)")
        oid = meta["opportunity_id"]
        eid = opportunity_event_id(oid, frm, to)
        rec = OpportunityEvent(
            event_id=eid, opportunity_id=oid, category=meta["category"],
            description=meta["description"], severity=meta["severity"],
            evidence_refs=meta["evidence_refs"], confidence=meta["confidence"], from_state=frm,
            to_state=to, status=to, created_at=now, input_hash=input_digest(oid, frm, to),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.opportunity_event_exists(eid):
            head = ledger.opportunities_head()
            ledger.append_opportunity_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def record_opportunity(self, category: str, description: str, severity: str = "MEDIUM",
                           evidence_refs: list | None = None, confidence: float = 0.0,
                           bottleneck_ref: str = "", now: str = "",
                           *, commit: bool = False) -> OpportunityEvent:
        oid = _opportunity_id(category, description)
        existing = ledger.opportunity_events_for(oid)
        if existing:
            first = existing[0]
            if first.get("severity") != severity:
                raise ImmutableOpportunityError(f"{oid} 개선 기회 불변 — 변경 불가")
            return OpportunityEvent(**existing[-1])
        meta = {"opportunity_id": oid, "category": category, "description": description,
                "severity": severity, "evidence_refs": list(evidence_refs or []),
                "confidence": round(float(confidence), 8)}
        rec = self._emit_opportunity_event(meta, "", IDENTIFIED, now, commit=commit)
        parent = _artifact_id(ART_BOTTLENECK, bottleneck_ref) if bottleneck_ref and \
            ledger.artifact_exists(_artifact_id(ART_BOTTLENECK, bottleneck_ref)) else ""
        self._record_artifact(ART_OPPORTUNITY, oid, parent, now, commit=commit)
        return OpportunityEvent(**rec)

    def transition_opportunity(self, opportunity_id: str, to: str, now: str = "", *,
                               commit: bool = False) -> dict:
        meta = self._opportunity_meta(opportunity_id)
        if meta is None:
            raise UnknownOpportunity(f"미존재 개선 기회 {opportunity_id}")
        return self._emit_opportunity_event(meta, self.opportunity_state(opportunity_id), to,
                                            now, commit=commit)

    # ── Improvement Recommendation (이벤트 소싱) ──
    def recommendation_state(self, recommendation_id: str) -> str:
        evs = ledger.recommendation_events_for(recommendation_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _recommendation_meta(self, recommendation_id: str) -> dict | None:
        evs = ledger.recommendation_events_for(recommendation_id)
        return evs[0] if evs else None

    def _emit_recommendation_event(self, meta: dict, frm: str, to: str, now: str,
                                   *, commit: bool) -> dict:
        if not can_transition_recommendation(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(recommendation)")
        rid = meta["recommendation_id"]
        eid = recommendation_event_id(rid, frm, to)
        rec = RecommendationEvent(
            event_id=eid, recommendation_id=rid, target_process=meta["target_process"],
            suggestion=meta["suggestion"], expected_benefit=meta["expected_benefit"],
            supporting_evidence=meta["supporting_evidence"], confidence=meta["confidence"],
            from_state=frm, to_state=to, status=to, created_at=now,
            input_hash=input_digest(rid, frm, to), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.recommendation_event_exists(eid):
            head = ledger.recommendations_head()
            ledger.append_recommendation_event(
                _seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def create_recommendation(self, target_process: str, suggestion: str,
                              expected_benefit: str = "", supporting_evidence: list | None = None,
                              confidence: float = 0.0, opportunity_ref: str = "", now: str = "",
                              *, commit: bool = False) -> RecommendationEvent:
        """연구 전용 제안 생성(CREATED). **자동 적용 없음.**"""
        rid = _recommendation_id(target_process, suggestion)
        existing = ledger.recommendation_events_for(rid)
        if existing:
            return RecommendationEvent(**existing[-1])
        meta = {"recommendation_id": rid, "target_process": target_process,
                "suggestion": suggestion, "expected_benefit": expected_benefit,
                "supporting_evidence": list(supporting_evidence or []),
                "confidence": round(float(confidence), 8)}
        rec = self._emit_recommendation_event(meta, "", CREATED, now, commit=commit)
        parent = _artifact_id(ART_OPPORTUNITY, opportunity_ref) if opportunity_ref and \
            ledger.artifact_exists(_artifact_id(ART_OPPORTUNITY, opportunity_ref)) else ""
        self._record_artifact(ART_RECOMMENDATION, rid, parent, now, commit=commit)
        return RecommendationEvent(**rec)

    def transition_recommendation(self, recommendation_id: str, to: str, now: str = "", *,
                                  commit: bool = False) -> dict:
        meta = self._recommendation_meta(recommendation_id)
        if meta is None:
            raise UnknownRecommendation(f"미존재 권고 {recommendation_id}")
        return self._emit_recommendation_event(meta, self.recommendation_state(recommendation_id),
                                               to, now, commit=commit)

    def accept_recommendation(self, recommendation_id: str, now: str = "", *,
                              commit: bool = False) -> dict:
        """CREATED→REVIEWED→ACCEPTED. **ACCEPTED 는 사람 인지일 뿐 자동 변경 없음.**"""
        meta = self._recommendation_meta(recommendation_id)
        if meta is None:
            raise UnknownRecommendation(f"미존재 권고 {recommendation_id}")
        cur = self.recommendation_state(recommendation_id)
        if cur == CREATED:
            self._emit_recommendation_event(meta, CREATED, REVIEWED, now, commit=commit)
        self._emit_recommendation_event(meta, REVIEWED, ACCEPTED, now, commit=commit)
        return {"recommendation_id": recommendation_id,
                "state": self.recommendation_state(recommendation_id)}

    # ── Template Evolution (불변) ──
    def track_template_change(self, name: str, version: str, changes: list | None = None,
                              reason: str = "", evidence: list | None = None,
                              parent_version: str = "", now: str = "",
                              *, commit: bool = False) -> TemplateEvolution:
        tid = _template_id(name, version)
        mh = _metadata_hash({"changes": list(changes or []), "reason": reason})
        for t in ledger.read_templates():
            if t.get("template_id") == tid:
                if t.get("metadata_hash") != mh:
                    raise ImmutableTemplateError(f"{tid} 템플릿 불변 — 변경 불가")
                return TemplateEvolution(**{k: v for k, v in t.items()
                                            if k in TemplateEvolution.__dataclass_fields__})
        rec = TemplateEvolution(
            template_id=tid, name=name, version=version, changes=list(changes or []),
            reason=reason, evidence=list(evidence or []), parent_version=parent_version,
            metadata_hash=mh, created_at=now, input_hash=input_digest(name, version),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.template_exists(tid):
            head = ledger.templates_head()
            ledger.append_template(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_TEMPLATE, tid, "", now, commit=commit)
        return TemplateEvolution(**rec)

    # ── Improvement Evidence ──
    def record_evidence(self, owner_ref: str, name: str, metric: str = "", value: float = 0.0,
                        interpretation: str = "", now: str = "",
                        *, commit: bool = False) -> ImprovementEvidence:
        eid = _evidence_id(owner_ref, name)
        rec = ImprovementEvidence(
            evidence_id=eid, owner_ref=owner_ref, name=name, metric=metric,
            value=round(float(value), 8), interpretation=interpretation, created_at=now,
            input_hash=input_digest(owner_ref, name), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.evidence_exists(eid):
            head = ledger.evidences_head()
            ledger.append_evidence(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = _artifact_id(ART_RECOMMENDATION, owner_ref) if ledger.artifact_exists(
            _artifact_id(ART_RECOMMENDATION, owner_ref)) else ""
        self._record_artifact(ART_EVIDENCE, eid, parent, now, commit=commit)
        return ImprovementEvidence(**rec)

    # ── Research Improvement Graph ──
    def record_improvement_edge(self, from_ref: str, from_type: str, to_ref: str, to_type: str,
                                edge_type: str, now: str = "", *, commit: bool = False) -> dict:
        """개선 그래프 엣지 기록. 노드 유형·엣지 유형 검증 + 순환 차단."""
        if from_type not in NODE_TYPES or to_type not in NODE_TYPES:
            raise InvalidImprovementLink(f"미등록 노드 유형 {from_type}/{to_type}")
        if edge_type not in EDGE_TYPES:
            raise InvalidImprovementLink(f"미등록 엣지 유형 {edge_type}")
        eid = _edge_id(from_ref, edge_type, to_ref)
        if not ledger.artifact_exists(_artifact_id(ART_EDGE, eid)):
            edges = [(a.get("from_ref"), a.get("to_ref")) for a in ledger.read_artifacts()
                     if a.get("artifact_type") == ART_EDGE]
            cyc = detect_cycle(edges + [(from_ref, to_ref)])
            if cyc:
                raise InvalidImprovementLink("개선 그래프 순환 차단: " + "->".join(cyc))
        return self._record_artifact(ART_EDGE, eid, "", now, commit=commit, from_ref=from_ref,
                                     to_ref=to_ref, edge_type=edge_type)

    def improvement_cycle(self) -> list:
        edges = [(a.get("from_ref"), a.get("to_ref")) for a in ledger.read_artifacts()
                 if a.get("artifact_type") == ART_EDGE]
        return detect_cycle(edges)

    # ── Improvement Analysis Framework ──
    def analyze(self, metrics: dict) -> dict:
        """개선 지표 → IMPROVEMENT_CONFIDENCE. **AUTO_FIX/AUTO_APPLY/DEPLOY 아님.**"""
        return {"improvement_score": improvement_score(metrics),
                "improvement_confidence": improvement_confidence(metrics)}

    # ── Improvement Report ──
    def generate_improvement_report(self, scope: str = "GLOBAL", metrics: dict | None = None,
                                    now: str = "", *, commit: bool = False) -> ImprovementReport:
        m = dict(metrics or {})
        opps = ledger.distinct_opportunities()
        sev: dict = {}
        for o in opps:
            sev[o.get("severity")] = sev.get(o.get("severity"), 0) + 1
        recs = ledger.distinct_recommendations()
        rstate: dict = {}
        for r in recs:
            st = self.recommendation_state(r.get("recommendation_id"))
            rstate[st] = rstate.get(st, 0) + 1
        rid = _report_id(scope)
        rec = ImprovementReport(
            report_id=rid, scope=scope, workflow_count=len(ledger.read_workflows()),
            bottleneck_count=len(ledger.read_bottlenecks()), opportunity_count=len(opps),
            opportunity_severity_distribution=dict(sorted(sev.items())),
            recommendation_count=len(recs),
            recommendation_state_distribution=dict(sorted(rstate.items())),
            template_count=len(ledger.read_templates()), metrics=m,
            improvement_score=improvement_score(m),
            improvement_confidence=improvement_confidence(m), disclaimer=_DISCLAIMER,
            created_at=now, input_hash=input_digest(scope), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_REPORT, rid, "", now, commit=commit)
        return ImprovementReport(**rec)

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
    def summary(self, now: str = "") -> ImprovementSummary:
        opps = ledger.distinct_opportunities()
        ostate: dict = {}
        for o in opps:
            st = self.opportunity_state(o.get("opportunity_id"))
            ostate[st] = ostate.get(st, 0) + 1
        recs = ledger.distinct_recommendations()
        rstate: dict = {}
        for r in recs:
            st = self.recommendation_state(r.get("recommendation_id"))
            rstate[st] = rstate.get(st, 0) + 1
        return ImprovementSummary(
            timestamp=now, workflow_count=len(ledger.read_workflows()),
            opportunity_count=len(opps),
            opportunity_state_distribution=dict(sorted(ostate.items())),
            bottleneck_count=len(ledger.read_bottlenecks()), recommendation_count=len(recs),
            recommendation_state_distribution=dict(sorted(rstate.items())),
            template_count=len(ledger.read_templates()),
            evidence_count=len(ledger.read_evidences()), report_count=len(ledger.read_reports()))
