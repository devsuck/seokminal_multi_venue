"""Autonomous Research Engine (P25) — 연구 개선 루프·지식 생성. **연구 지능 전용, 동작 없음.**

**지식을 만든다 — 거래 행위를 만들지 않는다.** 실험 자동 실행·전략 배포·모델 승인·거래·자본 배분·프로덕션 수정을
하지 않는다. execution/broker/live_trading/portfolio_execution import·호출 없음. LOOP CREATES KNOWLEDGE ≠
TRADING ACTIONS · PROPOSAL ≠ APPROVAL · PLAN ≠ EXECUTION. 결정적·불변·append-only·이벤트 소싱. 상위 계층은 READ ONLY.
"""
from __future__ import annotations

from jarvis.autonomous_research import ledger
from jarvis.autonomous_research import models as M
from jarvis.autonomous_research.models import (
    GENESIS,
    ArtifactRecord,
    CycleEventRecord,
    EvolutionReportRecord,
    ExperimentPlanRecord,
    IllegalCycleTransition,
    IllegalProposalTransition,
    LearningEventRecord,
    LearningFeedbackRecord,
    OpportunityRecord,
    ProposalEventRecord,
    ResearchLoopSummary,
    ReviewerRequired,
    UnknownEntityError,
    content_hash,
    input_digest,
)

_DISCLAIMER = ("Autonomous Research Loop 데이터 — LOOP CREATES KNOWLEDGE ≠ TRADING ACTIONS · "
               "PROPOSAL ≠ APPROVAL · PLAN ≠ EXECUTION. 연구 결과 분석·기회 탐지·제안·실험 계획·학습 기록 전용 — "
               "실험 자동 실행·전략 배포·모델 승인·거래·자본 배분·프로덕션 수정 없음.")

# ── 기회 탐지: 관측 대상 → 패턴 매핑(READ ONLY) ──
_PATTERN_SOURCES = {
    "REPEATED_FAILURES": "reliability",       # rel_incidents (P24)
    "VALIDATION_WARNINGS": "monitoring",      # rmon_anomalies (P23)
    "ROBUSTNESS_ISSUES": "simulation",        # sim_scenarios (P10.8)
    "MISSING_EXPERIMENTS": "alpha_intelligence",  # ai_experiments (P10.3)
    "DUPLICATED_RESEARCH": "strategy_research_governance",  # rg_experiments (P10.2)
}


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class AutonomousResearchEngine:
    """자율 연구 루프 엔진. 불변·append-only·이벤트 소싱·결정적. 실행/거래/배포/승인/전략선택 권한 없음."""

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

    # ══════════════ 연구 사이클 생애주기(event-sourced) ══════════════
    def _cycle_event(self, cyc, objective, refs, frm, to, note, now, *, commit):
        seq = len(ledger.cycle_events(cyc))
        eid = M.cycle_event_id(cyc, to, seq)
        rec = CycleEventRecord(
            cycle_event_id=eid, cycle_id=cyc, objective=objective, source_references=list(refs),
            from_state=frm, to_state=to, note=note, occurred_at=now,
            input_hash=input_digest(cyc, to, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.cycle_event_exists, ledger.cycles_head, ledger.append_cycle_event,
                         eid, rec, commit=commit)
        return CycleEventRecord(**rec)

    def cycle_state(self, cyc) -> str | None:
        evs = ledger.cycle_events(cyc)
        return evs[-1].get("to_state") if evs else None

    def _cycle_meta(self, cyc) -> dict:
        evs = ledger.cycle_events(cyc)
        if not evs:
            raise UnknownEntityError(f"미등록 사이클 {cyc}")
        g = evs[0]
        return {"objective": g.get("objective"), "refs": g.get("source_references", []),
                "state": evs[-1].get("to_state")}

    def _cycle_transition(self, cyc, to, note, now, *, commit):
        m = self._cycle_meta(cyc)
        frm = m["state"]
        if not M.can_cycle_transition(frm, to):
            raise IllegalCycleTransition(f"사이클 {cyc} {frm}→{to} 불가")
        return self._cycle_event(cyc, m["objective"], m["refs"], frm, to, note, now, commit=commit)

    def create_cycle(self, objective, source_references=None, now="",
                     *, commit=False) -> CycleEventRecord:
        """연구 개선 사이클 생성(genesis CREATED, 이벤트 소싱). **지식 생성 — 거래 없음.**"""
        cyc = M.cycle_id(objective)
        evs = ledger.cycle_events(cyc)
        if evs:
            return CycleEventRecord(**{k: v for k, v in evs[0].items()
                                       if k in CycleEventRecord.__dataclass_fields__})
        ev = self._cycle_event(cyc, objective, source_references or [], GENESIS, M.C_CREATED,
                               "created", now, commit=commit)
        self._artifact(M.ART_CYCLE, cyc, "", now, commit=commit)
        return ev

    def start_analyzing(self, cyc, note="analyzing", now="", *, commit=False):
        return self._cycle_transition(cyc, M.C_ANALYZING, note, now, commit=commit)

    def mark_planned(self, cyc, note="planned", now="", *, commit=False):
        return self._cycle_transition(cyc, M.C_PLANNED, note, now, commit=commit)

    def start_evaluating(self, cyc, note="evaluating", now="", *, commit=False):
        return self._cycle_transition(cyc, M.C_EVALUATING, note, now, commit=commit)

    def complete_cycle(self, cyc, note="completed", now="", *, commit=False):
        return self._cycle_transition(cyc, M.C_COMPLETED, note, now, commit=commit)

    def archive_cycle(self, cyc, note="archived", now="", *, commit=False):
        return self._cycle_transition(cyc, M.C_ARCHIVED, note, now, commit=commit)

    # ══════════════ analyze_history (READ ONLY) ══════════════
    def analyze_history(self, now="") -> dict:
        """상위 계층(READ ONLY)에서 연구 이력 신호를 집계. **읽기만 — 기록·변경 없음.**"""
        signals = {}
        for pattern, layer in sorted(_PATTERN_SOURCES.items()):
            signals[pattern] = {"layer": layer, "count": ledger.source_count(layer),
                                "present": ledger.source_present(layer)}
        return {"signals": signals, "read_only": True,
                "total": sum(v["count"] for v in signals.values())}

    # ══════════════ discover_opportunity ══════════════
    def discover_opportunity(self, cyc, source_pattern, description, evidence=None,
                             severity_weight=1.0, now="", *, commit=False) -> OpportunityRecord:
        """개선 기회 탐지·기록(불변). 우선순위는 **점수만 — 자동 선택 없음(is_auto_selected=False).**"""
        if source_pattern not in M.OPPORTUNITY_PATTERNS:
            raise ValueError(f"미지원 opportunity pattern {source_pattern}")
        self._cycle_meta(cyc)  # 존재 검증
        ev = dict(evidence or {})
        score = M.priority_score(ev.get("evidence_count", 0), severity_weight)
        oid = M.opportunity_id(source_pattern, description)
        rec = OpportunityRecord(
            opportunity_id=oid, cycle_id=cyc, source_pattern=source_pattern, description=description,
            evidence=ev, priority_score=score, priority_level=M.classify_priority(score),
            is_auto_selected=False, detected_at=now,
            input_hash=input_digest(source_pattern, description), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.opportunity_exists, ledger.opportunities_head,
                         ledger.append_opportunity, oid, rec, commit=commit)
        self._artifact(M.ART_OPPORTUNITY, oid, M.artifact_id(M.ART_CYCLE, cyc), now, commit=commit)
        return OpportunityRecord(**rec)

    def detect_opportunities_from_history(self, cyc, now="", *, commit=False) -> list:
        """관측 대상 존재/카운트를 READ ONLY 스캔 → 신호 있는 패턴을 기회로 기록. **탐지·기록만.**"""
        out = []
        for pattern, layer in sorted(_PATTERN_SOURCES.items()):
            count = ledger.source_count(layer)
            if count > 0:
                out.append(self.discover_opportunity(
                    cyc, pattern, f"{pattern} signal from {layer}",
                    {"evidence_count": count, "layer": layer, "read_only": True},
                    now=now, commit=commit))
        return out

    # ══════════════ create_hypothesis (proposal, event-sourced) ══════════════
    def _proposal_event(self, prop, cyc, opp, hypothesis, expected_value, risk, req_val, frm, to,
                        reviewer, note, now, *, commit):
        seq = len(ledger.proposal_events(prop))
        eid = M.proposal_event_id(prop, to, seq)
        rec = ProposalEventRecord(
            proposal_event_id=eid, proposal_id=prop, cycle_id=cyc, opportunity_id=opp,
            hypothesis=hypothesis, expected_value=expected_value, risk=risk,
            required_validation=list(req_val), from_state=frm, to_state=to, reviewer=reviewer,
            note=note, created_at=now, input_hash=input_digest(prop, to, seq),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.proposal_event_exists, ledger.proposals_head,
                         ledger.append_proposal_event, eid, rec, commit=commit)
        return ProposalEventRecord(**rec)

    def proposal_state(self, prop) -> str | None:
        evs = ledger.proposal_events(prop)
        return evs[-1].get("to_state") if evs else None

    def _proposal_meta(self, prop) -> dict:
        evs = ledger.proposal_events(prop)
        if not evs:
            raise UnknownEntityError(f"미등록 제안 {prop}")
        g = evs[0]
        return {"cycle_id": g.get("cycle_id"), "opportunity_id": g.get("opportunity_id"),
                "hypothesis": g.get("hypothesis"), "expected_value": g.get("expected_value"),
                "risk": g.get("risk"), "required_validation": g.get("required_validation", []),
                "state": evs[-1].get("to_state")}

    def create_hypothesis(self, cyc, hypothesis, expected_value="", risk="MEDIUM",
                          required_validation=None, opportunity_id="", now="",
                          *, commit=False) -> ProposalEventRecord:
        """연구 제안(가설) 기록(genesis DRAFT, 이벤트 소싱). **초안만 — 자동 승인 없음.**"""
        self._cycle_meta(cyc)  # 존재 검증
        if risk not in M.RISK_LEVELS:
            raise ValueError(f"미지원 risk {risk}")
        prop = M.proposal_id(cyc, hypothesis)
        evs = ledger.proposal_events(prop)
        if evs:
            return ProposalEventRecord(**{k: v for k, v in evs[0].items()
                                          if k in ProposalEventRecord.__dataclass_fields__})
        ev = self._proposal_event(prop, cyc, opportunity_id, hypothesis, expected_value, risk,
                                  required_validation or [], GENESIS, M.P_DRAFT, "", "draft", now,
                                  commit=commit)
        self._artifact(M.ART_PROPOSAL, prop, M.artifact_id(M.ART_CYCLE, cyc), now, commit=commit)
        return ev

    def submit_proposal(self, prop, note="submitted", now="", *, commit=False):
        m = self._proposal_meta(prop)
        return self._proposal_transition(prop, m, M.P_SUBMITTED, "", note, now, commit=commit)

    def review_proposal(self, prop, reviewer, note="reviewed", now="", *, commit=False):
        if not reviewer:
            raise ReviewerRequired("제안 검토는 reviewer 필수")
        m = self._proposal_meta(prop)
        return self._proposal_transition(prop, m, M.P_REVIEWED, reviewer, note, now, commit=commit)

    def accept_proposal(self, prop, reviewer, note="accepted", now="", *, commit=False):
        """제안 수락(REVIEWED→ACCEPTED). **사람 검토(reviewer) 필수 — 자동 승인 금지. ACCEPTED ≠ 배포/거래.**"""
        if not reviewer:
            raise ReviewerRequired("제안 수락은 reviewer 필수")
        m = self._proposal_meta(prop)
        return self._proposal_transition(prop, m, M.P_ACCEPTED, reviewer, note, now, commit=commit)

    def reject_proposal(self, prop, reviewer, note="rejected", now="", *, commit=False):
        """제안 거절(REVIEWED→REJECTED). **사람 검토(reviewer) 필수.**"""
        if not reviewer:
            raise ReviewerRequired("제안 거절은 reviewer 필수")
        m = self._proposal_meta(prop)
        return self._proposal_transition(prop, m, M.P_REJECTED, reviewer, note, now, commit=commit)

    def _proposal_transition(self, prop, m, to, reviewer, note, now, *, commit):
        frm = m["state"]
        if not M.can_proposal_transition(frm, to):
            raise IllegalProposalTransition(f"제안 {prop} {frm}→{to} 불가")
        return self._proposal_event(prop, m["cycle_id"], m["opportunity_id"], m["hypothesis"],
                                    m["expected_value"], m["risk"], m["required_validation"], frm, to,
                                    reviewer, note, now, commit=commit)

    # ══════════════ generate_plan (계획만, 실행 없음) ══════════════
    def generate_plan(self, prop, datasets=None, features=None, validation_requirements=None,
                      success_metrics=None, now="", *, commit=False) -> ExperimentPlanRecord:
        """실험 계획 기록(불변). **계획만 — 자동 실행 없음(is_executable=False).**"""
        self._proposal_meta(prop)  # 존재 검증
        seq = len(ledger.plans_for(prop))
        pid = M.experiment_plan_id(prop, seq)
        rec = ExperimentPlanRecord(
            plan_id=pid, proposal_id=prop, datasets=list(datasets or []),
            features=list(features or []), validation_requirements=list(validation_requirements or []),
            success_metrics=list(success_metrics or []), is_executable=False, created_at=now,
            input_hash=input_digest(prop, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.plan_exists, ledger.plans_head, ledger.append_plan, pid, rec,
                         commit=commit)
        self._artifact(M.ART_PLAN, pid, M.artifact_id(M.ART_PROPOSAL, prop), now, commit=commit)
        return ExperimentPlanRecord(**rec)

    # ══════════════ record_feedback ══════════════
    def record_feedback(self, cyc, result_summary, lessons=None, future_direction="", now="",
                        *, commit=False) -> LearningFeedbackRecord:
        """학습 피드백 기록(불변). **기록만.**"""
        self._cycle_meta(cyc)  # 존재 검증
        seq = len(ledger.feedback_for(cyc))
        fid = M.feedback_id(cyc, seq)
        rec = LearningFeedbackRecord(
            feedback_id=fid, cycle_id=cyc, result_summary=result_summary, lessons=list(lessons or []),
            future_direction=future_direction, created_at=now, input_hash=input_digest(cyc, seq),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.feedback_exists, ledger.feedback_head, ledger.append_feedback, fid,
                         rec, commit=commit)
        self._artifact(M.ART_FEEDBACK, fid, M.artifact_id(M.ART_CYCLE, cyc), now, commit=commit)
        return LearningFeedbackRecord(**rec)

    # ══════════════ update_learning_history ══════════════
    def update_learning_history(self, cyc, kind, pattern, evidence=None, now="",
                                *, commit=False) -> LearningEventRecord:
        """학습 이벤트 기록(불변). kind ∈ SUCCESSFUL/FAILED/RESEARCH_LESSON. **저장만.**"""
        self._cycle_meta(cyc)  # 존재 검증
        if kind not in M.LEARNING_KINDS:
            raise ValueError(f"미지원 learning kind {kind}")
        seq = len([r for r in ledger.learning_for(cyc) if r.get("kind") == kind])
        lid = M.learning_event_id(cyc, kind, seq)
        rec = LearningEventRecord(
            learning_event_id=lid, cycle_id=cyc, kind=kind, pattern=pattern,
            evidence=dict(evidence or {}), created_at=now, input_hash=input_digest(cyc, kind, seq),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.learning_exists, ledger.learning_head, ledger.append_learning, lid,
                         rec, commit=commit)
        return LearningEventRecord(**rec)

    # ══════════════ generate_report ══════════════
    def generate_report(self, scope="SYSTEM", now="", *, commit=False) -> EvolutionReportRecord:
        """진화 리포트(사이클·기회·제안·계획·학습 집계). **is_binding=False, KNOWLEDGE ≠ TRADING.**"""
        cycles = ledger.cycle_ids()
        states = {c: self.cycle_state(c) for c in cycles}
        opportunities = ledger.read_opportunities()
        proposals = ledger.proposal_ids()
        accepted = sum(1 for p in proposals if self.proposal_state(p) == M.P_ACCEPTED)
        learning = ledger.read_learning_events()
        pat_dist: dict = {}
        for o in opportunities:
            pat_dist[o.get("source_pattern")] = pat_dist.get(o.get("source_pattern"), 0) + 1
        learn_dist: dict = {}
        for le in learning:
            learn_dist[le.get("kind")] = learn_dist.get(le.get("kind"), 0) + 1
        rid = M.report_id(scope, now)
        rec = EvolutionReportRecord(
            report_id=rid, scope=scope, cycle_count=len(cycles),
            active_cycle_count=sum(1 for st in states.values()
                                   if st in (M.C_CREATED, M.C_ANALYZING, M.C_PLANNED, M.C_EVALUATING)),
            completed_cycle_count=sum(1 for st in states.values()
                                      if st in (M.C_COMPLETED, M.C_ARCHIVED)),
            opportunity_count=len(opportunities), proposal_count=len(proposals),
            accepted_proposal_count=accepted, experiment_plan_count=len(ledger.read_experiment_plans()),
            feedback_count=len(ledger.read_feedback()), learning_event_count=len(learning),
            pattern_distribution=dict(sorted(pat_dist.items())),
            learning_distribution=dict(sorted(learn_dist.items())), is_binding=False,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(scope, now),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.report_exists, ledger.reports_head, ledger.append_report, rid, rec,
                         commit=commit)
        self._artifact(M.ART_REPORT, rid, "", now, commit=commit)
        return EvolutionReportRecord(**rec)

    # ══════════════ verify / 조회 / summary ══════════════
    def verify_integrity(self) -> dict:
        from jarvis.autonomous_research.verify import verify_chain
        return verify_chain()

    def list_cycles(self) -> list:
        return ledger.cycle_ids()

    def cycles_in_state(self, state) -> list:
        return sorted(c for c in ledger.cycle_ids() if self.cycle_state(c) == state)

    def list_proposals(self) -> list:
        return ledger.proposal_ids()

    def summary(self, now="") -> ResearchLoopSummary:
        return ResearchLoopSummary(
            timestamp=now, cycle_event_count=len(ledger.read_cycle_events()),
            cycle_count=len(ledger.cycle_ids()), opportunity_count=len(ledger.read_opportunities()),
            proposal_event_count=len(ledger.read_proposal_events()),
            proposal_count=len(ledger.proposal_ids()),
            experiment_plan_count=len(ledger.read_experiment_plans()),
            feedback_count=len(ledger.read_feedback()),
            learning_event_count=len(ledger.read_learning_events()),
            report_count=len(ledger.read_reports()), artifact_count=len(ledger.read_artifacts()))
