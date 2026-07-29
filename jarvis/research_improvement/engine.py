"""Research Improvement Engine (P11.10) — 연구 자기개선 루프. **분석·기록 전용.**

이전 연구 활동을 분석해 개선 기회를 기록한다. **이전 연구·전략·모델 수정, 배포 승인, 자동 실험 실행, 설정
변경을 하지 않는다.** ACCEPTED 는 연구 프로세스 수용일 뿐 — 전략/모델/배포 승인·거래 활성화가 아니다.
execution/broker/portfolio/risk/permission/deployment/live import·호출 없음. IMPROVEMENT ≠ EXECUTION · ACCEPTED ≠
DEPLOYMENT · PROPOSAL ≠ APPROVAL. 결정적·불변·append-only·이벤트 소싱.
"""
from __future__ import annotations

from jarvis.research_improvement import ledger
from jarvis.research_improvement.models import (
    ART_CYCLE,
    ART_IMPROVEMENT,
    ART_LEARNING,
    ART_REPORT,
    CATEGORIES,
    DEC_ACCEPT,
    DEC_REWORK,
    DECISIONS,
    GENESIS,
    I_ACCEPTED,
    I_ANALYZING,
    I_ARCHIVED,
    I_OBSERVED,
    I_PROPOSED,
    I_REVIEWING,
    ArtifactRecord,
    CircularLearningError,
    CycleRecord,
    DanglingReferenceError,
    FailureRecord,
    IllegalImprovementTransition,
    ImmutableCycleError,
    ImmutableFailureError,
    ImmutableImprovementError,
    ImmutableLearningError,
    ImmutableObservationError,
    ImprovementEventRecord,
    ImprovementReportRecord,
    ImprovementSummary,
    InvalidCategory,
    InvalidDecision,
    IterationRecord,
    LearningRecord,
    MetricRecord,
    MissingSourceError,
    ObservationRecord,
    RegistryRecord,
    ReviewRecord,
    UnknownCycleError,
    UnknownImprovementError,
    UnknownRegistryError,
    ancestors,
    artifact_id as _artifact_id,
    can_transition,
    compare_direction,
    content_hash,
    cycle_id as _cycle_id,
    detect_cycle,
    failure_id as _failure_id,
    improvement_event_id as _improvement_event_id,
    improvement_id as _improvement_id,
    input_digest,
    iteration_id as _iteration_id,
    learning_id as _learning_id,
    metric_id as _metric_id,
    observation_id as _observation_id,
    registry_id as _registry_id,
    report_id as _report_id,
    review_id as _review_id,
)

_DISCLAIMER = ("Research Improvement 데이터 — IMPROVEMENT ≠ EXECUTION · ACCEPTED ≠ DEPLOYMENT · PROPOSAL ≠ "
               "APPROVAL. 연구 프로세스 개선 분석·기록 전용 — 연구/전략/모델 수정·배포 승인·자동 실행·설정 변경 "
               "없음. ACCEPTED 는 연구 프로세스 수용일 뿐이다.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchImprovementEngine:
    """연구 자기개선 루프 엔진. 불변·append-only·이벤트 소싱·결정적. 실행/승인/수정 권한 없음."""

    # ══════════════ 아티팩트 계보(내부) ══════════════
    def _artifact(self, atype: str, ref: str, parent: str, cycle: str, now: str,
                *, commit: bool) -> ArtifactRecord:
        aid = _artifact_id(atype, ref)
        rec = ArtifactRecord(artifact_id=aid, artifact_type=atype, ref_id=ref,
                             parent_artifact=parent, cycle_id=cycle, created_at=now,
                             input_hash=input_digest(atype, ref), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return ArtifactRecord(**rec)

    # ══════════════ Registry ══════════════
    def register_registry(self, name: str, mandate: str = "", now: str = "",
                        *, commit: bool = False) -> RegistryRecord:
        rid = _registry_id(name)
        existing = ledger.get_registry(rid)
        if existing is not None:
            return RegistryRecord(**{k: v for k, v in existing.items()
                                     if k in RegistryRecord.__dataclass_fields__})
        rec = RegistryRecord(registry_id=rid, name=name, mandate=mandate, created_at=now,
                             input_hash=input_digest(name), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.registry_exists(rid):
            head = ledger.registry_head()
            ledger.append_registry(_seal(rec, head["record_hash"] if head else GENESIS))
        return RegistryRecord(**rec)

    def _require_registry(self, rid: str) -> dict:
        rec = ledger.get_registry(rid)
        if rec is None:
            raise UnknownRegistryError(f"미등록 레지스트리 {rid}")
        return rec

    # ══════════════ register_cycle ══════════════
    def register_cycle(self, registry: str, name: str, scope: str = "", iteration: int = 1,
                     now: str = "", *, commit: bool = False) -> CycleRecord:
        """연구 사이클 기록(불변). iteration 은 반복 회차. **관측 등록만.**"""
        self._require_registry(registry)
        cid = _cycle_id(registry, name, iteration)
        existing = ledger.get_cycle(cid)
        if existing is not None:
            if existing.get("scope") != scope:
                raise ImmutableCycleError(f"{cid} 사이클 불변 — 변경 불가")
            return CycleRecord(**{k: v for k, v in existing.items()
                                  if k in CycleRecord.__dataclass_fields__})
        rec = CycleRecord(cycle_id=cid, registry_id=registry, name=name, scope=scope,
                          iteration=int(iteration), started_at=now,
                          input_hash=input_digest(registry, name, iteration),
                          previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.cycle_exists(cid):
            head = ledger.cycles_head()
            ledger.append_cycle(_seal(rec, head["record_hash"] if head else GENESIS))
        self._artifact(ART_CYCLE, cid, "", cid, now, commit=commit)
        return CycleRecord(**rec)

    def _require_cycle(self, cid: str) -> dict:
        rec = ledger.get_cycle(cid)
        if rec is None:
            raise UnknownCycleError(f"미등록 사이클 {cid}")
        return rec

    # ══════════════ record_observation (+process metric) ══════════════
    def record_observation(self, cycle: str, subject: str, metric_name: str, value: float,
                         unit: str = "", source_layer: str = "", source_ref: str = "", note: str = "",
                         now: str = "", *, commit: bool = False, verify_ref: bool = False) -> ObservationRecord:
        """성능 관측 기록(불변) + 프로세스 메트릭 파생. 소스 참조는 READ ONLY. **기록만.**"""
        self._require_cycle(cycle)
        if source_layer and not source_ref:
            raise MissingSourceError(f"소스 참조 누락: layer={source_layer} ref 없음")
        if verify_ref and source_layer and not ledger.source_ref_exists(source_layer, source_ref):
            raise DanglingReferenceError(f"상위 소스 없음 {source_layer}:{source_ref}")
        oid = _observation_id(cycle, subject, metric_name)
        existing = ledger.get_observation(oid)
        if existing is not None:
            if abs(float(existing.get("value", 0.0)) - float(value)) > 1e-9:
                raise ImmutableObservationError(f"{oid} 관측 불변 — 변경 불가")
            return ObservationRecord(**{k: v for k, v in existing.items()
                                        if k in ObservationRecord.__dataclass_fields__})
        rec = ObservationRecord(
            observation_id=oid, cycle_id=cycle, subject=subject, metric_name=metric_name,
            value=round(float(value), 8), unit=unit, source_layer=source_layer,
            source_ref=source_ref, note=note, recorded_at=now,
            input_hash=input_digest(cycle, subject, metric_name), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.observation_exists(oid):
            head = ledger.observations_head()
            ledger.append_observation(_seal(rec, head["record_hash"] if head else GENESIS))
        return ObservationRecord(**rec)

    def record_metric(self, cycle: str, metric_name: str, value: float, category: str = "",
                    now: str = "", *, commit: bool = False) -> MetricRecord:
        """프로세스 메트릭 기록(불변). **집계·기록만.**"""
        self._require_cycle(cycle)
        mid = _metric_id(cycle, metric_name)
        existing = ledger.get_metric(mid)
        if existing is not None:
            return MetricRecord(**{k: v for k, v in existing.items()
                                   if k in MetricRecord.__dataclass_fields__})
        rec = MetricRecord(metric_id=mid, cycle_id=cycle, metric_name=metric_name,
                           value=round(float(value), 8), category=category, recorded_at=now,
                           input_hash=input_digest(cycle, metric_name),
                           previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.metric_exists(mid):
            head = ledger.metrics_head()
            ledger.append_metric(_seal(rec, head["record_hash"] if head else GENESIS))
        return MetricRecord(**rec)

    # ══════════════ analyze_failure_pattern (repeated mistake detection) ══════════════
    def analyze_failure_pattern(self, cycle: str, pattern_type: str, subject: str, description: str,
                              occurrences: int = 1, source_layer: str = "", source_ref: str = "",
                              related_refs=None, now: str = "", *, commit: bool = False,
                              verify_ref: bool = False) -> FailureRecord:
        """반복 실수/실패 패턴 분석·기록(불변). **탐지·기록만.**"""
        self._require_cycle(cycle)
        if source_layer and not source_ref:
            raise MissingSourceError(f"소스 참조 누락: layer={source_layer} ref 없음")
        if verify_ref and source_layer and not ledger.source_ref_exists(source_layer, source_ref):
            raise DanglingReferenceError(f"상위 소스 없음 {source_layer}:{source_ref}")
        fid = _failure_id(cycle, pattern_type, subject)
        existing = ledger.get_failure(fid)
        if existing is not None:
            if existing.get("occurrences") != int(occurrences):
                raise ImmutableFailureError(f"{fid} 실패 패턴 불변 — 변경 불가")
            return FailureRecord(**{k: v for k, v in existing.items()
                                    if k in FailureRecord.__dataclass_fields__})
        rec = FailureRecord(
            failure_id=fid, cycle_id=cycle, pattern_type=pattern_type, subject=subject,
            description=description, occurrences=int(occurrences), source_layer=source_layer,
            source_ref=source_ref, related_refs=sorted(set(related_refs or [])), detected_at=now,
            input_hash=input_digest(cycle, pattern_type, subject), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.failure_exists(fid):
            head = ledger.failures_head()
            ledger.append_failure(_seal(rec, head["record_hash"] if head else GENESIS))
        return FailureRecord(**rec)

    # ══════════════ 개선 제안 생애주기(event-sourced) ══════════════
    def _improvement_event(self, improvement: str, cycle: str, category: str, title: str,
                         description: str, proposed_change: str, frm: str, to: str, note: str,
                         now: str, *, commit: bool) -> ImprovementEventRecord:
        seq = len(ledger.improvement_events(improvement))
        eid = _improvement_event_id(improvement, to, seq)
        rec = ImprovementEventRecord(
            improvement_event_id=eid, improvement_id=improvement, cycle_id=cycle, category=category,
            title=title, description=description, proposed_change=proposed_change, from_state=frm,
            to_state=to, note=note, occurred_at=now, input_hash=input_digest(improvement, to, seq),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.improvement_event_exists(eid):
            head = ledger.proposals_head()
            ledger.append_improvement_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return ImprovementEventRecord(**rec)

    def identify_improvement(self, cycle: str, category: str, title: str, description: str = "",
                           now: str = "", *, commit: bool = False) -> ImprovementEventRecord:
        """개선 기회 식별(OBSERVED). 중복 개선 기록 거부. **식별·기록만.**"""
        self._require_cycle(cycle)
        if category not in CATEGORIES:
            raise InvalidCategory(f"미등록 카테고리 {category}")
        imp = _improvement_id(cycle, category, title)
        evs = ledger.improvement_events(imp)
        if evs:
            g = evs[0]
            if g.get("description") != description:
                raise ImmutableImprovementError(f"{imp} 개선 기록 불변 — 중복 변경 거부")
            return ImprovementEventRecord(**{k: v for k, v in g.items()
                                             if k in ImprovementEventRecord.__dataclass_fields__})
        ev = self._improvement_event(imp, cycle, category, title, description, "", GENESIS,
                                   I_OBSERVED, "observed", now, commit=commit)
        parent = _artifact_id(ART_CYCLE, cycle)
        self._artifact(ART_IMPROVEMENT, imp, parent if ledger.artifact_exists(parent) else "",
                       cycle, now, commit=commit)
        return ev

    def current_state(self, improvement: str) -> str | None:
        evs = ledger.improvement_events(improvement)
        return evs[-1].get("to_state") if evs else None

    def improvement_meta(self, improvement: str) -> dict:
        evs = ledger.improvement_events(improvement)
        if not evs:
            raise UnknownImprovementError(f"미등록 개선 {improvement}")
        g = evs[0]
        return {"improvement_id": improvement, "cycle_id": g.get("cycle_id"),
                "category": g.get("category"), "title": g.get("title"),
                "description": g.get("description"), "state": evs[-1].get("to_state")}

    def _require_improvement(self, improvement: str) -> str:
        st = self.current_state(improvement)
        if st is None:
            raise UnknownImprovementError(f"미등록 개선 {improvement}")
        return st

    def _transition(self, improvement: str, to: str, note: str, now: str, proposed_change: str = "",
                  *, commit: bool) -> ImprovementEventRecord:
        frm = self._require_improvement(improvement)
        if not can_transition(frm, to):
            raise IllegalImprovementTransition(f"{improvement} {frm}→{to} 불가")
        m = self.improvement_meta(improvement)
        return self._improvement_event(improvement, m["cycle_id"], m["category"], m["title"],
                                      m["description"], proposed_change, frm, to, note, now,
                                      commit=commit)

    def create_proposal(self, improvement: str, proposed_change: str, rationale: str = "",
                      now: str = "", *, commit: bool = False) -> ImprovementEventRecord:
        """개선 제안 작성(OBSERVED→ANALYZING→PROPOSED). **제안·기록만 — 실행 아님.**"""
        st = self._require_improvement(improvement)
        if st != I_OBSERVED:
            raise IllegalImprovementTransition(f"{improvement} OBSERVED 아님({st}) — 제안 불가")
        self._transition(improvement, I_ANALYZING, "analyzing", now, commit=commit)
        return self._transition(improvement, I_PROPOSED, rationale or "proposed", now,
                              proposed_change=proposed_change, commit=commit)

    # ══════════════ review_improvement (workflow) ══════════════
    def review_improvement(self, improvement: str, reviewer: str, decision: str, rationale: str = "",
                         now: str = "", *, commit: bool = False) -> ReviewRecord:
        """개선 리뷰(ACCEPT/REWORK/NOTE). ACCEPT=연구 프로세스 수용일 뿐. **ACCEPTED ≠ DEPLOYMENT.**"""
        st = self._require_improvement(improvement)
        if decision not in DECISIONS:
            raise InvalidDecision(f"미등록 결정 {decision}")
        if st == I_PROPOSED:
            self._transition(improvement, I_REVIEWING, "reviewing", now, commit=commit)
            st = I_REVIEWING
        seq = len(ledger.improvement_reviews(improvement))
        rid = _review_id(improvement, reviewer, seq)
        rec = ReviewRecord(review_id=rid, improvement_id=improvement, reviewer=reviewer,
                           decision=decision, rationale=rationale, created_at=now,
                           input_hash=input_digest(improvement, reviewer, seq),
                           previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.review_exists(rid):
            head = ledger.reviews_head()
            ledger.append_review(_seal(rec, head["record_hash"] if head else GENESIS))
        if st == I_REVIEWING:
            if decision == DEC_ACCEPT:
                self._transition(improvement, I_ACCEPTED, "process_accepted(NOT deployment)", now,
                               commit=commit)
            elif decision == DEC_REWORK:
                self._transition(improvement, I_ANALYZING, "rework", now, commit=commit)
        return ReviewRecord(**rec)

    def archive_improvement(self, improvement: str, now: str = "", *, commit: bool = False) -> ImprovementEventRecord:
        return self._transition(improvement, I_ARCHIVED, "archived", now, commit=commit)

    # ══════════════ record_learning (lineage, reject circular) ══════════════
    def _learning_edges(self) -> list:
        return [(r.get("learning_id"), r.get("parent_learning")) for r in ledger.read_learning()
                if r.get("parent_learning")]

    def record_learning(self, cycle: str, lesson: str, category: str = "", source_layer: str = "",
                      source_ref: str = "", parent_learning: str = "", now: str = "",
                      *, commit: bool = False, verify_ref: bool = False) -> LearningRecord:
        """학습 기록(불변). 계보(parent) 순환/dangling·소스 누락 거부. **기록만.**"""
        self._require_cycle(cycle)
        if category and category not in CATEGORIES:
            raise InvalidCategory(f"미등록 카테고리 {category}")
        if source_layer and not source_ref:
            raise MissingSourceError(f"소스 참조 누락: layer={source_layer} ref 없음")
        if verify_ref and source_layer and not ledger.source_ref_exists(source_layer, source_ref):
            raise DanglingReferenceError(f"상위 소스 없음 {source_layer}:{source_ref}")
        lid = _learning_id(cycle, lesson)
        existing = ledger.get_learning(lid)
        if existing is not None:
            if existing.get("parent_learning") != parent_learning:
                raise ImmutableLearningError(f"{lid} 학습 기록 불변 — 변경 불가")
            return LearningRecord(**{k: v for k, v in existing.items()
                                     if k in LearningRecord.__dataclass_fields__})
        if parent_learning:
            if not ledger.learning_exists(parent_learning):
                raise DanglingReferenceError(f"미등록 부모 학습 {parent_learning}")
            edges = self._learning_edges() + [(lid, parent_learning)]
            if detect_cycle(edges):
                raise CircularLearningError(f"순환 학습 의존성 — 거부 {lid}->{parent_learning}")
        rec = LearningRecord(learning_id=lid, cycle_id=cycle, lesson=lesson, category=category,
                             source_layer=source_layer, source_ref=source_ref,
                             parent_learning=parent_learning, created_at=now,
                             input_hash=input_digest(cycle, lesson), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.learning_exists(lid):
            head = ledger.learning_head()
            ledger.append_learning(_seal(rec, head["record_hash"] if head else GENESIS))
        parent_art = _artifact_id(ART_CYCLE, cycle)
        self._artifact(ART_LEARNING, lid, parent_art if ledger.artifact_exists(parent_art) else "",
                       cycle, now, commit=commit)
        return LearningRecord(**rec)

    def trace_learning_lineage(self, learning: str) -> list:
        return ancestors(self._learning_edges(), learning)

    # ══════════════ compare_iterations (efficiency analysis) ══════════════
    def compare_iterations(self, cycle_a: str, cycle_b: str, metric_name: str,
                         higher_is_better: bool = True, now: str = "",
                         *, commit: bool = False) -> IterationRecord:
        """두 사이클의 메트릭 비교(효율/반복 분석, 결정적). **분석·기록만.**"""
        self._require_cycle(cycle_a)
        self._require_cycle(cycle_b)
        va = self._metric_value(cycle_a, metric_name)
        vb = self._metric_value(cycle_b, metric_name)
        direction, delta = compare_direction(va, vb, higher_is_better)
        iid = _iteration_id(cycle_a, cycle_b, metric_name)
        existing = ledger.get_iteration(iid)
        if existing is not None:
            return IterationRecord(**{k: v for k, v in existing.items()
                                      if k in IterationRecord.__dataclass_fields__})
        rec = IterationRecord(iteration_id=iid, cycle_a=cycle_a, cycle_b=cycle_b,
                              metric_name=metric_name, value_a=va, value_b=vb, delta=delta,
                              direction=direction, compared_at=now,
                              input_hash=input_digest(cycle_a, cycle_b, metric_name),
                              previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.iteration_exists(iid):
            head = ledger.iterations_head()
            ledger.append_iteration(_seal(rec, head["record_hash"] if head else GENESIS))
        return IterationRecord(**rec)

    def _metric_value(self, cycle: str, metric_name: str) -> float:
        m = ledger.get_metric(_metric_id(cycle, metric_name))
        if m is not None:
            return float(m.get("value", 0.0))
        for o in ledger.cycle_observations(cycle):
            if o.get("metric_name") == metric_name:
                return float(o.get("value", 0.0))
        return 0.0

    # ══════════════ generate_report ══════════════
    def generate_report(self, cycle: str, scope: str = "CYCLE", now: str = "",
                      *, commit: bool = False) -> ImprovementReportRecord:
        """개선 리포트(관측·실패·제안·수용·학습·카테고리 분포). **is_binding=False, 프로세스 수용만.**"""
        self._require_cycle(cycle)
        imps = ledger.cycle_improvements(cycle)
        accepted = sum(1 for i in imps if self.current_state(i) in (I_ACCEPTED, I_ARCHIVED))
        cat_dist: dict = {}
        for i in imps:
            cat = self.improvement_meta(i)["category"]
            cat_dist[cat] = cat_dist.get(cat, 0) + 1
        rid = _report_id(cycle, scope, now)
        rec = ImprovementReportRecord(
            report_id=rid, cycle_id=cycle, scope=scope,
            observation_count=len(ledger.cycle_observations(cycle)),
            failure_count=len(ledger.cycle_failures(cycle)), proposal_count=len(imps),
            accepted_count=accepted, learning_count=len(ledger.cycle_learning(cycle)),
            category_distribution=dict(sorted(cat_dist.items())), process_acceptance_only=True,
            is_binding=False, disclaimer=_DISCLAIMER, created_at=now,
            input_hash=input_digest(cycle, scope, now), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = _artifact_id(ART_CYCLE, cycle)
        self._artifact(ART_REPORT, rid, parent if ledger.artifact_exists(parent) else "", cycle,
                       now, commit=commit)
        return ImprovementReportRecord(**rec)

    # ══════════════ verify_integrity ══════════════
    def verify_integrity(self) -> dict:
        from jarvis.research_improvement.verify import verify_chain
        return verify_chain()

    # ══════════════ 조회 편의 ══════════════
    def list_cycles(self, registry: str = "") -> list:
        cs = ledger.read_cycles()
        if registry:
            cs = [c for c in cs if c.get("registry_id") == registry]
        return sorted(c.get("cycle_id") for c in cs)

    def improvements_of(self, cycle: str) -> list:
        return ledger.cycle_improvements(cycle)

    def improvements_in_state(self, state: str) -> list:
        return sorted(i for i in ledger.improvement_ids() if self.current_state(i) == state)

    # ══════════════ Summary ══════════════
    def summary(self, now: str = "") -> ImprovementSummary:
        return ImprovementSummary(
            timestamp=now, registry_count=len(ledger.read_registry()),
            cycle_count=len(ledger.read_cycles()),
            observation_count=len(ledger.read_observations()),
            metric_count=len(ledger.read_metrics()), failure_count=len(ledger.read_failures()),
            improvement_event_count=len(ledger.read_improvement_events()),
            learning_count=len(ledger.read_learning()),
            iteration_count=len(ledger.read_iterations()), review_count=len(ledger.read_reviews()),
            report_count=len(ledger.read_reports()), artifact_count=len(ledger.read_artifacts()))
