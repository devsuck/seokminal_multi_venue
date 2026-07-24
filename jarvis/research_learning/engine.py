"""Research Learning Loop Engine (P12.8) — 통제된 피드백 분석. **관찰·분석·기록 전용.**

"무엇이 통했나 / 실패했나 / 조사할까"를 분석한다. **자동 개선을 하지 않는다.** execution/broker/portfolio/risk/
permission/deployment/live import·호출 없음. 개선 후보는 기록만 하며 절대 자동 적용하지 않는다. LEARNING ≠
MODIFICATION · LESSON ≠ APPLICATION · CANDIDATE ≠ EXECUTION. 결정적·불변·append-only·이벤트 소싱.
"""
from __future__ import annotations

from jarvis.research_learning import ledger
from jarvis.research_learning.models import (
    ART_LESSON,
    ART_LOOP,
    GENESIS,
    L_ANALYZED,
    L_ARCHIVED,
    L_LESSON_CREATED,
    L_OBSERVED,
    L_REVIEWED,
    OBS_VERDICTS,
    ArtifactRecord,
    FeedbackRecord,
    ForbiddenAutoActionError,
    IllegalLearningTransition,
    ImmutableFeedbackError,
    ImmutableImprovementError,
    ImmutableLessonError,
    ImmutableLoopError,
    ImmutableObservationError,
    ImprovementCandidateRecord,
    InvalidVerdict,
    LearningReportRecord,
    LearningSummary,
    LessonRecord,
    LoopEventRecord,
    ObservationRecord,
    PatternRecord,
    UnknownLoopError,
    artifact_id as _artifact_id,
    can_transition,
    compare_direction,
    content_hash,
    feedback_id as _feedback_id,
    improvement_id as _improvement_id,
    input_digest,
    is_forbidden_verb,
    lesson_id as _lesson_id,
    loop_event_id as _loop_event_id,
    loop_id as _loop_id,
    observation_id as _observation_id,
    pattern_id as _pattern_id,
    report_id as _report_id,
)

_DISCLAIMER = ("Research Learning Loop 데이터 — LEARNING ≠ MODIFICATION · LESSON ≠ APPLICATION · CANDIDATE ≠ "
               "EXECUTION. 통제된 피드백 분석·기록 전용 — 자동 개선·전략/모델 수정·배포·실행 없음. 개선 후보는 "
               "기록만 하며 절대 자동 적용하지 않는다.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchLearningLoopEngine:
    """연구 학습 루프 엔진. 불변·append-only·이벤트 소싱·결정적. 자동 수정/실행 권한 없음."""

    # ══════════════ 아티팩트 계보(내부) ══════════════
    def _artifact(self, atype: str, ref: str, parent: str, now: str,
                *, commit: bool) -> ArtifactRecord:
        aid = _artifact_id(atype, ref)
        rec = ArtifactRecord(artifact_id=aid, artifact_type=atype, ref_id=ref,
                             parent_artifact=parent, created_at=now,
                             input_hash=input_digest(atype, ref), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return ArtifactRecord(**rec)

    # ══════════════ 루프 생애주기(event-sourced) ══════════════
    def _loop_event(self, loop: str, name: str, scope: str, frm: str, to: str, note: str, now: str,
                 *, commit: bool) -> LoopEventRecord:
        seq = len(ledger.loop_events(loop))
        eid = _loop_event_id(loop, to, seq)
        rec = LoopEventRecord(loop_event_id=eid, loop_id=loop, name=name, scope=scope, from_state=frm,
                              to_state=to, note=note, occurred_at=now,
                              input_hash=input_digest(loop, to, seq),
                              previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.loop_event_exists(eid):
            head = ledger.loops_head()
            ledger.append_loop_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return LoopEventRecord(**rec)

    def _meta(self, loop: str) -> dict:
        evs = ledger.loop_events(loop)
        if not evs:
            raise UnknownLoopError(f"미등록 루프 {loop}")
        g = evs[0]
        return {"loop_id": loop, "name": g.get("name"), "scope": g.get("scope"),
                "state": evs[-1].get("to_state")}

    def current_state(self, loop: str) -> str | None:
        evs = ledger.loop_events(loop)
        return evs[-1].get("to_state") if evs else None

    def _require_loop(self, loop: str) -> str:
        st = self.current_state(loop)
        if st is None:
            raise UnknownLoopError(f"미등록 루프 {loop}")
        return st

    def _transition(self, loop: str, to: str, note: str, now: str,
                  *, commit: bool) -> LoopEventRecord:
        frm = self._require_loop(loop)
        if not can_transition(frm, to):
            raise IllegalLearningTransition(f"{loop} {frm}→{to} 불가")
        m = self._meta(loop)
        return self._loop_event(loop, m["name"], m["scope"], frm, to, note, now, commit=commit)

    # ══════════════ create_learning_cycle (Learning Loop Registry) ══════════════
    def create_learning_cycle(self, name: str, scope: str = "", now: str = "",
                           *, commit: bool = False) -> LoopEventRecord:
        """학습 루프 생성(genesis OBSERVED). **분석 시작만.**"""
        lid = _loop_id(name)
        evs = ledger.loop_events(lid)
        if evs:
            g = evs[0]
            if g.get("scope") != scope:
                raise ImmutableLoopError(f"{lid} 루프 불변 — 변경 불가")
            return LoopEventRecord(**{k: v for k, v in g.items()
                                      if k in LoopEventRecord.__dataclass_fields__})
        ev = self._loop_event(lid, name, scope, GENESIS, L_OBSERVED, "observed", now, commit=commit)
        self._artifact(ART_LOOP, lid, "", now, commit=commit)
        return ev

    # ══════════════ observe_research (OBSERVED→ANALYZED, Observation Records) ══════════════
    def observe_research(self, loop: str, source_layer: str, source_ref: str, observation: str,
                      verdict: str, now: str = "", *, commit: bool = False) -> ObservationRecord:
        """연구 관찰 기록(불변, 무엇이 통했나/실패했나/조사할까) + OBSERVED→ANALYZED. **관찰·기록만.**"""
        st = self._require_loop(loop)
        if verdict not in OBS_VERDICTS:
            raise InvalidVerdict(f"미등록 판정 {verdict}")
        oid = _observation_id(loop, source_ref, observation)
        existing = ledger.get_observation(oid)
        if existing is not None:
            if existing.get("verdict") != verdict:
                raise ImmutableObservationError(f"{oid} 관찰 불변 — 변경 불가")
            return ObservationRecord(**{k: v for k, v in existing.items()
                                        if k in ObservationRecord.__dataclass_fields__})
        rec = ObservationRecord(observation_id=oid, loop_id=loop, source_layer=source_layer,
                                source_ref=source_ref, observation=observation, verdict=verdict,
                                recorded_at=now, input_hash=input_digest(loop, source_ref, observation),
                                previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.observation_exists(oid):
            head = ledger.observations_head()
            ledger.append_observation(_seal(rec, head["record_hash"] if head else GENESIS))
        if st == L_OBSERVED:
            self._transition(loop, L_ANALYZED, "analyzed", now, commit=commit)
        return ObservationRecord(**rec)

    # ══════════════ extract_lesson (ANALYZED→LESSON_CREATED, Lesson Records) ══════════════
    def extract_lesson(self, loop: str, title: str, lesson: str = "", category: str = "",
                    evidence_ref: str = "", now: str = "",
                    *, commit: bool = False) -> LessonRecord:
        """교훈 추출(불변) + ANALYZED→LESSON_CREATED. **분석·기록만.**"""
        st = self._require_loop(loop)
        lid = _lesson_id(loop, title)
        existing = ledger.get_lesson(lid)
        if existing is not None:
            if existing.get("lesson") != lesson:
                raise ImmutableLessonError(f"{lid} 교훈 불변 — 변경 불가")
            return LessonRecord(**{k: v for k, v in existing.items()
                                   if k in LessonRecord.__dataclass_fields__})
        if st == L_ANALYZED:
            self._transition(loop, L_LESSON_CREATED, "lesson_created", now, commit=commit)
        elif st != L_LESSON_CREATED:
            raise IllegalLearningTransition(f"{loop} ANALYZED 아님({st}) — 교훈 추출 불가")
        rec = LessonRecord(lesson_id=lid, loop_id=loop, title=title, lesson=lesson,
                           category=category, evidence_ref=evidence_ref, created_at=now,
                           input_hash=input_digest(loop, title), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.lesson_exists(lid):
            head = ledger.lessons_head()
            ledger.append_lesson(_seal(rec, head["record_hash"] if head else GENESIS))
        self._artifact(ART_LESSON, lid, _artifact_id(ART_LOOP, loop)
                       if ledger.artifact_exists(_artifact_id(ART_LOOP, loop)) else "", now,
                       commit=commit)
        return LessonRecord(**rec)

    # ══════════════ record_improvement_candidate (record only, never applied) ══════════════
    def record_improvement_candidate(self, loop: str, title: str, description: str = "",
                                  rationale: str = "", reviewer: str = "", now: str = "",
                                  *, commit: bool = False) -> ImprovementCandidateRecord:
        """개선 후보 기록(불변, **applied=False 고정 — 절대 자동 적용 안 함**). 금지 자동 동사 차단. **기록만.**"""
        self._require_loop(loop)
        if is_forbidden_verb(description) or is_forbidden_verb(title):
            raise ForbiddenAutoActionError(f"자동 수정/실행 시도 — 거부: {title}/{description}")
        iid = _improvement_id(loop, title)
        existing = ledger.get_improvement(iid)
        if existing is not None:
            if existing.get("description") != description:
                raise ImmutableImprovementError(f"{iid} 개선 후보 불변 — 변경 불가")
            return ImprovementCandidateRecord(
                **{k: v for k, v in existing.items()
                   if k in ImprovementCandidateRecord.__dataclass_fields__})
        rec = ImprovementCandidateRecord(
            improvement_id=iid, loop_id=loop, title=title, description=description,
            rationale=rationale, applied=False, reviewer=reviewer, created_at=now,
            input_hash=input_digest(loop, title), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.improvement_exists(iid):
            head = ledger.improvements_head()
            ledger.append_improvement(_seal(rec, head["record_hash"] if head else GENESIS))
        return ImprovementCandidateRecord(**rec)

    # ══════════════ record_feedback (Feedback Records) ══════════════
    def record_feedback(self, loop: str, source: str, feedback: str, sentiment: str = "NEUTRAL",
                     now: str = "", *, commit: bool = False) -> FeedbackRecord:
        """피드백 기록(불변). **기록만.**"""
        self._require_loop(loop)
        seq = len(ledger.loop_feedback(loop))
        fid = _feedback_id(loop, source, seq)
        rec = FeedbackRecord(feedback_id=fid, loop_id=loop, source=source, feedback=feedback,
                             sentiment=sentiment, recorded_at=now,
                             input_hash=input_digest(loop, source, seq),
                             previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.feedback_exists(fid):
            head = ledger.feedback_head()
            ledger.append_feedback(_seal(rec, head["record_hash"] if head else GENESIS))
        return FeedbackRecord(**rec)

    def review_loop(self, loop: str, now: str = "", *, commit: bool = False) -> LoopEventRecord:
        """루프 리뷰(LESSON_CREATED→REVIEWED). **상태 기록만.**"""
        return self._transition(loop, L_REVIEWED, "reviewed", now, commit=commit)

    def archive_loop(self, loop: str, now: str = "", *, commit: bool = False) -> LoopEventRecord:
        return self._transition(loop, L_ARCHIVED, "archived", now, commit=commit)

    # ══════════════ compare_cycles (Learning Patterns) ══════════════
    def compare_cycles(self, loop_a: str, loop_b: str, metric_name: str, value_a: float,
                    value_b: float, higher_is_better: bool = True, now: str = "",
                    *, commit: bool = False) -> PatternRecord:
        """두 학습 사이클 비교(결정적 패턴). **분석·기록만.**"""
        self._require_loop(loop_a)
        self._require_loop(loop_b)
        direction, delta = compare_direction(value_a, value_b, higher_is_better)
        pid = _pattern_id(loop_a, loop_b, metric_name)
        existing = ledger.get_pattern(pid)
        if existing is not None:
            return PatternRecord(**{k: v for k, v in existing.items()
                                    if k in PatternRecord.__dataclass_fields__})
        rec = PatternRecord(pattern_id=pid, loop_a=loop_a, loop_b=loop_b, metric_name=metric_name,
                            value_a=round(float(value_a), 8), value_b=round(float(value_b), 8),
                            delta=delta, direction=direction, compared_at=now,
                            input_hash=input_digest(loop_a, loop_b, metric_name),
                            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.pattern_exists(pid):
            head = ledger.patterns_head()
            ledger.append_pattern(_seal(rec, head["record_hash"] if head else GENESIS))
        return PatternRecord(**rec)

    # ══════════════ generate_learning_report ══════════════
    def generate_learning_report(self, loop: str, scope: str = "LOOP", now: str = "",
                              *, commit: bool = False) -> LearningReportRecord:
        """학습 리포트(관찰·교훈·개선후보·피드백·판정 분포). **is_binding=False, 분석만.**"""
        self._require_loop(loop)
        obs = ledger.loop_observations(loop)
        verdict_dist: dict = {}
        for o in obs:
            verdict_dist[o.get("verdict")] = verdict_dist.get(o.get("verdict"), 0) + 1
        rid = _report_id(loop, scope, now)
        rec = LearningReportRecord(
            report_id=rid, loop_id=loop, scope=scope, observation_count=len(obs),
            lesson_count=len(ledger.loop_lessons(loop)),
            improvement_count=len(ledger.loop_improvements(loop)),
            feedback_count=len(ledger.loop_feedback(loop)),
            verdict_distribution=dict(sorted(verdict_dist.items())), is_binding=False,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(loop, scope, now),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        return LearningReportRecord(**rec)

    # ══════════════ verify_integrity ══════════════
    def verify_integrity(self) -> dict:
        from jarvis.research_learning.verify import verify_chain
        return verify_chain()

    # ══════════════ 조회 편의 ══════════════
    def list_loops(self) -> list:
        return ledger.loop_ids()

    def loops_in_state(self, state: str) -> list:
        return sorted(x for x in ledger.loop_ids() if self.current_state(x) == state)

    def loop_meta(self, loop: str) -> dict:
        return self._meta(loop)

    # ══════════════ Summary ══════════════
    def summary(self, now: str = "") -> LearningSummary:
        return LearningSummary(
            timestamp=now, loop_event_count=len(ledger.read_loop_events()),
            observation_count=len(ledger.read_observations()),
            lesson_count=len(ledger.read_lessons()),
            improvement_count=len(ledger.read_improvements()),
            feedback_count=len(ledger.read_feedback()), pattern_count=len(ledger.read_patterns()),
            report_count=len(ledger.read_reports()), artifact_count=len(ledger.read_artifacts()))
