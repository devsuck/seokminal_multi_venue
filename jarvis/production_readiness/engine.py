"""Production Readiness Engine (P21) — 배포 준비성 검증·승인 기록·전환 조건 관리. **배포·실행 없음.**

**실제 주문·live trading·portfolio mutation·capital allocation·자동 배포·자동 승인을 하지 않는다.** execution/
broker/portfolio_manager/risk_engine/permission_manager import·호출 없음. VALIDATED ≠ DEPLOYED · READY ≠ LIVE.
결정적·불변·append-only·이벤트 소싱. 상위 계층(P9.8~P20)은 READ ONLY.
"""
from __future__ import annotations

from jarvis.production_readiness import ledger
from jarvis.production_readiness import models as M
from jarvis.production_readiness.models import (
    GENESIS,
    ApprovalRequired,
    ArtifactRecord,
    DeploymentCandidateRecord,
    IllegalCandidateTransition,
    IllegalReviewTransition,
    ImmutableCandidateError,
    MissingEvidenceError,
    ReadinessCheckRecord,
    ReadinessReportRecord,
    ReadinessSummary,
    RequirementRecord,
    ReviewerRequired,
    ReviewEventRecord,
    RiskAssessmentRecord,
    TransitionRecord,
    UnknownEntityError,
    content_hash,
    input_digest,
    metadata_hash,
)

_DISCLAIMER = ("Production Readiness & Deployment Governance 데이터 — VALIDATED ≠ DEPLOYED · READY ≠ LIVE. "
               "배포 준비성 검증·승인 기록·감사 전용 — 실제 주문·live trading·portfolio mutation·capital allocation·"
               "자동 배포·자동 승인 없음. READY_FOR_DEPLOYMENT 는 연구 상태일 뿐 배포하지 않는다.")


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ProductionReadinessEngine:
    """배포 준비성 거버넌스 엔진. 불변·append-only·이벤트 소싱·결정적. 배포/실행/승격/거래/자동승인 권한 없음."""

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

    # ══════════════ 후보 상태 머신(event-sourced, pd_transitions) ══════════════
    def _transition(self, cand, frm, to, note, now, *, commit) -> TransitionRecord:
        seq = len(ledger.candidate_transitions(cand))
        tid = M.transition_id(cand, to, seq)
        rec = TransitionRecord(transition_id=tid, candidate_id=cand, from_state=frm, to_state=to,
                               note=note, occurred_at=now, input_hash=input_digest(cand, to, seq),
                               previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.transition_exists, ledger.transitions_head, ledger.append_transition,
                         tid, rec, commit=commit)
        return TransitionRecord(**rec)

    def candidate_state(self, cand) -> str | None:
        evs = ledger.candidate_transitions(cand)
        return evs[-1].get("to_state") if evs else None

    def _require_candidate(self, cand) -> str:
        st = self.candidate_state(cand)
        if st is None:
            raise UnknownEntityError(f"미등록 후보 {cand}")
        return st

    def create_transition_record(self, cand, to_state, note="", now="",
                                 *, commit=False) -> TransitionRecord:
        """후보 상태 전이 기록(검증). 유효하지 않은 전이는 차단. **기록만 — 배포 아님.**"""
        frm = self._require_candidate(cand)
        if not M.can_candidate_transition(frm, to_state):
            raise IllegalCandidateTransition(f"후보 {cand} {frm}→{to_state} 불가")
        return self._transition(cand, frm, to_state, note, now, commit=commit)

    # ══════════════ register_candidate ══════════════
    def register_candidate(self, source_layer, source_reference, strategy_reference="",
                           model_reference="", portfolio_reference="", metadata=None, now="",
                           *, commit=False) -> DeploymentCandidateRecord:
        """배포 후보 등록(불변) + genesis 전이 REGISTERED. **후보 기록만.**"""
        cid = M.candidate_id(source_layer, source_reference)
        existing = ledger.get_candidate(cid)
        if existing is not None:
            if existing.get("strategy_reference") != strategy_reference:
                raise ImmutableCandidateError(f"{cid} 후보 불변")
            return DeploymentCandidateRecord(**{k: v for k, v in existing.items()
                                                if k in DeploymentCandidateRecord.__dataclass_fields__})
        rec = DeploymentCandidateRecord(
            candidate_id=cid, source_layer=source_layer, source_reference=source_reference,
            strategy_reference=strategy_reference, model_reference=model_reference,
            portfolio_reference=portfolio_reference, metadata_hash=metadata_hash(metadata),
            created_at=now, input_hash=input_digest(source_layer, source_reference),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.candidate_exists, ledger.candidates_head, ledger.append_candidate,
                         cid, rec, commit=commit)
        self._transition(cid, GENESIS, M.S_REGISTERED, "registered", now, commit=commit)
        self._artifact(M.ART_CANDIDATE, cid, "", now, commit=commit)
        return DeploymentCandidateRecord(**rec)

    # ══════════════ create_readiness_check ══════════════
    def create_readiness_check(self, cand, category, status, evidence=None, note="", now="",
                               *, commit=False) -> ReadinessCheckRecord:
        """준비성 체크리스트 항목 기록(불변). **증거 필수(evidence_required).** 최초 체크 시 REGISTERED→CHECKING."""
        st = self._require_candidate(cand)
        if category not in M.CHECKLIST_CATEGORIES:
            raise ValueError(f"미지원 category {category}")
        if status not in M.CHECK_STATUSES:
            raise ValueError(f"미지원 status {status}")
        if not evidence:
            raise MissingEvidenceError(f"{category} 체크 증거 필수")
        if st == M.S_REGISTERED:
            self._transition(cand, st, M.S_CHECKING, "checking", now, commit=commit)
        seq = len(ledger.candidate_checks(cand))
        kid = M.check_id(cand, category, seq)
        rec = ReadinessCheckRecord(check_id=kid, candidate_id=cand, category=category, status=status,
                                   evidence=list(evidence), evidence_required=True, note=note,
                                   recorded_at=now, input_hash=input_digest(cand, category, seq),
                                   previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.check_exists, ledger.checks_head, ledger.append_check, kid, rec,
                         commit=commit)
        parent = M.artifact_id(M.ART_CANDIDATE, cand)
        self._artifact(M.ART_CHECK, kid, parent if ledger.artifact_exists(parent) else "", now,
                       commit=commit)
        return ReadinessCheckRecord(**rec)

    # ══════════════ evaluate_requirements ══════════════
    def evaluate_requirements(self, cand, requirement_type, target, actual, met, note="", now="",
                              *, commit=False) -> RequirementRecord:
        """요구사항 평가 기록(불변). **자동 승인 없음 — 충족 여부만 기록.**"""
        self._require_candidate(cand)
        if requirement_type not in M.REQUIREMENT_TYPES:
            raise ValueError(f"미지원 requirement_type {requirement_type}")
        seq = len(ledger.candidate_requirements(cand))
        qid = M.requirement_id(cand, requirement_type, seq)
        rec = RequirementRecord(requirement_id=qid, candidate_id=cand, requirement_type=requirement_type,
                                target=str(target), actual=str(actual), met=bool(met), note=note,
                                recorded_at=now, input_hash=input_digest(cand, requirement_type, seq),
                                previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.requirement_exists, ledger.requirements_head,
                         ledger.append_requirement, qid, rec, commit=commit)
        return RequirementRecord(**rec)

    # ══════════════ 준비성 게이트 전이 ══════════════
    def mark_ready_for_review(self, cand, now="", *, commit=False) -> TransitionRecord:
        """CHECKING→READY_FOR_REVIEW. 체크 ≥1 + FAILED 없음 필요. **검토 준비 표기.**"""
        checks = ledger.candidate_checks(cand)
        if not checks:
            raise IllegalCandidateTransition(f"{cand} 체크 없음 — READY_FOR_REVIEW 불가")
        if any(c.get("status") == "FAILED" for c in checks):
            raise IllegalCandidateTransition(f"{cand} FAILED 체크 존재 — READY_FOR_REVIEW 불가")
        return self.create_transition_record(cand, M.S_READY_FOR_REVIEW, "ready for review", now,
                                             commit=commit)

    def mark_reviewed(self, cand, now="", *, commit=False) -> TransitionRecord:
        """READY_FOR_REVIEW→REVIEWED. 리뷰(결정) ≥1 필요."""
        if not any(self.review_decision(r) is not None for r in ledger.candidate_reviews(cand)):
            raise IllegalCandidateTransition(f"{cand} 결정된 리뷰 없음 — REVIEWED 불가")
        return self.create_transition_record(cand, M.S_REVIEWED, "reviewed", now, commit=commit)

    def mark_ready_for_deployment(self, cand, now="", *, commit=False) -> TransitionRecord:
        """REVIEWED→READY_FOR_DEPLOYMENT. **승인된 리뷰(APPROVED, 검토자 보유) 필수 — 자동 승인 없음. 배포 아님.**"""
        approved = False
        for rev in ledger.candidate_reviews(cand):
            evs = ledger.review_events(rev)
            last = evs[-1]
            if last.get("to_state") == M.R_APPROVED and last.get("reviewer_id"):
                approved = True
                break
        if not approved:
            raise ApprovalRequired(f"{cand} 승인된(검토자 보유) 리뷰 없음 — READY_FOR_DEPLOYMENT 불가")
        return self.create_transition_record(cand, M.S_READY_FOR_DEPLOYMENT,
                                             "ready for deployment (research status only)", now,
                                             commit=commit)

    def archive_candidate(self, cand, now="", *, commit=False) -> TransitionRecord:
        return self.create_transition_record(cand, M.S_ARCHIVED, "archived", now, commit=commit)

    def send_back_to_checking(self, cand, now="", *, commit=False) -> TransitionRecord:
        """REVIEWED/READY_FOR_REVIEW → CHECKING (변경 요청/반려)."""
        return self.create_transition_record(cand, M.S_CHECKING, "back to checking", now,
                                             commit=commit)

    # ══════════════ 리뷰 생애주기(event-sourced, 사람 필수) ══════════════
    def _review_event(self, rev, cand, subject, reviewer, frm, to, decision, comments, now,
                      *, commit) -> ReviewEventRecord:
        seq = len(ledger.review_events(rev))
        eid = M.review_event_id(rev, to, seq)
        rec = ReviewEventRecord(review_event_id=eid, review_id=rev, candidate_id=cand, subject=subject,
                                reviewer_id=reviewer, from_state=frm, to_state=to, decision=decision,
                                comments=comments, is_automatic=False, occurred_at=now,
                                input_hash=input_digest(rev, to, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.review_event_exists, ledger.reviews_head, ledger.append_review_event,
                         eid, rec, commit=commit)
        return ReviewEventRecord(**rec)

    def review_state(self, rev) -> str | None:
        evs = ledger.review_events(rev)
        return evs[-1].get("to_state") if evs else None

    def review_decision(self, rev) -> str | None:
        evs = ledger.review_events(rev)
        if not evs:
            return None
        last = evs[-1].get("to_state")
        return last if last != M.R_PENDING else None

    def request_review(self, cand, subject, now="", *, commit=False) -> ReviewEventRecord:
        """리뷰 요청(genesis PENDING). **자동 승인 없음.**"""
        self._require_candidate(cand)
        rev = M.review_id(cand, subject)
        evs = ledger.review_events(rev)
        if evs:
            return ReviewEventRecord(**{k: v for k, v in evs[0].items()
                                        if k in ReviewEventRecord.__dataclass_fields__})
        ev = self._review_event(rev, cand, subject, "", GENESIS, M.R_PENDING, "PENDING", "", now,
                                commit=commit)
        parent = M.artifact_id(M.ART_CANDIDATE, cand)
        self._artifact(M.ART_REVIEW, rev, parent if ledger.artifact_exists(parent) else "", now,
                       commit=commit)
        return ev

    def record_review(self, rev, reviewer_id, decision, comments="", now="",
                      *, commit=False) -> ReviewEventRecord:
        """리뷰 결정 기록(PENDING→APPROVED/REJECTED/REQUEST_CHANGE). **검토자 필수 — 없으면 거부. 자동 승인 없음.**"""
        evs = ledger.review_events(rev)
        if not evs:
            raise UnknownEntityError(f"미등록 리뷰 {rev}")
        if not reviewer_id or not str(reviewer_id).strip():
            raise ReviewerRequired("검토자 신원 필수 — 검토자 없이 승인/결정 불가")
        to = M.normalize_decision(decision)
        if to is None:
            raise ValueError(f"미지원 decision {decision} (APPROVE/REJECT/REQUEST_CHANGE)")
        st = evs[-1].get("to_state")
        if not M.can_review_transition(st, to):
            raise IllegalReviewTransition(f"리뷰 {rev} {st}→{to} 불가")
        g = evs[0]
        return self._review_event(rev, g.get("candidate_id"), g.get("subject"), reviewer_id, st, to,
                                  decision.strip().upper(), comments, now, commit=commit)

    # ══════════════ assess_transition_risk ══════════════
    def assess_transition_risk(self, cand, level, factors=None, detail="", now="",
                               *, commit=False) -> RiskAssessmentRecord:
        """전환 리스크 평가 기록(불변). **평가·기록일 뿐 — 배포 결정 아님.**"""
        self._require_candidate(cand)
        if level not in M.RISK_LEVELS:
            raise ValueError(f"미지원 risk level {level}")
        seq = len(ledger.candidate_risks(cand))
        rid = M.risk_id(cand, seq)
        rec = RiskAssessmentRecord(risk_id=rid, candidate_id=cand, level=level,
                                   factors=list(factors or []), detail=detail, is_binding=False,
                                   recorded_at=now, input_hash=input_digest(cand, seq),
                                   previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.risk_exists, ledger.risks_head, ledger.append_risk, rid, rec,
                         commit=commit)
        return RiskAssessmentRecord(**rec)

    # ══════════════ generate_readiness_report ══════════════
    def generate_readiness_report(self, cand, scope="CANDIDATE", now="",
                                  *, commit=False) -> ReadinessReportRecord:
        """준비성 리포트(체크·요구·리뷰·리스크 집계). **deployed=False, is_binding=False — 배포하지 않는다.**"""
        self._require_candidate(cand)
        checks = ledger.candidate_checks(cand)
        cdist: dict = {}
        for c in checks:
            cdist[c.get("status")] = cdist.get(c.get("status"), 0) + 1
        reqs = ledger.candidate_requirements(cand)
        req_summary = {"total": len(reqs), "met": sum(1 for r in reqs if r.get("met")),
                       "unmet": sum(1 for r in reqs if not r.get("met"))}
        decisions = [self.review_decision(r) for r in ledger.candidate_reviews(cand)]
        decisions = [d for d in decisions if d]
        decision = decisions[-1] if decisions else "NONE"
        risks = ledger.candidate_risks(cand)
        risk_level = risks[-1].get("level") if risks else "UNKNOWN"
        rid = M.report_id(cand, scope, now)
        rec = ReadinessReportRecord(
            report_id=rid, candidate_id=cand, scope=scope, candidate_state=self.candidate_state(cand),
            check_summary=dict(sorted(cdist.items())), requirement_summary=req_summary,
            review_decision=decision, risk_level=risk_level, deployed=False, is_binding=False,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(cand, scope, now),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.report_exists, ledger.reports_head, ledger.append_report, rid, rec,
                         commit=commit)
        parent = M.artifact_id(M.ART_CANDIDATE, cand)
        self._artifact(M.ART_REPORT, rid, parent if ledger.artifact_exists(parent) else "", now,
                       commit=commit)
        return ReadinessReportRecord(**rec)

    # ══════════════ verify / 조회 / summary ══════════════
    def verify_integrity(self) -> dict:
        from jarvis.production_readiness.verify import verify_chain
        return verify_chain()

    def list_candidates(self) -> list:
        return ledger.candidate_ids()

    def candidates_in_state(self, state) -> list:
        return sorted(c for c in ledger.candidate_ids() if self.candidate_state(c) == state)

    def summary(self, now="") -> ReadinessSummary:
        return ReadinessSummary(
            timestamp=now, candidate_count=len(ledger.read_candidates()),
            transition_count=len(ledger.read_transitions()), check_count=len(ledger.read_checks()),
            requirement_count=len(ledger.read_requirements()),
            review_event_count=len(ledger.read_review_events()), risk_count=len(ledger.read_risks()),
            report_count=len(ledger.read_reports()), artifact_count=len(ledger.read_artifacts()))
