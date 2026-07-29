"""Adaptive Research Loop Engine (P12.4) — 연구 프로세스 개선 피드백 루프. **개선 기록 전용.**

실패 실험 분석·개선 제안·워크플로 적응·연구 효율 추적을 관리한다. **개선을 기록만 하며 자동 수정을 하지 않는다.**
execution/broker/portfolio/risk/permission/deployment/live import·호출 없음. IMPROVEMENT ≠ EXECUTION · PROPOSAL ≠
MODIFICATION · RECORDED ≠ DEPLOYMENT. 개선 제안은 모델·전략·권한을 수정할 수 없고 인간 리뷰 기록이 필요하다.
결정적·불변·append-only·이벤트 소싱.
"""
from __future__ import annotations

from jarvis.adaptive_research_loop import ledger
from jarvis.adaptive_research_loop.models import (
    ADAPTATION_CATEGORIES,
    DEC_ACCEPT,
    DEC_REWORK,
    DECISIONS,
    GENESIS,
    L_ANALYZED,
    L_ARCHIVED,
    L_OBSERVED,
    L_PROPOSED,
    L_RECORDED,
    L_REVIEWED,
    AdaptationRecord,
    EfficiencyMetricRecord,
    FeedbackRecord,
    ForbiddenModificationError,
    IllegalLoopTransition,
    ImmutableCycleError,
    ImmutableFeedbackError,
    ImmutableProposalError,
    InvalidCategory,
    InvalidDecision,
    LoopCycleRecord,
    LoopReportRecord,
    LoopSummary,
    MissingReviewError,
    ProposalEventRecord,
    UnknownCycleError,
    UnknownProposalError,
    adaptation_id as _adaptation_id,
    can_transition,
    compare_direction,
    content_hash,
    cycle_id as _cycle_id,
    feedback_id as _feedback_id,
    input_digest,
    is_forbidden_verb,
    metric_id as _metric_id,
    proposal_event_id as _proposal_event_id,
    proposal_id as _proposal_id,
    report_id as _report_id,
)

_DISCLAIMER = ("Adaptive Research Loop 데이터 — IMPROVEMENT ≠ EXECUTION · PROPOSAL ≠ MODIFICATION · RECORDED ≠ "
               "DEPLOYMENT. 개선 기록 전용 — 자동 수정·모델/전략/권한 수정·배포 없음. 개선 제안은 인간 리뷰 기록이 "
               "필요하다.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class AdaptiveResearchLoopEngine:
    """적응 연구 루프 엔진. 불변·append-only·이벤트 소싱·결정적. 자동 수정/실행 권한 없음."""

    # ══════════════ create_adaptation_cycle (Loop Cycles) ══════════════
    def create_adaptation_cycle(self, name: str, mandate: str = "", now: str = "",
                             *, commit: bool = False) -> LoopCycleRecord:
        """루프 사이클 생성(불변). **컨테이너 등록만.**"""
        cid = _cycle_id(name)
        existing = ledger.get_cycle(cid)
        if existing is not None:
            if existing.get("mandate") != mandate:
                raise ImmutableCycleError(f"{cid} 루프 사이클 불변 — 변경 불가")
            return LoopCycleRecord(**{k: v for k, v in existing.items()
                                      if k in LoopCycleRecord.__dataclass_fields__})
        rec = LoopCycleRecord(cycle_id=cid, name=name, mandate=mandate, created_at=now,
                              input_hash=input_digest(name), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.cycle_exists(cid):
            head = ledger.cycles_head()
            ledger.append_cycle(_seal(rec, head["record_hash"] if head else GENESIS))
        return LoopCycleRecord(**rec)

    def _require_cycle(self, cid: str) -> dict:
        rec = ledger.get_cycle(cid)
        if rec is None:
            raise UnknownCycleError(f"미등록 루프 사이클 {cid}")
        return rec

    # ══════════════ create_feedback (Research Feedback) ══════════════
    def create_feedback(self, cycle: str, source_layer: str, source_ref: str, observation: str,
                     category: str = "", now: str = "", *, commit: bool = False) -> FeedbackRecord:
        """연구 피드백 기록(불변). **관찰 기록만.**"""
        self._require_cycle(cycle)
        if category and category not in ADAPTATION_CATEGORIES:
            raise InvalidCategory(f"미등록 카테고리 {category}")
        fid = _feedback_id(cycle, source_ref, observation)
        existing = ledger.get_feedback(fid)
        if existing is not None:
            return FeedbackRecord(**{k: v for k, v in existing.items()
                                     if k in FeedbackRecord.__dataclass_fields__})
        rec = FeedbackRecord(feedback_id=fid, cycle_id=cycle, source_layer=source_layer,
                             source_ref=source_ref, observation=observation, category=category,
                             created_at=now, input_hash=input_digest(cycle, source_ref, observation),
                             previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.feedback_exists(fid):
            head = ledger.feedback_head()
            ledger.append_feedback(_seal(rec, head["record_hash"] if head else GENESIS))
        return FeedbackRecord(**rec)

    # ══════════════ 제안 생애주기(event-sourced) ══════════════
    def _proposal_event(self, proposal: str, cycle: str, feedback_ref: str, category: str,
                     title: str, description: str, proposed_change: str, root_cause: str,
                     reviewer: str, decision: str, frm: str, to: str, note: str, now: str,
                     *, commit: bool) -> ProposalEventRecord:
        seq = len(ledger.proposal_events(proposal))
        eid = _proposal_event_id(proposal, to, seq)
        rec = ProposalEventRecord(
            proposal_event_id=eid, proposal_id=proposal, cycle_id=cycle, feedback_ref=feedback_ref,
            category=category, title=title, description=description, proposed_change=proposed_change,
            root_cause=root_cause, reviewer=reviewer, decision=decision, from_state=frm, to_state=to,
            note=note, occurred_at=now, input_hash=input_digest(proposal, to, seq),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.proposal_event_exists(eid):
            head = ledger.proposals_head()
            ledger.append_proposal_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return ProposalEventRecord(**rec)

    def _meta(self, proposal: str) -> dict:
        evs = ledger.proposal_events(proposal)
        if not evs:
            raise UnknownProposalError(f"미등록 제안 {proposal}")
        g = evs[0]
        return {"proposal_id": proposal, "cycle_id": g.get("cycle_id"),
                "feedback_ref": g.get("feedback_ref"), "category": g.get("category"),
                "title": g.get("title"), "description": g.get("description"),
                "proposed_change": g.get("proposed_change"), "root_cause": g.get("root_cause"),
                "state": evs[-1].get("to_state")}

    def current_state(self, proposal: str) -> str | None:
        evs = ledger.proposal_events(proposal)
        return evs[-1].get("to_state") if evs else None

    def _require_proposal(self, proposal: str) -> str:
        st = self.current_state(proposal)
        if st is None:
            raise UnknownProposalError(f"미등록 제안 {proposal}")
        return st

    def _transition(self, proposal: str, to: str, reviewer: str, decision: str, note: str, now: str,
                  *, commit: bool) -> ProposalEventRecord:
        frm = self._require_proposal(proposal)
        if not can_transition(frm, to):
            raise IllegalLoopTransition(f"{proposal} {frm}→{to} 불가")
        m = self._meta(proposal)
        return self._proposal_event(proposal, m["cycle_id"], m["feedback_ref"], m["category"],
                                    m["title"], m["description"], m["proposed_change"],
                                    m["root_cause"], reviewer, decision, frm, to, note, now,
                                    commit=commit)

    # ══════════════ analyze_failure (OBSERVED→ANALYZED) ══════════════
    def analyze_failure(self, cycle: str, feedback_ref: str, title: str, root_cause: str = "",
                     category: str = "WORKFLOW", now: str = "",
                     *, commit: bool = False) -> ProposalEventRecord:
        """실패 분석(genesis OBSERVED→ANALYZED). 근본 원인 기록. **분석·기록만.**"""
        self._require_cycle(cycle)
        if category not in ADAPTATION_CATEGORIES:
            raise InvalidCategory(f"미등록 카테고리 {category}")
        pid = _proposal_id(cycle, title)
        evs = ledger.proposal_events(pid)
        if evs:
            g = evs[0]
            if g.get("root_cause") != root_cause:
                raise ImmutableProposalError(f"{pid} 제안 불변 — 중복 변경 거부")
            return ProposalEventRecord(**{k: v for k, v in g.items()
                                          if k in ProposalEventRecord.__dataclass_fields__})
        self._proposal_event(pid, cycle, feedback_ref, category, title, "", "", root_cause, "", "",
                             GENESIS, L_OBSERVED, "observed", now, commit=commit)
        return self._proposal_event(pid, cycle, feedback_ref, category, title, "", "", root_cause,
                                    "", "", L_OBSERVED, L_ANALYZED, "analyzed", now, commit=commit)

    # ══════════════ generate_improvement (ANALYZED→PROPOSED) ══════════════
    def generate_improvement(self, proposal: str, description: str, proposed_change: str,
                          now: str = "", *, commit: bool = False) -> ProposalEventRecord:
        """개선 제안 작성(ANALYZED→PROPOSED). 금지 수정 동사 차단. **제안·기록만 — 수정 아님.**"""
        st = self._require_proposal(proposal)
        if is_forbidden_verb(proposed_change):
            raise ForbiddenModificationError(f"금지 수정 시도 {proposed_change} — 거부")
        if st != L_ANALYZED:
            raise IllegalLoopTransition(f"{proposal} ANALYZED 아님({st}) — 제안 불가")
        m = self._meta(proposal)
        return self._proposal_event(proposal, m["cycle_id"], m["feedback_ref"], m["category"],
                                    m["title"], description, proposed_change, m["root_cause"], "", "",
                                    L_ANALYZED, L_PROPOSED, "proposed", now, commit=commit)

    # ══════════════ review_improvement (PROPOSED→REVIEWED, 인간 리뷰 기록) ══════════════
    def review_improvement(self, proposal: str, reviewer: str, decision: str, now: str = "",
                        *, commit: bool = False) -> ProposalEventRecord:
        """인간 리뷰(ACCEPT/REWORK/NOTE). reviewer 필수. ACCEPT→REVIEWED, REWORK→ANALYZED. **리뷰 기록만.**"""
        st = self._require_proposal(proposal)
        if decision not in DECISIONS:
            raise InvalidDecision(f"미등록 결정 {decision}")
        if not reviewer:
            raise MissingReviewError(f"{proposal} 인간 리뷰어 누락 — 거부")
        if st != L_PROPOSED:
            raise IllegalLoopTransition(f"{proposal} PROPOSED 아님({st}) — 리뷰 불가")
        if decision == DEC_REWORK:
            return self._transition(proposal, L_ANALYZED, reviewer, decision, "rework", now,
                                    commit=commit)
        return self._transition(proposal, L_REVIEWED, reviewer, decision, "reviewed", now,
                                commit=commit)

    # ══════════════ record_outcome (REVIEWED→RECORDED, Adaptation History) ══════════════
    def record_outcome(self, proposal: str, outcome: str, evidence_ref: str = "", note: str = "",
                    now: str = "", *, commit: bool = False) -> AdaptationRecord:
        """결과 기록(REVIEWED→RECORDED) + 적응 이력. 인간 리뷰 필요. **기록만 — 자동 수정 아님.**"""
        st = self._require_proposal(proposal)
        if st != L_REVIEWED:
            raise MissingReviewError(f"{proposal} REVIEWED 아님({st}) — 인간 리뷰 후에만 결과 기록")
        m = self._meta(proposal)
        self._transition(proposal, L_RECORDED, "", "", "recorded", now, commit=commit)
        seq = len(ledger.proposal_adaptations(proposal))
        aid = _adaptation_id(proposal, seq)
        rec = AdaptationRecord(adaptation_id=aid, proposal_id=proposal, cycle_id=m["cycle_id"],
                               outcome=outcome, evidence_ref=evidence_ref, note=note, recorded_at=now,
                               input_hash=input_digest(proposal, seq),
                               previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.adaptation_exists(aid):
            head = ledger.adaptations_head()
            ledger.append_adaptation(_seal(rec, head["record_hash"] if head else GENESIS))
        return AdaptationRecord(**rec)

    def archive_proposal(self, proposal: str, now: str = "",
                      *, commit: bool = False) -> ProposalEventRecord:
        return self._transition(proposal, L_ARCHIVED, "", "", "archived", now, commit=commit)

    # ══════════════ compare_cycles (Efficiency Metrics) ══════════════
    def compare_cycles(self, cycle_a: str, cycle_b: str, metric_name: str, value_a: float,
                    value_b: float, higher_is_better: bool = True, now: str = "",
                    *, commit: bool = False) -> EfficiencyMetricRecord:
        """두 사이클 효율 비교(결정적). **분석·기록만.**"""
        self._require_cycle(cycle_a)
        self._require_cycle(cycle_b)
        direction, delta = compare_direction(value_a, value_b, higher_is_better)
        mid = _metric_id(cycle_a, cycle_b, metric_name)
        existing = ledger.get_metric(mid)
        if existing is not None:
            return EfficiencyMetricRecord(**{k: v for k, v in existing.items()
                                             if k in EfficiencyMetricRecord.__dataclass_fields__})
        rec = EfficiencyMetricRecord(metric_id=mid, cycle_a=cycle_a, cycle_b=cycle_b,
                                     metric_name=metric_name, value_a=round(float(value_a), 8),
                                     value_b=round(float(value_b), 8), delta=delta,
                                     direction=direction, compared_at=now,
                                     input_hash=input_digest(cycle_a, cycle_b, metric_name),
                                     previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.metric_exists(mid):
            head = ledger.metrics_head()
            ledger.append_metric(_seal(rec, head["record_hash"] if head else GENESIS))
        return EfficiencyMetricRecord(**rec)

    # ══════════════ generate_report ══════════════
    def generate_report(self, cycle: str, scope: str = "CYCLE", now: str = "",
                     *, commit: bool = False) -> LoopReportRecord:
        """루프 리포트(피드백·제안·리뷰·기록·메트릭·카테고리 분포). **is_binding=False, 관찰만.**"""
        self._require_cycle(cycle)
        props = ledger.cycle_proposals(cycle)
        reviewed = sum(1 for p in props
                       if self.current_state(p) in (L_REVIEWED, L_RECORDED, L_ARCHIVED))
        recorded = sum(1 for p in props if self.current_state(p) in (L_RECORDED, L_ARCHIVED))
        cat_dist: dict = {}
        for p in props:
            cat = self._meta(p)["category"]
            cat_dist[cat] = cat_dist.get(cat, 0) + 1
        metrics = [m for m in ledger.read_metrics()
                   if m.get("cycle_a") == cycle or m.get("cycle_b") == cycle]
        rid = _report_id(cycle, scope, now)
        rec = LoopReportRecord(
            report_id=rid, cycle_id=cycle, scope=scope,
            feedback_count=len(ledger.cycle_feedback(cycle)), proposal_count=len(props),
            reviewed_count=reviewed, recorded_count=recorded, metric_count=len(metrics),
            category_distribution=dict(sorted(cat_dist.items())), is_binding=False,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(cycle, scope, now),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        return LoopReportRecord(**rec)

    # ══════════════ verify_integrity ══════════════
    def verify_integrity(self) -> dict:
        from jarvis.adaptive_research_loop.verify import verify_chain
        return verify_chain()

    # ══════════════ 조회 편의 ══════════════
    def list_proposals(self, cycle: str = "") -> list:
        if cycle:
            return ledger.cycle_proposals(cycle)
        return ledger.proposal_ids()

    def proposals_in_state(self, state: str) -> list:
        return sorted(p for p in ledger.proposal_ids() if self.current_state(p) == state)

    def proposal_meta(self, proposal: str) -> dict:
        return self._meta(proposal)

    # ══════════════ Summary ══════════════
    def summary(self, now: str = "") -> LoopSummary:
        return LoopSummary(
            timestamp=now, cycle_count=len(ledger.read_cycles()),
            feedback_count=len(ledger.read_feedback()),
            proposal_event_count=len(ledger.read_proposal_events()),
            metric_count=len(ledger.read_metrics()),
            adaptation_count=len(ledger.read_adaptations()),
            report_count=len(ledger.read_reports()))
