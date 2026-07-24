"""Research Agent Execution Coordinator Engine (P12.3) — 연구 에이전트 조정. **조정·기록 전용.**

에이전트 배정·작업 위임·협업 추적·에이전트 진행·연구 핸드오프를 조정한다. **외부 행위를 실행하지 않는다.**
execution/broker/portfolio/risk/permission/deployment/live import·호출 없음. COORDINATE ≠ EXECUTION · ASSIGN ≠
AUTHORIZATION · HANDOFF ≠ DEPLOYMENT. 결정적·불변·append-only·이벤트 소싱. 상충 소유자 금지·핸드오프 증거 필수·
완료 결과 필수.
"""
from __future__ import annotations

from jarvis.research_agent_coordinator import ledger
from jarvis.research_agent_coordinator.models import (
    A_ASSIGNED,
    A_COMPLETED,
    A_CREATED,
    A_HANDOFF,
    A_IN_PROGRESS,
    A_REVIEW,
    ACTIVE_STATES,
    GENESIS,
    AgentRegistrationRecord,
    CollaborationRecord,
    ConflictingOwnerError,
    CoordinatorReportRecord,
    CoordinatorSummary,
    HandoffEvidenceError,
    HandoffRecord,
    IllegalAssignmentTransition,
    ImmutableAgentError,
    MissingResultError,
    OwnershipEventRecord,
    ProgressRecord,
    UnknownAgentError,
    UnknownAssignmentError,
    agent_registration_id as _agent_registration_id,
    assignment_id as _assignment_id,
    can_transition,
    collaboration_id as _collaboration_id,
    content_hash,
    handoff_id as _handoff_id,
    input_digest,
    ownership_event_id as _ownership_event_id,
    progress_id as _progress_id,
    report_id as _report_id,
)

_DISCLAIMER = ("Research Agent Coordinator 데이터 — COORDINATE ≠ EXECUTION · ASSIGN ≠ AUTHORIZATION · HANDOFF "
               "≠ DEPLOYMENT. 연구 에이전트 조정·기록 전용 — 외부 행위 실행·거래·배포·자본 배분·권한 변경 없음.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchAgentCoordinatorEngine:
    """연구 에이전트 실행 조정 엔진. 불변·append-only·이벤트 소싱·결정적. 실행 권한 없음."""

    # ══════════════ assign_agent (Agent Assignment Registry) ══════════════
    def assign_agent(self, coordinator: str, agent: str, capability: str = "", now: str = "",
                  *, commit: bool = False) -> AgentRegistrationRecord:
        """에이전트를 코디네이터 로스터에 배정(불변). **등록만 — 인가 아님.**"""
        aid = _agent_registration_id(coordinator, agent)
        existing = ledger.get_agent(aid)
        if existing is not None:
            if existing.get("capability") != capability:
                raise ImmutableAgentError(f"{aid} 에이전트 배정 불변 — 변경 불가")
            return AgentRegistrationRecord(**{k: v for k, v in existing.items()
                                              if k in AgentRegistrationRecord.__dataclass_fields__})
        rec = AgentRegistrationRecord(agent_registration_id=aid, coordinator=coordinator,
                                      agent=agent, capability=capability, registered_at=now,
                                      input_hash=input_digest(coordinator, agent),
                                      previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.agent_exists(aid):
            head = ledger.registry_head()
            ledger.append_agent(_seal(rec, head["record_hash"] if head else GENESIS))
        return AgentRegistrationRecord(**rec)

    def _require_agent(self, coordinator: str, agent: str) -> None:
        if not ledger.agent_registered(coordinator, agent):
            raise UnknownAgentError(f"미배정 에이전트 {agent}@{coordinator}")

    # ══════════════ 배정 생애주기(event-sourced) ══════════════
    def _ownership_event(self, assignment: str, coordinator: str, task_ref: str, agent: str,
                      frm: str, to: str, result_ref: str, note: str, now: str,
                      *, commit: bool) -> OwnershipEventRecord:
        seq = len(ledger.assignment_events(assignment))
        eid = _ownership_event_id(assignment, to, seq)
        rec = OwnershipEventRecord(ownership_event_id=eid, assignment_id=assignment,
                                   coordinator=coordinator, task_ref=task_ref, agent=agent,
                                   from_state=frm, to_state=to, result_ref=result_ref, note=note,
                                   occurred_at=now, input_hash=input_digest(assignment, to, seq),
                                   previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.ownership_event_exists(eid):
            head = ledger.ownership_head()
            ledger.append_ownership_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return OwnershipEventRecord(**rec)

    def _meta(self, assignment: str) -> dict:
        evs = ledger.assignment_events(assignment)
        if not evs:
            raise UnknownAssignmentError(f"미등록 배정 {assignment}")
        g = evs[0]
        last = evs[-1]
        return {"assignment_id": assignment, "coordinator": g.get("coordinator"),
                "task_ref": g.get("task_ref"), "agent": last.get("agent"),
                "state": last.get("to_state")}

    def current_state(self, assignment: str) -> str | None:
        evs = ledger.assignment_events(assignment)
        return evs[-1].get("to_state") if evs else None

    def current_owner(self, assignment: str) -> str | None:
        evs = ledger.assignment_events(assignment)
        return evs[-1].get("agent") if evs else None

    def _require_assignment(self, assignment: str) -> str:
        st = self.current_state(assignment)
        if st is None:
            raise UnknownAssignmentError(f"미등록 배정 {assignment}")
        return st

    def _transition(self, assignment: str, to: str, agent: str, result_ref: str, note: str,
                  now: str, *, commit: bool) -> OwnershipEventRecord:
        frm = self._require_assignment(assignment)
        if not can_transition(frm, to):
            raise IllegalAssignmentTransition(f"{assignment} {frm}→{to} 불가")
        m = self._meta(assignment)
        return self._ownership_event(assignment, m["coordinator"], m["task_ref"],
                                     agent or m["agent"], frm, to, result_ref, note, now,
                                     commit=commit)

    # ══════════════ create_task_assignment (Research Task Ownership) ══════════════
    def create_task_assignment(self, coordinator: str, task_ref: str, agent: str, note: str = "",
                            now: str = "", *, commit: bool = False) -> OwnershipEventRecord:
        """작업 배정(genesis CREATED→ASSIGNED). 상충 소유자 거부. **위임 기록만.**"""
        self._require_agent(coordinator, agent)
        aid = _assignment_id(coordinator, task_ref)
        evs = ledger.assignment_events(aid)
        if evs:
            m = self._meta(aid)
            if m["state"] != A_COMPLETED and m["agent"] != agent:
                raise ConflictingOwnerError(f"작업 {task_ref} 상충 소유자 {m['agent']}≠{agent}")
            return OwnershipEventRecord(**{k: v for k, v in evs[0].items()
                                           if k in OwnershipEventRecord.__dataclass_fields__})
        # 타 코디네이터에서 동일 작업 활성 소유 여부(전역 상충 방지)
        for other in ledger.task_assignments(task_ref):
            om = self._meta(other)
            if om["state"] != A_COMPLETED and om["agent"] != agent:
                raise ConflictingOwnerError(
                    f"작업 {task_ref} 이미 {om['agent']} 소유(활성) — 상충")
        self._ownership_event(aid, coordinator, task_ref, agent, GENESIS, A_CREATED, "", "created",
                              now, commit=commit)
        # CREATED→ASSIGNED 직접 발행(비커밋 미리보기에서도 ledger 상태 재조회 없이 동작)
        return self._ownership_event(aid, coordinator, task_ref, agent, A_CREATED, A_ASSIGNED, "",
                                     note or "assigned", now, commit=commit)

    # ══════════════ track_progress (Agent Progress Records) ══════════════
    def track_progress(self, assignment: str, percent: int = 0, note: str = "", result_ref: str = "",
                    now: str = "", *, commit: bool = False) -> ProgressRecord:
        """에이전트 진행 기록(불변). ASSIGNED/HANDOFF→IN_PROGRESS. **기록만.**"""
        st = self._require_assignment(assignment)
        m = self._meta(assignment)
        if st in (A_ASSIGNED, A_HANDOFF):
            self._transition(assignment, A_IN_PROGRESS, m["agent"], "", "in_progress", now,
                             commit=commit)
        seq = len(ledger.assignment_progress(assignment))
        pid = _progress_id(assignment, seq)
        rec = ProgressRecord(progress_id=pid, assignment_id=assignment, agent=m["agent"],
                             percent=int(percent), note=note, result_ref=result_ref,
                             recorded_at=now, input_hash=input_digest(assignment, seq),
                             previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.progress_exists(pid):
            head = ledger.progress_head()
            ledger.append_progress(_seal(rec, head["record_hash"] if head else GENESIS))
        return ProgressRecord(**rec)

    # ══════════════ record_handoff (Handoff Records) ══════════════
    def record_handoff(self, assignment: str, to_agent: str, evidence_ref: str, note: str = "",
                    now: str = "", *, commit: bool = False) -> HandoffRecord:
        """연구 핸드오프(불변). 증거 필수. IN_PROGRESS→HANDOFF, 소유자 이전. **기록만.**"""
        st = self._require_assignment(assignment)
        if not evidence_ref:
            raise HandoffEvidenceError(f"{assignment} 핸드오프 증거 누락 — 거부")
        m = self._meta(assignment)
        self._require_agent(m["coordinator"], to_agent)
        if st != A_IN_PROGRESS:
            raise IllegalAssignmentTransition(f"{assignment} IN_PROGRESS 아님({st}) — 핸드오프 불가")
        from_agent = m["agent"]
        self._transition(assignment, A_HANDOFF, to_agent, "", f"handoff:{from_agent}->{to_agent}",
                         now, commit=commit)
        seq = len(ledger.assignment_handoffs(assignment))
        hid = _handoff_id(assignment, seq)
        rec = HandoffRecord(handoff_id=hid, assignment_id=assignment, from_agent=from_agent,
                            to_agent=to_agent, evidence_ref=evidence_ref, note=note, recorded_at=now,
                            input_hash=input_digest(assignment, seq),
                            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.handoff_exists(hid):
            head = ledger.handoffs_head()
            ledger.append_handoff(_seal(rec, head["record_hash"] if head else GENESIS))
        return HandoffRecord(**rec)

    # ══════════════ submit_for_review / complete_assignment ══════════════
    def submit_for_review(self, assignment: str, now: str = "",
                       *, commit: bool = False) -> OwnershipEventRecord:
        """IN_PROGRESS/HANDOFF→REVIEW. **상태 기록만.**"""
        m = self._meta(assignment)
        return self._transition(assignment, A_REVIEW, m["agent"], "", "review", now, commit=commit)

    def complete_assignment(self, assignment: str, result_ref: str, now: str = "",
                         *, commit: bool = False) -> OwnershipEventRecord:
        """완료(REVIEW→COMPLETED). 기록된 결과 필수. **종결 기록만.**"""
        st = self._require_assignment(assignment)
        if not result_ref:
            raise MissingResultError(f"{assignment} 완료 결과 누락 — 거부")
        if st != A_REVIEW:
            raise IllegalAssignmentTransition(f"{assignment} REVIEW 아님({st}) — 완료 불가")
        m = self._meta(assignment)
        return self._transition(assignment, A_COMPLETED, m["agent"], result_ref, "completed", now,
                                commit=commit)

    # ══════════════ resolve_assignment_conflict (Collaboration Sessions) ══════════════
    def resolve_assignment_conflict(self, task_ref: str, agents, winning_agent: str,
                                 rationale: str = "", now: str = "",
                                 *, commit: bool = False) -> CollaborationRecord:
        """배정 상충 해소 기록(협업 세션, 불변). **기록만 — 자동 재배정 아님.**"""
        seq = len(ledger.task_collaborations(task_ref))
        cid = _collaboration_id(task_ref, seq)
        rec = CollaborationRecord(collaboration_id=cid, task_ref=task_ref,
                                  agents=sorted(set(agents or [])), winning_agent=winning_agent,
                                  rationale=rationale, created_at=now,
                                  input_hash=input_digest(task_ref, seq),
                                  previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.collaboration_exists(cid):
            head = ledger.collaborations_head()
            ledger.append_collaboration(_seal(rec, head["record_hash"] if head else GENESIS))
        return CollaborationRecord(**rec)

    # ══════════════ generate_coordination_report ══════════════
    def generate_coordination_report(self, coordinator: str, scope: str = "ALL", now: str = "",
                                  *, commit: bool = False) -> CoordinatorReportRecord:
        """조정 리포트(배정·활성·완료·핸드오프·에이전트 분포). **is_binding=False, 관찰만.**"""
        assigns = ledger.coordinator_assignments(coordinator)
        state_dist: dict = {}
        active = completed = 0
        for a in assigns:
            st = self.current_state(a)
            state_dist[st] = state_dist.get(st, 0) + 1
            if st in ACTIVE_STATES:
                active += 1
            if st == A_COMPLETED:
                completed += 1
        handoffs = sum(len(ledger.assignment_handoffs(a)) for a in assigns)
        agents = {r.get("agent") for r in ledger.read_agents() if r.get("coordinator") == coordinator}
        rid = _report_id(coordinator, scope, now)
        rec = CoordinatorReportRecord(
            report_id=rid, coordinator=coordinator, scope=scope, assignment_count=len(assigns),
            active_count=active, completed_count=completed, handoff_count=handoffs,
            agent_count=len(agents), state_distribution=dict(sorted(state_dist.items())),
            is_binding=False, disclaimer=_DISCLAIMER, created_at=now,
            input_hash=input_digest(coordinator, scope, now), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        return CoordinatorReportRecord(**rec)

    # ══════════════ verify_integrity ══════════════
    def verify_integrity(self) -> dict:
        from jarvis.research_agent_coordinator.verify import verify_chain
        return verify_chain()

    # ══════════════ 조회 편의 ══════════════
    def list_assignments(self, coordinator: str = "") -> list:
        if coordinator:
            return ledger.coordinator_assignments(coordinator)
        return ledger.assignment_ids()

    def assignments_in_state(self, state: str) -> list:
        return sorted(a for a in ledger.assignment_ids() if self.current_state(a) == state)

    def assignment_meta(self, assignment: str) -> dict:
        return self._meta(assignment)

    # ══════════════ Summary ══════════════
    def summary(self, now: str = "") -> CoordinatorSummary:
        return CoordinatorSummary(
            timestamp=now, agent_registration_count=len(ledger.read_agents()),
            ownership_event_count=len(ledger.read_ownership_events()),
            progress_count=len(ledger.read_progress()),
            handoff_count=len(ledger.read_handoffs()),
            collaboration_count=len(ledger.read_collaborations()),
            report_count=len(ledger.read_reports()))
