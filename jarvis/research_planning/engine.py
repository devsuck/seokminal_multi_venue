"""Research Planning Engine (P10.15) — 역사적 근거로 미래 연구 방향 조직. **계획·기록 전용.**

P10.5/7/8/11/12/13/14 를 READ ONLY 로 소비해 기회·가설·청사진·계획·의존·우선순위·리포트를 남긴다.
**실험 자동 시작·strategy 선택·resource 배분·agent 실행·model 배포 없음.** execution/broker/portfolio
execution/live trading/permission/capital allocation import·호출 없음. PLAN ≠ EXECUTION · PRIORITY ≠
APPROVAL · OPPORTUNITY ≠ GUARANTEED VALUE. 상위 파일은 읽기만. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.research_planning import ledger
from jarvis.research_planning.models import (
    ANALYZED,
    ARCHIVED,
    ART_BLUEPRINT,
    ART_DEPENDENCY,
    ART_HYPOTHESIS,
    ART_OPPORTUNITY,
    ART_PLAN,
    ART_PRIORITY,
    ART_REPORT,
    ART_SOURCE,
    COMPLEXITY_MEDIUM,
    EDGE_TYPES,
    GENESIS,
    IDENTIFIED,
    NODE_TYPES,
    PLANNED,
    DependencyEdge,
    IllegalTransition,
    ImmutableBlueprintError,
    ImmutableHypothesisError,
    ImmutableOpportunityError,
    ImmutablePlanError,
    InvalidDependency,
    OpportunityEvent,
    PlanningArtifact,
    PlanningHypothesis,
    PlanningReport,
    PlanningSummary,
    PriorityAnalysis,
    ResearchBlueprint,
    ResearchPlan,
    UnknownOpportunity,
    UnknownPlan,
    artifact_id as _artifact_id,
    blueprint_id as _blueprint_id,
    can_transition_opportunity,
    complexity_value,
    content_hash,
    dependency_id as _dependency_id,
    detect_cycle,
    hypothesis_id as _hypothesis_id,
    input_digest,
    metadata_hash as _metadata_hash,
    opportunity_event_id,
    opportunity_id as _opportunity_id,
    plan_id as _plan_id,
    planning_confidence,
    planning_score,
    priority_id as _priority_id,
    priority_rank,
    priority_score as _priority_score,
    report_id as _report_id,
)

_DISCLAIMER = ("연구 계획 분석 — PLAN ≠ EXECUTION · PRIORITY ≠ APPROVAL · OPPORTUNITY ≠ "
               "GUARANTEED VALUE. 실험 자동시작/선택/배분/배포 아님.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchPlanningEngine:
    """연구 계획 엔진. 불변·append-only·결정적. 실행/거래/배포/선택/배분 권한 없음."""

    # ── 아티팩트 계보(내부) ──
    def _record_artifact(self, artifact_type: str, ref_id: str, parent_artifact: str,
                         now: str, *, commit: bool) -> dict:
        aid = _artifact_id(artifact_type, ref_id)
        rec = PlanningArtifact(
            artifact_id=aid, artifact_type=artifact_type, ref_id=ref_id,
            parent_artifact=parent_artifact, created_at=now,
            input_hash=input_digest(artifact_type, ref_id), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    # ── Research Opportunity (이벤트 소싱) ──
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
            event_id=eid, opportunity_id=oid, description=meta["description"],
            source_evidence=meta["source_evidence"], expected_learning=meta["expected_learning"],
            confidence=meta["confidence"], from_state=frm, to_state=to, status=to, created_at=now,
            input_hash=input_digest(oid, frm, to), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.opportunity_event_exists(eid):
            head = ledger.opportunities_head()
            ledger.append_opportunity_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def register_opportunity(self, description: str, source_evidence: list | None = None,
                             expected_learning: str = "", confidence: float = 0.0, now: str = "",
                             *, commit: bool = False) -> OpportunityEvent:
        oid = _opportunity_id(description)
        existing = ledger.opportunity_events_for(oid)
        if existing:
            first = existing[0]
            if first.get("expected_learning") != expected_learning:
                raise ImmutableOpportunityError(f"{oid} 기회 불변 — 변경 불가")
            return OpportunityEvent(**existing[-1])
        meta = {"opportunity_id": oid, "description": description,
                "source_evidence": list(source_evidence or []),
                "expected_learning": expected_learning, "confidence": round(float(confidence), 8)}
        rec = self._emit_opportunity_event(meta, "", IDENTIFIED, now, commit=commit)
        self._record_artifact(ART_SOURCE, f"opp:{oid}", "", now, commit=commit)
        self._record_artifact(ART_OPPORTUNITY, oid, _artifact_id(ART_SOURCE, f"opp:{oid}"), now,
                              commit=commit)
        return OpportunityEvent(**rec)

    def transition_opportunity(self, opportunity_id: str, to: str, now: str = "", *,
                               commit: bool = False) -> dict:
        meta = self._opportunity_meta(opportunity_id)
        if meta is None:
            raise UnknownOpportunity(f"미존재 기회 {opportunity_id}")
        return self._emit_opportunity_event(meta, self.opportunity_state(opportunity_id), to,
                                            now, commit=commit)

    def _safe_advance_opportunity(self, opportunity_id: str, to: str, now: str,
                                  *, commit: bool) -> None:
        meta = self._opportunity_meta(opportunity_id)
        if meta is None:
            return
        cur = self.opportunity_state(opportunity_id)
        if cur != to and can_transition_opportunity(cur, to):
            self._emit_opportunity_event(meta, cur, to, now, commit=commit)

    # ── Planning Hypothesis (불변) ──
    def create_hypothesis(self, statement: str, rationale: str = "",
                          evidence_refs: list | None = None, confidence: float = 0.0,
                          now: str = "", *, commit: bool = False) -> PlanningHypothesis:
        hid = _hypothesis_id(statement)
        for h in ledger.read_hypotheses():
            if h.get("hypothesis_id") == hid:
                if h.get("rationale") != rationale:
                    raise ImmutableHypothesisError(f"{hid} 가설 불변 — 변경 불가")
                return PlanningHypothesis(**{k: v for k, v in h.items()
                                             if k in PlanningHypothesis.__dataclass_fields__})
        rec = PlanningHypothesis(
            hypothesis_id=hid, statement=statement, rationale=rationale,
            evidence_refs=list(evidence_refs or []), confidence=round(float(confidence), 8),
            created_at=now, input_hash=input_digest(statement), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.hypothesis_exists(hid):
            head = ledger.hypotheses_head()
            ledger.append_hypothesis(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_HYPOTHESIS, hid, "", now, commit=commit)
        return PlanningHypothesis(**rec)

    # ── Research Blueprint (불변, 실행 없음) ──
    def create_blueprint(self, objective: str, inputs: list | None = None, method: str = "",
                         validation_requirements: list | None = None,
                         dependencies: list | None = None, now: str = "",
                         *, commit: bool = False) -> ResearchBlueprint:
        bid = _blueprint_id(objective, method)
        mh = _metadata_hash({"inputs": list(inputs or []), "method": method,
                             "validation": list(validation_requirements or []),
                             "dependencies": list(dependencies or [])})
        for b in ledger.read_blueprints():
            if b.get("blueprint_id") == bid:
                if b.get("metadata_hash") != mh:
                    raise ImmutableBlueprintError(f"{bid} 청사진 불변 — 변경 불가")
                return ResearchBlueprint(**{k: v for k, v in b.items()
                                            if k in ResearchBlueprint.__dataclass_fields__})
        rec = ResearchBlueprint(
            blueprint_id=bid, objective=objective, inputs=list(inputs or []), method=method,
            validation_requirements=list(validation_requirements or []),
            dependencies=list(dependencies or []), metadata_hash=mh, created_at=now,
            input_hash=input_digest(objective, method), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.blueprint_exists(bid):
            head = ledger.blueprints_head()
            ledger.append_blueprint(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_BLUEPRINT, bid, "", now, commit=commit)
        return ResearchBlueprint(**rec)

    # ── Dependency Graph (노드/엣지 검증·순환 차단) ──
    def add_dependency(self, from_node: str, from_type: str, edge_type: str, to_node: str,
                       to_type: str, now: str = "", *, commit: bool = False) -> DependencyEdge:
        if from_type not in NODE_TYPES or to_type not in NODE_TYPES:
            raise InvalidDependency(f"미등록 노드 유형 {from_type}/{to_type}")
        if edge_type not in EDGE_TYPES:
            raise InvalidDependency(f"미등록 엣지 유형 {edge_type}")
        did = _dependency_id(from_node, edge_type, to_node)
        if not ledger.dependency_exists(did):
            edges = [(d.get("from_node"), d.get("to_node")) for d in ledger.read_dependencies()]
            cyc = detect_cycle(edges + [(from_node, to_node)])
            if cyc:
                raise InvalidDependency("의존 순환 차단: " + "->".join(cyc))
        rec = DependencyEdge(
            dependency_id=did, from_node=from_node, from_type=from_type, edge_type=edge_type,
            to_node=to_node, to_type=to_type, created_at=now,
            input_hash=input_digest(from_node, edge_type, to_node),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.dependency_exists(did):
            head = ledger.dependencies_head()
            ledger.append_dependency(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_DEPENDENCY, did, "", now, commit=commit)
        return DependencyEdge(**rec)

    def dependency_cycle(self) -> list:
        edges = [(d.get("from_node"), d.get("to_node")) for d in ledger.read_dependencies()]
        return detect_cycle(edges)

    # ── Research Plan (불변) ──
    def create_plan(self, name: str, opportunities: list | None = None,
                    dependencies: list | None = None, metrics: dict | None = None,
                    estimated_complexity: str = COMPLEXITY_MEDIUM, expected_value: str = "",
                    now: str = "", *, commit: bool = False) -> ResearchPlan:
        """연구 계획을 불변 등록. priority_score 는 정보용 — 승인/실행 아님."""
        pid = _plan_id(name)
        m = dict(metrics or {})
        if "complexity" not in m:
            m["complexity"] = complexity_value(estimated_complexity)
        pscore = _priority_score(m)
        opps = sorted(opportunities or [])
        deps = sorted(dependencies or [])
        mh = _metadata_hash({"opportunities": opps, "dependencies": deps,
                             "complexity": estimated_complexity, "expected_value": expected_value})
        for p in ledger.read_plans():
            if p.get("plan_id") == pid:
                if p.get("metadata_hash") != mh:
                    raise ImmutablePlanError(f"{pid} 계획 불변 — 변경 불가")
                return ResearchPlan(**{k: v for k, v in p.items()
                                       if k in ResearchPlan.__dataclass_fields__})
        rec = ResearchPlan(
            plan_id=pid, name=name, opportunities=opps, dependencies=deps,
            priority_score=pscore, estimated_complexity=estimated_complexity,
            expected_value=expected_value, metadata_hash=mh, created_at=now,
            input_hash=input_digest(name), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.plan_exists(pid):
            head = ledger.plans_head()
            ledger.append_plan(_seal(rec, head["record_hash"] if head else GENESIS))
        # 계획에 포함된 기회는 PLANNED 로 진행(safe).
        for oid in opps:
            self._safe_advance_opportunity(oid, ANALYZED, now, commit=commit)
            self._safe_advance_opportunity(oid, PLANNED, now, commit=commit)
        parent = _artifact_id(ART_OPPORTUNITY, opps[0]) if opps and ledger.artifact_exists(
            _artifact_id(ART_OPPORTUNITY, opps[0])) else ""
        self._record_artifact(ART_PLAN, pid, parent, now, commit=commit)
        return ResearchPlan(**rec)

    # ── Priority Analysis (정보용) ──
    def prioritize(self, plan_ref: str, metrics: dict, now: str = "",
                   *, commit: bool = False) -> PriorityAnalysis:
        """계획 우선순위 분석(정보용). **PRIORITY ≠ APPROVAL.**"""
        if ledger.get_plan(plan_ref) is None:
            raise UnknownPlan(f"미존재 계획 {plan_ref}")
        m = dict(metrics or {})
        pscore = _priority_score(m)
        rank = priority_rank(pscore)
        prid = _priority_id(plan_ref)
        rec = PriorityAnalysis(
            priority_id=prid, plan_ref=plan_ref, components=m, priority_score=pscore, rank=rank,
            created_at=now, input_hash=input_digest(plan_ref), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.priority_exists(prid):
            head = ledger.priorities_head()
            ledger.append_priority(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_PRIORITY, prid, _artifact_id(ART_PLAN, plan_ref), now,
                              commit=commit)
        return PriorityAnalysis(**rec)

    # ── Planning Analysis ──
    def analyze(self, metrics: dict) -> dict:
        """계획 지표 → PLANNING_CONFIDENCE. **자동 조치 없음.**"""
        return {"planning_score": planning_score(metrics),
                "planning_confidence": planning_confidence(metrics)}

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

    # ── Planning Report ──
    def generate_report(self, scope: str = "GLOBAL", metrics: dict | None = None, now: str = "",
                        *, commit: bool = False) -> PlanningReport:
        m = dict(metrics or {})
        opps = ledger.distinct_opportunities()
        ostate: dict = {}
        for o in opps:
            st = self.opportunity_state(o.get("opportunity_id"))
            ostate[st] = ostate.get(st, 0) + 1
        rid = _report_id(scope)
        rec = PlanningReport(
            report_id=rid, scope=scope, opportunity_count=len(opps),
            opportunity_state_distribution=dict(sorted(ostate.items())),
            plan_count=len(ledger.read_plans()), blueprint_count=len(ledger.read_blueprints()),
            hypothesis_count=len(ledger.read_hypotheses()),
            dependency_count=len(ledger.read_dependencies()),
            priority_count=len(ledger.read_priorities()), metrics=m,
            planning_score=planning_score(m), planning_confidence=planning_confidence(m),
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(scope),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_REPORT, rid, "", now, commit=commit)
        return PlanningReport(**rec)

    # ── Summary ──
    def summary(self, now: str = "") -> PlanningSummary:
        opps = ledger.distinct_opportunities()
        ostate: dict = {}
        for o in opps:
            st = self.opportunity_state(o.get("opportunity_id"))
            ostate[st] = ostate.get(st, 0) + 1
        deps = ledger.read_dependencies()
        edist: dict = {}
        for d in deps:
            edist[d.get("edge_type")] = edist.get(d.get("edge_type"), 0) + 1
        return PlanningSummary(
            timestamp=now, opportunity_count=len(opps),
            opportunity_state_distribution=dict(sorted(ostate.items())),
            plan_count=len(ledger.read_plans()), blueprint_count=len(ledger.read_blueprints()),
            hypothesis_count=len(ledger.read_hypotheses()), dependency_count=len(deps),
            edge_type_distribution=dict(sorted(edist.items())),
            priority_count=len(ledger.read_priorities()), report_count=len(ledger.read_reports()))
