"""Research Agent Framework Engine (P11.1) — 연구 보조 AI 에이전트. **연구 보조 전용.**

5종 에이전트(Data Analyst·Strategy Research·Backtest Analyst·Risk Analyst·Reviewer)가 Research OS 를 READ ONLY
로 참조(파일 기반, import 없음)해 읽기·분석·리포트만 수행한다. **에이전트는 연구 보조원 — TRADE·EXECUTE·DEPLOY·
ALLOCATE 금지·차단.** 허용 역량: READ·ANALYZE·REPORT. 모든 활동은 append-only 감사 원장에 기록된다.
execution/broker/order/portfolio execution/capital allocation/live trading/permission/risk controller import·
호출 없음. ASSIST ≠ EXECUTE · ANALYZE ≠ TRADE · REPORT ≠ DEPLOY. 상위 파일은 읽기만. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.research_agents import ledger
from jarvis.research_agents.models import (
    ACT_KIND_AGENT_TRANSITION,
    ACT_KIND_BLOCKED,
    ACT_KIND_MESSAGE,
    ACT_KIND_PROFILE,
    ACT_KIND_REGISTERED,
    ACT_KIND_REPORT,
    ACT_KIND_TASK_EVENT,
    AGENT_REGISTERED,
    AGENT_TYPES,
    ALLOWED_CAPABILITIES,
    CAP_REPORT,
    GENESIS,
    TASK_ASSIGNED,
    TASK_CANCELLED,
    TASK_COMPLETED,
    TASK_CREATED,
    TASK_FAILED,
    TASK_IN_PROGRESS,
    AgentProfileRecord,
    AgentRecord,
    AgentReportRecord,
    AgentSummary,
    ActivityRecord,
    CapabilityDenied,
    ForbiddenAgentAction,
    IllegalAgentTransition,
    IllegalTaskTransition,
    ImmutableAgentError,
    ImmutableMessageError,
    ImmutableProfileError,
    ImmutableReportError,
    InvalidAgentType,
    InvalidCapability,
    MessageRecord,
    TaskEventRecord,
    UnknownAgentError,
    activity_id as _activity_id,
    agent_id as _agent_id,
    can_transition_agent,
    can_transition_task,
    content_hash,
    input_digest,
    is_allowed_capability,
    is_forbidden_action,
    message_id as _message_id,
    profile_id as _profile_id,
    report_id as _report_id,
    task_event_id as _task_event_id,
    task_id as _task_id,
)

_DISCLAIMER = ("Research Agent 활동 — ASSIST ≠ EXECUTE · ANALYZE ≠ TRADE · REPORT ≠ DEPLOY. 연구 보조원 전용 — "
               "TRADE/EXECUTE/DEPLOY/ALLOCATE 금지·차단. 허용: READ·ANALYZE·REPORT.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchAgentEngine:
    """연구 보조 에이전트 프레임워크. 불변·append-only·결정적. 실행/거래/배포/할당 권한 없음(차단)."""

    # ══════════════ 활동 감사(내부) ══════════════
    def _log(self, kind: str, agent: str, action: str, reference: str, detail: str,
           allowed: bool, now: str, *, commit: bool) -> dict:
        aid = _activity_id(kind, reference, now)
        rec = ActivityRecord(activity_id=aid, kind=kind, agent=agent, action=action,
                             reference=reference, detail=detail, allowed=allowed, occurred_at=now,
                             input_hash=input_digest(kind, reference, now),
                             previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.activity_exists(aid):
            head = ledger.activity_head()
            ledger.append_activity(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    # ══════════════ register_agent ══════════════
    def register_agent(self, name: str, agent_type: str, description: str = "", now: str = "",
                     *, commit: bool = False) -> AgentRecord:
        """연구 보조 에이전트를 레지스트리에 등록. **연구 보조 등록만 — 실행 권한 부여 아님.**"""
        if agent_type not in AGENT_TYPES:
            raise InvalidAgentType(f"미등록 에이전트 유형 {agent_type}")
        aid = _agent_id(name)
        existing = ledger.get_agent(aid)
        if existing is not None:
            if existing.get("agent_type") != agent_type:
                raise ImmutableAgentError(f"{aid} 에이전트 불변 — 변경 불가")
            return AgentRecord(**{k: v for k, v in existing.items()
                                  if k in AgentRecord.__dataclass_fields__})
        rec = AgentRecord(agent_id=aid, name=name, agent_type=agent_type, description=description,
                          registered_at=now, input_hash=input_digest(name),
                          previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.agent_exists(aid):
            head = ledger.agents_head()
            ledger.append_agent(_seal(rec, head["record_hash"] if head else GENESIS))
        self._log(ACT_KIND_REGISTERED, name, "REGISTER", aid, agent_type, True, now, commit=commit)
        return AgentRecord(**rec)

    def _require_agent(self, name: str) -> dict:
        rec = ledger.get_agent(_agent_id(name))
        if rec is None:
            raise UnknownAgentError(f"미등록 에이전트 {name}")
        return rec

    # ══════════════ 프로파일(역량) ══════════════
    def create_profile(self, agent: str, capabilities, description: str = "", now: str = "",
                     *, commit: bool = False) -> AgentProfileRecord:
        """에이전트 프로파일(역량) 등록. **허용 역량(READ·ANALYZE·REPORT)만 — 금지 행위 거부.**"""
        arec = self._require_agent(agent)
        caps = [str(c).strip().upper() for c in capabilities]
        for c in caps:
            if is_forbidden_action(c):
                self._log(ACT_KIND_BLOCKED, agent, c, f"profile:{agent}",
                          "forbidden capability in profile", False, now, commit=commit)
                raise ForbiddenAgentAction(f"금지 역량 {c} — 프로파일 거부")
            if c not in ALLOWED_CAPABILITIES:
                raise InvalidCapability(f"미허용 역량 {c}")
        pid = _profile_id(agent)
        existing = ledger.get_profile(pid)
        if existing is not None:
            if sorted(existing.get("capabilities", [])) != sorted(caps):
                raise ImmutableProfileError(f"{pid} 프로파일 불변 — 변경 불가")
            return AgentProfileRecord(**{k: v for k, v in existing.items()
                                         if k in AgentProfileRecord.__dataclass_fields__})
        rec = AgentProfileRecord(
            profile_id=pid, agent=agent, agent_type=arec.get("agent_type"),
            capabilities=sorted(set(caps)), description=description, created_at=now,
            input_hash=input_digest(agent), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.profile_exists(pid):
            head = ledger.profiles_head()
            ledger.append_profile(_seal(rec, head["record_hash"] if head else GENESIS))
        self._log(ACT_KIND_PROFILE, agent, "PROFILE", pid, ",".join(sorted(set(caps))), True, now,
                  commit=commit)
        return AgentProfileRecord(**rec)

    def has_capability(self, agent: str, capability: str) -> bool:
        prof = ledger.get_profile(_profile_id(agent))
        if prof is None:
            return False
        return capability.strip().upper() in prof.get("capabilities", [])

    # ══════════════ 권한 가드 ══════════════
    def guard_action(self, agent: str, action: str, now: str = "", *, commit: bool = False) -> bool:
        """행위 권한 검사. 금지 행위는 감사 기록 후 차단. **TRADE/EXECUTE/DEPLOY/ALLOCATE 차단.**"""
        self._require_agent(agent)
        act = (action or "").strip().upper()
        if is_forbidden_action(act):
            self._log(ACT_KIND_BLOCKED, agent, act, f"{agent}:{act}",
                      "forbidden action blocked", False, now, commit=commit)
            raise ForbiddenAgentAction(f"금지 행위 {act} — 차단(에이전트는 연구 보조만)")
        if not is_allowed_capability(act):
            raise InvalidCapability(f"미허용 역량 {act}")
        if not self.has_capability(agent, act):
            raise CapabilityDenied(f"{agent} 프로파일에 {act} 역량 없음")
        return True

    # ══════════════ 에이전트 생애주기 ══════════════
    def current_agent_state(self, agent: str) -> str:
        state = AGENT_REGISTERED
        for a in ledger.read_activity():
            if a.get("kind") == ACT_KIND_AGENT_TRANSITION and a.get("agent") == agent:
                state = a.get("detail")
        return state

    def transition_agent(self, agent: str, to_state: str, now: str = "",
                       *, commit: bool = False) -> dict:
        """에이전트 생애주기 전이(REGISTERED→ACTIVE→IDLE→RETIRED). **관측 상태만.**"""
        self._require_agent(agent)
        frm = self.current_agent_state(agent)
        if not can_transition_agent(frm, to_state):
            raise IllegalAgentTransition(f"{agent} {frm}→{to_state} 불가")
        return self._log(ACT_KIND_AGENT_TRANSITION, agent, "TRANSITION", f"{agent}:{to_state}",
                         to_state, True, now, commit=commit)

    # ══════════════ 태스크 생애주기 ══════════════
    def current_task_state(self, task: str) -> str | None:
        evs = ledger.task_events(task)
        return evs[-1].get("to_state") if evs else None

    def _task_event(self, task: str, agent: str, action: str, target: str, description: str,
                  frm: str, to: str, now: str, *, commit: bool) -> TaskEventRecord:
        teid = _task_event_id(task, to)
        rec = TaskEventRecord(
            task_event_id=teid, task_id=task, agent=agent, action=action, target=target,
            description=description, from_state=frm, to_state=to, occurred_at=now,
            input_hash=input_digest(task, to), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.task_event_exists(teid):
            head = ledger.tasks_head()
            ledger.append_task(_seal(rec, head["record_hash"] if head else GENESIS))
        self._log(ACT_KIND_TASK_EVENT, agent, action, teid, f"{task}:{frm}->{to}", True, now,
                  commit=commit)
        return TaskEventRecord(**rec)

    def create_task(self, agent: str, action: str, target: str, description: str = "", now: str = "",
                  *, commit: bool = False) -> TaskEventRecord:
        """연구 태스크 생성(CREATED). action 은 허용 역량이어야 하며 금지 행위는 차단·감사. **READ/ANALYZE/REPORT.**"""
        self.guard_action(agent, action, now, commit=commit)
        task = _task_id(agent, action, target, description)
        if self.current_task_state(task) is not None:
            evs = ledger.task_events(task)
            last = evs[-1]
            return TaskEventRecord(**{k: v for k, v in last.items()
                                      if k in TaskEventRecord.__dataclass_fields__})
        return self._task_event(task, agent, action.strip().upper(), target, description,
                                GENESIS, TASK_CREATED, now, commit=commit)

    def _transition_task(self, task: str, to: str, now: str, *, commit: bool) -> TaskEventRecord:
        evs = ledger.task_events(task)
        if not evs:
            raise IllegalTaskTransition(f"미존재 태스크 {task}")
        last = evs[-1]
        frm = last.get("to_state")
        if not can_transition_task(frm, to):
            raise IllegalTaskTransition(f"{task} {frm}→{to} 불가")
        return self._task_event(task, last.get("agent"), last.get("action"), last.get("target"),
                                last.get("description"), frm, to, now, commit=commit)

    def assign_task(self, task: str, now: str = "", *, commit: bool = False) -> TaskEventRecord:
        return self._transition_task(task, TASK_ASSIGNED, now, commit=commit)

    def start_task(self, task: str, now: str = "", *, commit: bool = False) -> TaskEventRecord:
        return self._transition_task(task, TASK_IN_PROGRESS, now, commit=commit)

    def complete_task(self, task: str, now: str = "", *, commit: bool = False) -> TaskEventRecord:
        return self._transition_task(task, TASK_COMPLETED, now, commit=commit)

    def fail_task(self, task: str, now: str = "", *, commit: bool = False) -> TaskEventRecord:
        return self._transition_task(task, TASK_FAILED, now, commit=commit)

    def cancel_task(self, task: str, now: str = "", *, commit: bool = False) -> TaskEventRecord:
        return self._transition_task(task, TASK_CANCELLED, now, commit=commit)

    # ══════════════ 메시지 ══════════════
    def send_message(self, from_agent: str, to_agent: str, subject: str, content: str, now: str = "",
                   *, commit: bool = False) -> MessageRecord:
        """에이전트 간 메시지 기록(불변). **정보 교환만 — 실행 지시 아님.**"""
        self._require_agent(from_agent)
        mid = _message_id(from_agent, to_agent, subject, content)
        existing = ledger.get_message(mid)
        if existing is not None:
            if existing.get("content") != content:
                raise ImmutableMessageError(f"{mid} 메시지 불변 — 변경 불가")
            return MessageRecord(**{k: v for k, v in existing.items()
                                    if k in MessageRecord.__dataclass_fields__})
        rec = MessageRecord(message_id=mid, from_agent=from_agent, to_agent=to_agent,
                            subject=subject, content=content, created_at=now,
                            input_hash=input_digest(from_agent, to_agent, subject),
                            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.message_exists(mid):
            head = ledger.messages_head()
            ledger.append_message(_seal(rec, head["record_hash"] if head else GENESIS))
        self._log(ACT_KIND_MESSAGE, from_agent, "MESSAGE", mid, f"{from_agent}->{to_agent}", True,
                  now, commit=commit)
        return MessageRecord(**rec)

    # ══════════════ 리포트(REPORT 역량 필요) ══════════════
    def submit_report(self, agent: str, task: str, scope: str, findings, summary: str = "",
                    now: str = "", *, commit: bool = False) -> AgentReportRecord:
        """에이전트 연구 리포트 제출(불변). **REPORT 역량 필요 — 관측 리포트, 실행 아님.**"""
        self.guard_action(agent, CAP_REPORT, now, commit=commit)
        rid = _report_id(agent, task, scope)
        existing = ledger.get_report(rid)
        finds = list(findings or [])
        if existing is not None:
            if existing.get("summary") != summary or list(existing.get("findings", [])) != finds:
                raise ImmutableReportError(f"{rid} 리포트 불변 — 변경 불가")
            return AgentReportRecord(**{k: v for k, v in existing.items()
                                        if k in AgentReportRecord.__dataclass_fields__})
        rec = AgentReportRecord(report_id=rid, agent=agent, task_id=task, scope=scope,
                                findings=finds, summary=summary, created_at=now,
                                input_hash=input_digest(agent, task, scope),
                                previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        self._log(ACT_KIND_REPORT, agent, "REPORT", rid, scope, True, now, commit=commit)
        return AgentReportRecord(**rec)

    # ══════════════ READ ONLY 연구 보조 조회 ══════════════
    def read_os(self, role: str, limit: int = 0) -> list:
        """Research OS 소스를 READ ONLY 로 조회(에이전트 읽기 보조). **읽기만.**"""
        recs = ledger.read_role(role)
        return recs[:limit] if limit else recs

    def analyze_source(self, agent: str, role: str, now: str = "", *, commit: bool = False) -> dict:
        """에이전트 ANALYZE — 소스 레코드 수 등 요약(읽기·분석만). **ANALYZE ≠ TRADE.**"""
        self.guard_action(agent, "ANALYZE", now, commit=commit)
        recs = ledger.read_role(role)
        return {"agent": agent, "role": role, "record_count": len(recs), "read_only": True}

    # ══════════════ 조회 편의 ══════════════
    def list_agents(self, agent_type: str = "") -> list:
        agents = ledger.read_agents()
        if agent_type:
            agents = [a for a in agents if a.get("agent_type") == agent_type]
        return sorted(a.get("name") for a in agents if a.get("name"))

    def agent_activity(self, agent: str) -> list:
        return [a for a in ledger.read_activity() if a.get("agent") == agent]

    def blocked_actions(self) -> list:
        return [a for a in ledger.read_activity() if a.get("kind") == ACT_KIND_BLOCKED]

    # ══════════════ Summary ══════════════
    def summary(self, now: str = "") -> AgentSummary:
        activity = ledger.read_activity()
        blocked = sum(1 for a in activity if a.get("kind") == ACT_KIND_BLOCKED)
        return AgentSummary(
            timestamp=now, agent_count=len(ledger.read_agents()),
            profile_count=len(ledger.read_profiles()), task_event_count=len(ledger.read_tasks()),
            message_count=len(ledger.read_messages()), report_count=len(ledger.read_reports()),
            activity_count=len(activity), blocked_count=blocked)
