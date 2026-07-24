"""Research Agent Coordinator (P26) — 복수 연구 에이전트 협업 조정·기록. **협업 조정 전용, 동작 없음.**

**연구 협업만 관리한다.** 거래·주문·자본 배분·전략 배포·라이브 승인·권한 수정·자율 투자 결정을 하지 않는다. execution/
broker/live_trading/portfolio_execution import·호출 없음. CONSENSUS ≠ APPROVAL · CONSENSUS ≠ DEPLOYMENT ·
COORDINATION ≠ EXECUTION. 결정적·불변·append-only·이벤트 소싱. 상위 계층은 READ ONLY. 권한·정체성은 P10.6 소유(중복 없음).
"""
from __future__ import annotations

from jarvis.research_agent_coordination import ledger
from jarvis.research_agent_coordination import models as M
from jarvis.research_agent_coordination.models import (
    GENESIS,
    AgentRecord,
    ArtifactRecord,
    ConsensusRecord,
    CoordinationReportRecord,
    CoordinationSummary,
    IllegalSessionTransition,
    IllegalTaskTransition,
    MessageRecord,
    RoleRecord,
    RoleSeparationError,
    SessionEventRecord,
    TaskEventRecord,
    TaskIsolationError,
    TeamRecord,
    UnknownEntityError,
    content_hash,
    input_digest,
)

_DISCLAIMER = ("Research Agent Coordination 데이터 — CONSENSUS ≠ APPROVAL · CONSENSUS ≠ DEPLOYMENT · "
               "COORDINATION ≠ EXECUTION. 연구 협업·역할·작업 위임·토론·합의 기록 전용 — 거래·주문·자본 배분·전략 배포·"
               "라이브 승인·권한 수정·자율 투자 결정 없음. 권한·정체성·행동 제한은 P10.6 Agent Governance 소유.")


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchAgentCoordinator:
    """연구 에이전트 조정기. 불변·append-only·이벤트 소싱·결정적. 실행/거래/배포/승인/권한변경 권한 없음."""

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

    # ══════════════ register_agent (정체성 불변; 권한은 P10.6 소유) ══════════════
    def register_agent(self, name, version, capabilities=None, source_reference="", now="",
                       *, commit=False) -> AgentRecord:
        """연구 에이전트 등록(정체성 불변). **협업 조정용 — 권한/행동 제한은 P10.6 Agent Governance 소유.**"""
        caps = list(capabilities or [])
        aid = M.agent_id(name, version)
        existing = next((a for a in ledger.read_agents() if a.get("agent_id") == aid), None)
        if existing:
            return AgentRecord(**{k: v for k, v in existing.items()
                                  if k in AgentRecord.__dataclass_fields__})
        rec = AgentRecord(
            agent_id=aid, name=name, version=version, capabilities=caps,
            source_reference=source_reference, identity_hash=M.identity_hash(name, version, caps),
            registered_at=now, input_hash=input_digest(name, version), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.agent_exists, ledger.agents_head, ledger.append_agent, aid, rec,
                         commit=commit)
        self._artifact(M.ART_AGENT, aid, "", now, commit=commit)
        return AgentRecord(**rec)

    # ══════════════ define_role (역할 분리: 금지 행동 불가) ══════════════
    def define_role(self, name, responsibility="", allowed_actions=None, now="",
                    *, commit=False) -> RoleRecord:
        """역할 정의(불변). **역할 분리: allowed_actions 에 실행·배포·승인·권한변경 동사 금지.**"""
        actions = list(allowed_actions or [])
        if M.contains_forbidden_action(actions):
            raise RoleSeparationError(f"역할 {name}: 금지 행동 포함(실행/배포/승인/권한변경 불가)")
        rid = M.role_id(name)
        existing = next((r for r in ledger.read_roles() if r.get("role_id") == rid), None)
        if existing:
            return RoleRecord(**{k: v for k, v in existing.items()
                                 if k in RoleRecord.__dataclass_fields__})
        rec = RoleRecord(role_id=rid, name=name, responsibility=responsibility,
                         allowed_actions=actions, created_at=now, input_hash=input_digest(name),
                         previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.role_exists, ledger.roles_head, ledger.append_role, rid, rec,
                         commit=commit)
        return RoleRecord(**rec)

    # ══════════════ create_team ══════════════
    def create_team(self, objective, members=None, now="", *, commit=False) -> TeamRecord:
        """연구 팀 구조 정의(불변). 멤버는 등록된 에이전트여야 한다."""
        mem = list(members or [])
        known = {a.get("agent_id") for a in ledger.read_agents()}
        for m in mem:
            if m not in known:
                raise UnknownEntityError(f"미등록 에이전트 {m}")
        tid = M.team_id(objective)
        existing = next((t for t in ledger.read_teams() if t.get("team_id") == tid), None)
        if existing:
            return TeamRecord(**{k: v for k, v in existing.items()
                                 if k in TeamRecord.__dataclass_fields__})
        rec = TeamRecord(team_id=tid, members=mem, objective=objective, created_at=now,
                         input_hash=input_digest(objective), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.team_exists, ledger.teams_head, ledger.append_team, tid, rec,
                         commit=commit)
        self._artifact(M.ART_TEAM, tid, "", now, commit=commit)
        return TeamRecord(**rec)

    # ══════════════ 세션 생애주기(event-sourced) ══════════════
    def _session_event(self, sess, objective, team, frm, to, note, now, *, commit):
        seq = len(ledger.session_events(sess))
        eid = M.session_event_id(sess, to, seq)
        rec = SessionEventRecord(
            session_event_id=eid, session_id=sess, objective=objective, team_id=team, from_state=frm,
            to_state=to, note=note, occurred_at=now, input_hash=input_digest(sess, to, seq),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.session_event_exists, ledger.sessions_head,
                         ledger.append_session_event, eid, rec, commit=commit)
        return SessionEventRecord(**rec)

    def session_state(self, sess) -> str | None:
        evs = ledger.session_events(sess)
        return evs[-1].get("to_state") if evs else None

    def _session_meta(self, sess) -> dict:
        evs = ledger.session_events(sess)
        if not evs:
            raise UnknownEntityError(f"미등록 세션 {sess}")
        g = evs[0]
        return {"objective": g.get("objective"), "team_id": g.get("team_id"),
                "state": evs[-1].get("to_state")}

    def _session_transition(self, sess, to, note, now, *, commit):
        m = self._session_meta(sess)
        frm = m["state"]
        if not M.can_session_transition(frm, to):
            raise IllegalSessionTransition(f"세션 {sess} {frm}→{to} 불가")
        return self._session_event(sess, m["objective"], m["team_id"], frm, to, note, now,
                                   commit=commit)

    def create_session(self, objective, team_id="", now="", *, commit=False) -> SessionEventRecord:
        """협업 세션 생성(genesis CREATED, 이벤트 소싱)."""
        sess = M.session_id(objective)
        evs = ledger.session_events(sess)
        if evs:
            return SessionEventRecord(**{k: v for k, v in evs[0].items()
                                         if k in SessionEventRecord.__dataclass_fields__})
        ev = self._session_event(sess, objective, team_id, GENESIS, M.S_CREATED, "created", now,
                                 commit=commit)
        self._artifact(M.ART_SESSION, sess, "", now, commit=commit)
        return ev

    def activate_session(self, sess, note="active", now="", *, commit=False):
        return self._session_transition(sess, M.S_ACTIVE, note, now, commit=commit)

    def start_discussion(self, sess, note="discussing", now="", *, commit=False):
        return self._session_transition(sess, M.S_DISCUSSING, note, now, commit=commit)

    def conclude_session(self, sess, note="concluded", now="", *, commit=False):
        return self._session_transition(sess, M.S_CONCLUDED, note, now, commit=commit)

    def archive_session(self, sess, note="archived", now="", *, commit=False):
        return self._session_transition(sess, M.S_ARCHIVED, note, now, commit=commit)

    # ══════════════ 작업 위임 생애주기(event-sourced) ══════════════
    def _task_event(self, task, sess, agent, objective, source, deps, frm, to, note, now, *, commit):
        seq = len(ledger.task_events(task))
        eid = M.task_event_id(task, to, seq)
        rec = TaskEventRecord(
            task_event_id=eid, task_id=task, session_id=sess, assigned_agent=agent,
            objective=objective, source=source, dependencies=list(deps), from_state=frm, to_state=to,
            note=note, occurred_at=now, input_hash=input_digest(task, to, seq),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.task_event_exists, ledger.tasks_head, ledger.append_task_event, eid,
                         rec, commit=commit)
        return TaskEventRecord(**rec)

    def task_state(self, task) -> str | None:
        evs = ledger.task_events(task)
        return evs[-1].get("to_state") if evs else None

    def _task_meta(self, task) -> dict:
        evs = ledger.task_events(task)
        if not evs:
            raise UnknownEntityError(f"미등록 작업 {task}")
        g = evs[0]
        return {"session_id": g.get("session_id"), "assigned_agent": g.get("assigned_agent"),
                "objective": g.get("objective"), "source": g.get("source"),
                "dependencies": g.get("dependencies", []), "state": evs[-1].get("to_state")}

    def _task_transition(self, task, to, note, now, *, commit):
        m = self._task_meta(task)
        frm = m["state"]
        if not M.can_task_transition(frm, to):
            raise IllegalTaskTransition(f"작업 {task} {frm}→{to} 불가")
        return self._task_event(task, m["session_id"], m["assigned_agent"], m["objective"],
                                m["source"], m["dependencies"], frm, to, note, now, commit=commit)

    def assign_task(self, sess, assigned_agent, objective, source="", dependencies=None, now="",
                    *, commit=False) -> TaskEventRecord:
        """작업 생성·위임(genesis CREATED→ASSIGNED). **작업 격리: owner·objective 필수. 금지 행동 objective 불가.**"""
        self._session_meta(sess)  # 존재 검증
        if not assigned_agent:
            raise TaskIsolationError("작업은 owner(assigned_agent) 필수")
        if not objective:
            raise TaskIsolationError("작업은 objective 필수")
        if M.is_forbidden_verb(objective):
            raise RoleSeparationError(f"작업 objective 금지(실행/배포/승인/권한변경): {objective}")
        if assigned_agent not in {a.get("agent_id") for a in ledger.read_agents()}:
            raise UnknownEntityError(f"미등록 에이전트 {assigned_agent}")
        deps = list(dependencies or [])
        task = M.task_id(sess, objective)
        evs = ledger.task_events(task)
        if not evs:
            self._task_event(task, sess, assigned_agent, objective, source, deps, GENESIS,
                             M.T_CREATED, "created", now, commit=commit)
            self._artifact(M.ART_TASK, task, M.artifact_id(M.ART_AGENT, assigned_agent), now,
                           commit=commit)
            return self._task_transition(task, M.T_ASSIGNED, "assigned", now, commit=commit)
        return TaskEventRecord(**{k: v for k, v in evs[-1].items()
                                  if k in TaskEventRecord.__dataclass_fields__})

    def start_task(self, task, note="in_progress", now="", *, commit=False):
        return self._task_transition(task, M.T_IN_PROGRESS, note, now, commit=commit)

    def complete_task(self, task, note="completed", now="", *, commit=False):
        return self._task_transition(task, M.T_COMPLETED, note, now, commit=commit)

    def archive_task(self, task, note="archived", now="", *, commit=False):
        return self._task_transition(task, M.T_ARCHIVED, note, now, commit=commit)

    def resolve_dependencies(self, task) -> dict:
        """작업 의존성 상태 조회(READ ONLY). 모든 의존 작업이 COMPLETED/ARCHIVED 인지."""
        m = self._task_meta(task)
        states = {d: self.task_state(d) for d in m["dependencies"]}
        ready = all(st in (M.T_COMPLETED, M.T_ARCHIVED) for st in states.values())
        return {"task_id": task, "dependencies": states, "ready": ready}

    # ══════════════ record_message (토론 계보) ══════════════
    def record_message(self, sess, agent_id, content, refs=None, now="",
                       *, commit=False) -> MessageRecord:
        """연구 토론 메시지 기록(불변). **기록만.**"""
        self._session_meta(sess)  # 존재 검증
        seq = len(ledger.messages_in_session(sess))
        mid = M.message_id(sess, agent_id, seq)
        rec = MessageRecord(message_id=mid, session_id=sess, agent_id=agent_id, content=content,
                            refs=list(refs or []), timestamp=now,
                            input_hash=input_digest(sess, agent_id, seq),
                            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.message_exists, ledger.messages_head, ledger.append_message, mid,
                         rec, commit=commit)
        self._artifact(M.ART_MESSAGE, mid, M.artifact_id(M.ART_SESSION, sess), now, commit=commit)
        return MessageRecord(**rec)

    # ══════════════ record_consensus (기록만, 자동 결정 없음) ══════════════
    def record_consensus(self, sess, positions=None, summary="", now="",
                         *, commit=False) -> ConsensusRecord:
        """합의 기록(불변). 판정 YES/NO/MIXED + 동의 점수. **기록만 — 승인/배포/선택/실행 트리거 없음(is_decision=False).**"""
        self._session_meta(sess)  # 존재 검증
        pos = dict(positions or {})
        score = M.agreement_score(pos)
        verdict = M.classify_consensus(score, pos)
        seq = len(ledger.consensus_in_session(sess))
        cid = M.consensus_id(sess, seq)
        rec = ConsensusRecord(
            consensus_id=cid, session_id=sess, positions=pos, agreement_score=score, verdict=verdict,
            summary=summary, is_decision=False, created_at=now, input_hash=input_digest(sess, seq),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.consensus_exists, ledger.consensus_head, ledger.append_consensus,
                         cid, rec, commit=commit)
        self._artifact(M.ART_CONSENSUS, cid, M.artifact_id(M.ART_SESSION, sess), now, commit=commit)
        return ConsensusRecord(**rec)

    # ══════════════ generate_report ══════════════
    def generate_report(self, scope="SYSTEM", now="", *, commit=False) -> CoordinationReportRecord:
        """조정 리포트(에이전트·역할·팀·세션·작업·메시지·합의 집계). **is_binding=False, CONSENSUS ≠ APPROVAL.**"""
        sessions = ledger.session_ids()
        session_states = {s: self.session_state(s) for s in sessions}
        tasks = ledger.task_ids()
        task_states = {t: self.task_state(t) for t in tasks}
        consensus = ledger.read_consensus()
        verdict_dist: dict = {}
        for c in consensus:
            verdict_dist[c.get("verdict")] = verdict_dist.get(c.get("verdict"), 0) + 1
        rid = M.report_id(scope, now)
        rec = CoordinationReportRecord(
            report_id=rid, scope=scope, agent_count=len(ledger.read_agents()),
            role_count=len(ledger.read_roles()), team_count=len(ledger.read_teams()),
            session_count=len(sessions),
            active_session_count=sum(1 for st in session_states.values()
                                     if st in (M.S_CREATED, M.S_ACTIVE, M.S_DISCUSSING)),
            task_count=len(tasks),
            completed_task_count=sum(1 for st in task_states.values()
                                     if st in (M.T_COMPLETED, M.T_ARCHIVED)),
            message_count=len(ledger.read_messages()), consensus_count=len(consensus),
            verdict_distribution=dict(sorted(verdict_dist.items())), is_binding=False,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(scope, now),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.report_exists, ledger.reports_head, ledger.append_report, rid, rec,
                         commit=commit)
        self._artifact(M.ART_REPORT, rid, "", now, commit=commit)
        return CoordinationReportRecord(**rec)

    # ══════════════ verify / 조회 / summary ══════════════
    def verify_integrity(self) -> dict:
        from jarvis.research_agent_coordination.verify import verify_chain
        return verify_chain()

    def list_agents(self) -> list:
        return sorted(a.get("agent_id") for a in ledger.read_agents())

    def list_sessions(self) -> list:
        return ledger.session_ids()

    def sessions_in_state(self, state) -> list:
        return sorted(s for s in ledger.session_ids() if self.session_state(s) == state)

    def list_tasks(self) -> list:
        return ledger.task_ids()

    def summary(self, now="") -> CoordinationSummary:
        return CoordinationSummary(
            timestamp=now, agent_count=len(ledger.read_agents()), role_count=len(ledger.read_roles()),
            team_count=len(ledger.read_teams()),
            session_event_count=len(ledger.read_session_events()),
            session_count=len(ledger.session_ids()),
            task_event_count=len(ledger.read_task_events()), task_count=len(ledger.task_ids()),
            message_count=len(ledger.read_messages()), consensus_count=len(ledger.read_consensus()),
            report_count=len(ledger.read_reports()), artifact_count=len(ledger.read_artifacts()))
