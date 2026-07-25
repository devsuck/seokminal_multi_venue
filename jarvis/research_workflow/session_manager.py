"""Research Session Manager (P66) — 연구를 **지속**시킨다. **조율/상태만, 실행 없음.**

세션 생성/재개/일시정지/보관 + 목표·진행·대기작업·완료실험·교훈·미해결질문 추적. append-only 이벤트 소싱
(rwf_sessions)으로 상태를 보존해 "어제 하던 연구 계속"이 가능하다. 실험/지식 실제 저장은 기존 원장이 담당 —
이 원장은 세션 조율 상태만. 자동 실행·집행 없음.
"""
from __future__ import annotations

from jarvis.research_workflow import ledger
from jarvis.research_workflow import models as M
from jarvis.research_workflow.models import (
    GENESIS,
    SESS_ACTIVE,
    SESS_ARCHIVED,
    SESS_PAUSED,
    SessionEvent,
    SessionState,
    content_digest,
    content_hash,
    input_digest,
)


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


def _extend(dst: list, items, seen: set):
    for it in (items or []):
        key = str(it)
        if key not in seen:
            seen.add(key)
            dst.append(it)


class ResearchSessionManager:
    """연구 세션 생애주기 + 상태 추적. 이벤트 소싱. 실행 권한 없음."""

    def _emit(self, sess_id, goal, kind, to_state, payload, note, now, commit) -> dict:
        events = ledger.session_events(sess_id)
        seq = len(events)
        eid = M.session_event_id(sess_id, kind, seq)
        rec = SessionEvent(
            event_id=eid, session_id=sess_id, kind=kind, to_state=to_state,
            payload_digest=content_digest(payload or {}), note=note, occurred_at=now,
            input_hash=input_digest(sess_id, kind, seq), previous_hash=GENESIS).to_dict()
        rec["payload"] = payload or {}           # 상태 재구성을 위해 페이로드 인라인 보존
        rec["goal"] = goal
        rec["record_hash"] = content_hash(rec)
        if commit:
            head = ledger.sessions_head()
            ledger.append_session(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def create_session(self, goal, *, goals=None, now="", commit=False) -> SessionState:
        sess_id = M.session_id(str(goal))
        if not ledger.session_events(sess_id):
            self._emit(sess_id, str(goal), "CREATE", SESS_ACTIVE,
                       {"goals": goals or [str(goal)]}, "session created", now, commit)
        return self.state(sess_id)

    def update_progress(self, sess_id, *, progress=None, pending=None,
                        completed_experiments=None, lessons=None, open_questions=None,
                        resolved_questions=None, goals=None, now="", commit=False) -> SessionState:
        payload = {"progress": progress or [], "pending": pending or [],
                   "completed_experiments": completed_experiments or [],
                   "lessons": lessons or [], "open_questions": open_questions or [],
                   "resolved_questions": resolved_questions or [], "goals": goals or []}
        goal = (ledger.session_events(sess_id) or [{}])[0].get("goal", "")
        self._emit(sess_id, goal, "PROGRESS", self._current_state(sess_id), payload,
                   "progress recorded", now, commit)
        return self.state(sess_id)

    def pause_session(self, sess_id, note="", *, now="", commit=False) -> SessionState:
        goal = (ledger.session_events(sess_id) or [{}])[0].get("goal", "")
        self._emit(sess_id, goal, "PAUSE", SESS_PAUSED, {}, note or "paused", now, commit)
        return self.state(sess_id)

    def resume_session(self, sess_id, note="", *, now="", commit=False) -> SessionState:
        """세션 재개 — 저장된 상태로 '어제 하던 연구 계속'. 이벤트 기록 + 전체 상태 반환."""
        goal = (ledger.session_events(sess_id) or [{}])[0].get("goal", "")
        self._emit(sess_id, goal, "RESUME", SESS_ACTIVE, {}, note or "resumed", now, commit)
        return self.state(sess_id)

    def archive_session(self, sess_id, note="", *, now="", commit=False) -> SessionState:
        goal = (ledger.session_events(sess_id) or [{}])[0].get("goal", "")
        self._emit(sess_id, goal, "ARCHIVE", SESS_ARCHIVED, {}, note or "archived", now, commit)
        return self.state(sess_id)

    def _current_state(self, sess_id) -> str:
        st = SESS_ACTIVE
        for e in ledger.session_events(sess_id):
            if e.get("to_state"):
                st = e["to_state"]
        return st

    def state(self, sess_id) -> SessionState:
        """이벤트 → 세션 상태(목표·진행·대기·완료실험·교훈·미해결질문). 결정적 폴드."""
        events = ledger.session_events(sess_id)
        goal = events[0].get("goal", "") if events else ""
        goals, progress, pending, completed, lessons, questions = [], [], [], [], [], []
        seen = {k: set() for k in ("g", "pr", "pd", "ce", "le", "oq")}
        resolved = set()
        state = SESS_ACTIVE
        updated = ""
        for e in events:
            if e.get("to_state"):
                state = e["to_state"]
            updated = e.get("occurred_at", updated)
            p = e.get("payload") or {}
            _extend(goals, p.get("goals"), seen["g"])
            _extend(progress, p.get("progress"), seen["pr"])
            _extend(pending, p.get("pending"), seen["pd"])
            _extend(completed, p.get("completed_experiments"), seen["ce"])
            _extend(lessons, p.get("lessons"), seen["le"])
            _extend(questions, p.get("open_questions"), seen["oq"])
            for rq in (p.get("resolved_questions") or []):
                resolved.add(str(rq))
        completed_set = {str(c) for c in completed}
        pending = [w for w in pending if str(w) not in completed_set]     # 완료된 것은 대기에서 제외
        questions = [q for q in questions if str(q) not in resolved]
        return SessionState(
            session_id=sess_id, goal=goal, state=state, goals=goals, progress=progress,
            pending_work=pending, completed_experiments=completed, lessons_learned=lessons,
            open_questions=questions, updated_at=updated)

    def list_sessions(self) -> list:
        seen, out = set(), []
        for e in ledger.read_sessions():
            sid = e.get("session_id")
            if sid and sid not in seen:
                seen.add(sid)
                out.append(self.state(sid).to_dict())
        return out
