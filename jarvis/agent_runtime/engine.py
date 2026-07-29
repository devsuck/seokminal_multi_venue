"""Agent Runtime Engine (P45) — 연구 에이전트 런타임. **거래·배포·실행·자본 결정 없음, 동작 없음.**

에이전트·태스크 배정·산출물·메모리 참조·상태·로그를 기록·관리한다. **에이전트는 거래·배포·자본 결정을 할 수 없다.
무제한 도구 접근 없음 — 능력 허용목록만.** execution/broker/live_trading/portfolio_execution import·호출 없음.
AGENT RUNTIME ≠ AUTONOMOUS TRADING. 엔진은 execute()/trade()/deploy()/allocate()/approve() 를 노출하지 않는다.
산출물은 항상 is_binding=False·is_executed=False(사람 검토용). 결정적·불변·append-only·이벤트 소싱. 상위 계층은 READ ONLY.
"""
from __future__ import annotations

from jarvis.agent_runtime import ledger
from jarvis.agent_runtime import models as M
from jarvis.agent_runtime.models import (
    GENESIS,
    AgentEventRecord,
    AgentReportRecord,
    AgentSummary,
    ArtifactRecord,
    IllegalAgentTransition,
    LogRecord,
    MemoryReferenceRecord,
    OutputRecord,
    TaskAssignmentRecord,
    UnknownEntityError,
    content_hash,
    input_digest,
)

_DISCLAIMER = ("Agent Runtime Layer 데이터 — AGENT RUNTIME ≠ AUTONOMOUS TRADING. 연구 에이전트 실행·기록 전용, "
               "산출물은 사람 검토용(is_binding=False·is_executed=False) — 거래·배포·실행·자본 배분 없음. 에이전트는 "
               "능력 허용목록 안에서만 동작하며 무제한 도구 접근이 없다.")


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class AgentRuntimeEngine:
    """연구 에이전트 런타임 엔진. 불변·append-only·이벤트 소싱·결정적. 거래/배포/실행/자본 결정 권한 없음."""

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

    # ══════════════ 에이전트 생애주기(event-sourced) ══════════════
    def _agent_event(self, agent, name, role, caps, frm, to, note, now, *, commit):
        seq = len(ledger.agent_events(agent))
        eid = M.agent_event_id(agent, to, seq)
        rec = AgentEventRecord(
            agent_event_id=eid, agent_id=agent, name=name, role=role, capabilities=caps,
            from_state=frm, to_state=to, note=note, occurred_at=now,
            input_hash=input_digest(agent, to, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.agent_event_exists, ledger.agents_head, ledger.append_agent_event,
                         eid, rec, commit=commit)
        return AgentEventRecord(**rec)

    def agent_state(self, agent) -> str | None:
        evs = ledger.agent_events(agent)
        return evs[-1].get("to_state") if evs else None

    def _agent_meta(self, agent) -> dict:
        evs = ledger.agent_events(agent)
        if not evs:
            raise UnknownEntityError(f"미등록 에이전트 {agent}")
        g = evs[0]
        return {"name": g.get("name"), "role": g.get("role"),
                "capabilities": g.get("capabilities", []), "state": evs[-1].get("to_state")}

    def register_agent(self, name, role, capabilities=None, now="", *, commit=False) -> AgentEventRecord:
        """에이전트 등록(genesis CREATED). **능력 허용목록 검증 — 무제한 접근·자본 결정 능력 거부.**"""
        if role not in M.AGENT_ROLES:
            raise ValueError(f"미지원 role {role}")
        caps = M.validate_capabilities(capabilities or [])
        agent = M.agent_id(name)
        evs = ledger.agent_events(agent)
        if evs:
            return AgentEventRecord(**{k: v for k, v in evs[0].items()
                                       if k in AgentEventRecord.__dataclass_fields__})
        ev = self._agent_event(agent, name, role, caps, GENESIS, M.A_CREATED, "registered", now,
                               commit=commit)
        self._artifact(M.ART_AGENT, agent, "", now, commit=commit)
        return ev

    def track_state(self, agent, to_state, note="", now="", *, commit=False) -> AgentEventRecord:
        """에이전트 상태 전이(CREATED→READY→WORKING→WAITING_REVIEW→ARCHIVED). **상태 기록 — 실행 아님.**"""
        m = self._agent_meta(agent)
        frm = m["state"]
        if to_state not in M.AGENT_STATES:
            raise ValueError(f"미지원 상태 {to_state}")
        if not M.can_agent_transition(frm, to_state):
            raise IllegalAgentTransition(f"에이전트 {agent} {frm}→{to_state} 불가")
        return self._agent_event(agent, m["name"], m["role"], m["capabilities"], frm, to_state,
                                 note or to_state.lower(), now, commit=commit)

    def mark_ready(self, agent, note="ready", now="", *, commit=False):
        return self.track_state(agent, M.A_READY, note, now, commit=commit)

    def start_work(self, agent, note="working", now="", *, commit=False):
        return self.track_state(agent, M.A_WORKING, note, now, commit=commit)

    def submit_for_review(self, agent, note="waiting_review", now="", *, commit=False):
        return self.track_state(agent, M.A_WAITING_REVIEW, note, now, commit=commit)

    def archive_agent(self, agent, note="archived", now="", *, commit=False):
        return self.track_state(agent, M.A_ARCHIVED, note, now, commit=commit)

    # ══════════════ assign_task ══════════════
    def assign_task(self, agent, title, description="", now="", *, commit=False) -> TaskAssignmentRecord:
        """에이전트에 연구 태스크 배정(불변). **정의·기록만 — 자동 실행 아님, is_binding=False.**"""
        m = self._agent_meta(agent)
        if m["state"] == M.A_ARCHIVED:
            raise IllegalAgentTransition(f"보관된 에이전트 {agent} 에는 배정 불가")
        seq = len(ledger.assignments_for(agent))
        tid = M.task_id(agent, title, seq)
        rec = TaskAssignmentRecord(
            task_id=tid, agent_id=agent, title=title, description=description, status="ASSIGNED",
            is_binding=False, created_at=now, input_hash=input_digest(agent, title, seq),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.assignment_exists, ledger.assignments_head, ledger.append_assignment,
                         tid, rec, commit=commit)
        self._artifact(M.ART_TASK, tid, M.artifact_id(M.ART_AGENT, agent), now, commit=commit)
        return TaskAssignmentRecord(**rec)

    # ══════════════ record_output ══════════════
    def record_output(self, agent, task_id, kind, payload=None, summary="", now="",
                      *, commit=False) -> OutputRecord:
        """에이전트 산출물 기록(내용 해시·불변). **항상 is_binding=False·is_executed=False — 사람 검토용.**"""
        self._agent_meta(agent)
        if kind not in M.OUTPUT_KINDS:
            raise ValueError(f"미지원 kind {kind}")
        seq = len([o for o in ledger.outputs_for(agent) if o.get("task_id") == task_id])
        oid = M.output_id(agent, task_id, seq)
        rec = OutputRecord(
            output_id=oid, agent_id=agent, task_id=task_id, kind=kind,
            content_hash=M.output_content_hash(payload), summary=summary, is_binding=False,
            is_executed=False, created_at=now, input_hash=input_digest(agent, task_id, seq),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.output_exists, ledger.outputs_head, ledger.append_output, oid, rec,
                         commit=commit)
        return OutputRecord(**rec)

    # ══════════════ reference_memory (READ ONLY 참조) ══════════════
    def reference_memory(self, agent, memory_layer, memory_ref, purpose="", now="",
                        *, commit=False) -> MemoryReferenceRecord:
        """에이전트의 메모리 참조 기록(READ ONLY). **참조만 — 메모리 변경 없음.**"""
        self._agent_meta(agent)
        mid = M.memref_id(agent, memory_layer, memory_ref)
        existing = next((r for r in ledger.read_memory_refs() if r.get("memref_id") == mid), None)
        if existing:
            return MemoryReferenceRecord(**{k: v for k, v in existing.items()
                                            if k in MemoryReferenceRecord.__dataclass_fields__})
        rec = MemoryReferenceRecord(
            memref_id=mid, agent_id=agent, memory_layer=memory_layer, memory_ref=memory_ref,
            purpose=purpose, is_read_only=True, created_at=now,
            input_hash=input_digest(agent, memory_layer, memory_ref), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.memref_exists, ledger.memory_refs_head, ledger.append_memref, mid,
                         rec, commit=commit)
        return MemoryReferenceRecord(**rec)

    # ══════════════ log_activity ══════════════
    def log_activity(self, agent, level, message, now="", *, commit=False) -> LogRecord:
        """에이전트 활동 로그(불변)."""
        self._agent_meta(agent)
        if level not in M.LOG_LEVELS:
            raise ValueError(f"미지원 level {level}")
        seq = len(ledger.logs_for(agent))
        lid = M.log_id(agent, seq)
        rec = LogRecord(log_id=lid, agent_id=agent, level=level, message=message, created_at=now,
                        input_hash=input_digest(agent, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.log_exists, ledger.logs_head, ledger.append_log, lid, rec,
                         commit=commit)
        return LogRecord(**rec)

    # ══════════════ generate_agent_report ══════════════
    def generate_agent_report(self, scope="SYSTEM", now="", *, commit=False) -> AgentReportRecord:
        """에이전트 런타임 리포트(에이전트·배정·산출물·참조·로그 집계). **is_binding=False, 거래·실행 없음.**"""
        agents = ledger.agent_ids()
        states = {a: self.agent_state(a) for a in agents}
        metas = {a: self._agent_meta(a) for a in agents}
        st_dist: dict = {}
        for st in states.values():
            st_dist[st] = st_dist.get(st, 0) + 1
        rl_dist: dict = {}
        for a in agents:
            rl_dist[metas[a]["role"]] = rl_dist.get(metas[a]["role"], 0) + 1
        rid = M.report_id(scope, now)
        rec = AgentReportRecord(
            report_id=rid, scope=scope, agent_count=len(agents),
            working_agent_count=sum(1 for st in states.values() if st == M.A_WORKING),
            waiting_review_count=sum(1 for st in states.values() if st == M.A_WAITING_REVIEW),
            assignment_count=len(ledger.read_assignments()),
            output_count=len(ledger.read_outputs()), memref_count=len(ledger.read_memory_refs()),
            log_count=len(ledger.read_logs()), role_distribution=dict(sorted(rl_dist.items())),
            state_distribution=dict(sorted(st_dist.items())), requires_human_review=True,
            is_binding=False, disclaimer=_DISCLAIMER, created_at=now,
            input_hash=input_digest(scope, now), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.report_exists, ledger.reports_head, ledger.append_report, rid, rec,
                         commit=commit)
        self._artifact(M.ART_REPORT, rid, "", now, commit=commit)
        return AgentReportRecord(**rec)

    def verify_integrity(self) -> dict:
        from jarvis.agent_runtime.verify import verify_chain
        return verify_chain()

    def list_agents(self) -> list:
        return ledger.agent_ids()

    def agents_in_state(self, state) -> list:
        return sorted(a for a in ledger.agent_ids() if self.agent_state(a) == state)

    def list_tasks(self, agent) -> list:
        return [a.get("task_id") for a in ledger.assignments_for(agent)]

    def agent_capabilities(self, agent) -> list:
        return self._agent_meta(agent)["capabilities"]

    def summary(self, now="") -> AgentSummary:
        return AgentSummary(
            timestamp=now, agent_event_count=len(ledger.read_agent_events()),
            agent_count=len(ledger.agent_ids()), assignment_count=len(ledger.read_assignments()),
            output_count=len(ledger.read_outputs()), memref_count=len(ledger.read_memory_refs()),
            log_count=len(ledger.read_logs()), report_count=len(ledger.read_reports()),
            artifact_count=len(ledger.read_artifacts()))
