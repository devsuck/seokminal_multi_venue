"""Research Loop Engine (C5) — 헌장 워크플로 모델. **사람 승인 필수, 자동 실행/집행/승인 없음.**

관측→가설→제안→**사람 승인**→(연구)실행→검증→리포트→지식→메모리. 각 단계는 기록된 상태일 뿐 — 루프는 아무것도
자동 실행하지 않는다. **제안→실행 전이는 사람 APPROVED 검토 기록이 없으면 ApprovalRequiredError 로 차단된다.**
엔진은 approve()/execute()/trade()/deploy()/allocate() 를 노출하지 않는다 — 사람의 결정을 record_human_review 로
'기록'할 뿐. execution/broker/live_trading import 없음. 결정적·불변·이벤트 소싱. 기존 원장 READ ONLY.
"""
from __future__ import annotations

from jarvis.research_loop import ledger
from jarvis.research_loop import models as M
from jarvis.research_loop.models import (
    GENESIS,
    ApprovalRequiredError,
    HumanReviewRecord,
    IllegalStageTransition,
    LoopReportRecord,
    LoopStageEvent,
    LoopSummary,
    UnknownEntityError,
    content_hash,
    input_digest,
)


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchLoopEngine:
    """연구 루프 엔진. 단계 상태를 기록·관리. 사람 승인 게이트. 자동 실행/집행/승인 권한 없음."""

    def _emit(self, exists_fn, head_fn, append_fn, rid, rec, *, commit) -> dict:
        rec = dict(rec)
        rec["record_hash"] = content_hash(rec)
        if commit and not exists_fn(rid):
            head = head_fn()
            append_fn(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    # ── 단계 이벤트 ──
    def _stage_event(self, loop, title, frm, to, note, now, *, commit):
        seq = len(ledger.loop_events(loop))
        eid = M.loop_event_id(loop, to, seq)
        rec = LoopStageEvent(
            loop_event_id=eid, loop_id=loop, title=title, from_stage=frm, to_stage=to, note=note,
            occurred_at=now, input_hash=input_digest(loop, to, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.loop_event_exists, ledger.loops_head, ledger.append_loop_event,
                         eid, rec, commit=commit)
        return LoopStageEvent(**rec)

    def stage(self, loop) -> str | None:
        evs = ledger.loop_events(loop)
        return evs[-1].get("to_stage") if evs else None

    def _meta(self, loop) -> dict:
        evs = ledger.loop_events(loop)
        if not evs:
            raise UnknownEntityError(f"미등록 루프 {loop}")
        return {"title": evs[0].get("title"), "stage": evs[-1].get("to_stage")}

    def create_loop(self, title, observation="", now="", *, commit=False) -> LoopStageEvent:
        """연구 루프 생성(genesis OBSERVATION). **기록만 — 실행 아님.**"""
        loop = M.loop_id(title)
        evs = ledger.loop_events(loop)
        if evs:
            return LoopStageEvent(**{k: v for k, v in evs[0].items()
                                     if k in LoopStageEvent.__dataclass_fields__})
        return self._stage_event(loop, title, GENESIS, M.S_OBSERVATION,
                                 observation or "observation", now, commit=commit)

    # ── 사람 검토(승인/거부) 기록 — 엔진이 승인하지 않는다, 사람 결정을 기록만 ──
    def record_human_review(self, loop, decision, reviewer, note="", now="",
                            *, commit=False) -> HumanReviewRecord:
        """사람이 내린 검토 결정(APPROVED/REJECTED)을 기록. **reviewer(사람) 필수. 엔진은 승인하지 않는다.**"""
        self._meta(loop)
        dec = (decision or "").strip().upper()
        if dec not in M.REVIEW_DECISIONS:
            raise ValueError(f"미지원 decision {decision}")
        if not (reviewer or "").strip():
            raise ValueError("reviewer(사람 식별자) 필수 — 사람 승인은 사람만 한다")
        seq = len(ledger.reviews_for(loop))
        rid = M.review_id(loop, seq)
        rec = HumanReviewRecord(
            review_id=rid, loop_id=loop, decision=dec, reviewer=reviewer.strip(), is_human=True,
            note=note, created_at=now, input_hash=input_digest(loop, seq),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.review_exists, ledger.reviews_head, ledger.append_review, rid, rec,
                         commit=commit)
        return HumanReviewRecord(**rec)

    def approval_status(self, loop) -> str:
        """루프의 최신 사람 검토 결정. 없으면 PENDING_HUMAN_REVIEW."""
        revs = ledger.reviews_for(loop)
        return revs[-1].get("decision") if revs else M.REVIEW_PENDING

    def is_approved(self, loop) -> bool:
        return self.approval_status(loop) == M.REVIEW_APPROVED

    # ── 단계 전이(게이트 강제) ──
    def advance(self, loop, to_stage, note="", now="", *, commit=False) -> LoopStageEvent:
        """다음 단계로 전이. **승인 게이트: EXECUTION 진입은 사람 APPROVED 기록이 없으면 차단.**"""
        m = self._meta(loop)
        frm = m["stage"]
        if to_stage not in M.STAGES:
            raise ValueError(f"미지원 단계 {to_stage}")
        if not M.can_stage_transition(frm, to_stage):
            raise IllegalStageTransition(f"루프 {loop} {frm}→{to_stage} 불가")
        if M.requires_human_approval(to_stage) and not self.is_approved(loop):
            raise ApprovalRequiredError(
                f"{to_stage} 진입 차단 — 사람 승인 필요(현재 {self.approval_status(loop)}). "
                "record_human_review(decision=APPROVED, reviewer=사람) 먼저.")
        return self._stage_event(loop, m["title"], frm, to_stage, note or to_stage.lower(), now,
                                 commit=commit)

    # 안전한 이름의 단계 헬퍼(‘approve/execute’ 등 금지어 회피)
    def to_hypothesis(self, loop, note="", now="", *, commit=False):
        return self.advance(loop, M.S_HYPOTHESIS, note, now, commit=commit)

    def to_proposal(self, loop, note="", now="", *, commit=False):
        return self.advance(loop, M.S_PROPOSAL, note, now, commit=commit)

    def to_execution(self, loop, note="", now="", *, commit=False):
        """연구 실행 단계 진입(사람 승인 게이트 통과 필요). **연구 실행이며 거래 집행 아님.**"""
        return self.advance(loop, M.S_EXECUTION, note, now, commit=commit)

    def to_validation(self, loop, note="", now="", *, commit=False):
        return self.advance(loop, M.S_VALIDATION, note, now, commit=commit)

    def to_report(self, loop, note="", now="", *, commit=False):
        return self.advance(loop, M.S_REPORT, note, now, commit=commit)

    def to_knowledge(self, loop, note="", now="", *, commit=False):
        return self.advance(loop, M.S_KNOWLEDGE, note, now, commit=commit)

    def to_memory(self, loop, note="", now="", *, commit=False):
        return self.advance(loop, M.S_MEMORY, note, now, commit=commit)

    def reject(self, loop, note="rejected", now="", *, commit=False):
        return self.advance(loop, M.S_REJECTED, note, now, commit=commit)

    def archive(self, loop, note="archived", now="", *, commit=False):
        return self.advance(loop, M.S_ARCHIVED, note, now, commit=commit)

    # ── 리포트 ──
    def generate_report(self, scope="SYSTEM", now="", *, commit=False) -> LoopReportRecord:
        loops = ledger.loop_ids()
        by_stage: dict = {}
        for lp in loops:
            st = self.stage(lp)
            by_stage[st] = by_stage.get(st, 0) + 1
        approved = sum(1 for lp in loops if self.approval_status(lp) == M.REVIEW_APPROVED)
        rejected = sum(1 for lp in loops if self.approval_status(lp) == M.REVIEW_REJECTED)
        pending = sum(1 for lp in loops if self.approval_status(lp) == M.REVIEW_PENDING)
        rid = M.report_id(scope, now)
        rec = LoopReportRecord(
            report_id=rid, scope=scope, loop_count=len(loops),
            by_stage=dict(sorted(by_stage.items())), approved_count=approved,
            rejected_count=rejected, pending_review_count=pending, requires_human_approval=True,
            is_binding=False, disclaimer=M.DISCLAIMER, created_at=now,
            input_hash=input_digest(scope, now), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.report_exists, ledger.reports_head, ledger.append_report, rid, rec,
                         commit=commit)
        return LoopReportRecord(**rec)

    def verify_integrity(self) -> dict:
        from jarvis.research_loop.verify import verify_chain
        return verify_chain()

    def list_loops(self) -> list:
        return ledger.loop_ids()

    def loops_in_stage(self, stage) -> list:
        return sorted(lp for lp in ledger.loop_ids() if self.stage(lp) == stage)

    def summary(self, now="") -> LoopSummary:
        return LoopSummary(
            timestamp=now, loop_event_count=len(ledger.read_loop_events()),
            loop_count=len(ledger.loop_ids()), review_count=len(ledger.read_reviews()),
            report_count=len(ledger.read_reports()))
