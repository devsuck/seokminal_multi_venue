"""Autonomous Experiment Scheduler Engine (P12.2) — 스케줄링 지능. **스케줄·기록 전용.**

실험 큐·우선순위·의존 순서·실행 윈도 계획을 관리한다. **실험을 실행하지 않는다.** execution/broker/portfolio/
risk/permission/deployment/live import·호출 없음. SCHEDULE ≠ EXECUTION · PLAN ≠ RUN · PRIORITY ≠ APPROVAL.
결정적·불변·append-only·이벤트 소싱. 무효 의존·순환 스케줄·중복 실행 요청·무단 우선순위 변경은 차단된다.
"""
from __future__ import annotations

from jarvis.autonomous_experiment_scheduler import ledger
from jarvis.autonomous_experiment_scheduler.models import (
    GENESIS,
    Q_ARCHIVED,
    Q_COMPLETED,
    Q_QUEUED,
    Q_REQUESTED,
    Q_SCHEDULED,
    SCHEDULABLE_STATES,
    CircularScheduleError,
    DanglingDependencyError,
    DependencyRecord,
    DuplicateRequestError,
    IllegalScheduleTransition,
    ImmutablePolicyError,
    ImmutableScheduleError,
    PolicyRecord,
    PriorityChangeError,
    PriorityRecord,
    ScheduleEventRecord,
    ScheduleRecord,
    ScheduleReportRecord,
    SchedulerSummary,
    SnapshotRecord,
    UnknownRequestError,
    UnknownScheduleError,
    can_transition,
    content_hash,
    dependency_id as _dependency_id,
    input_digest,
    policy_id as _policy_id,
    priority_id as _priority_id,
    report_id as _report_id,
    request_id as _request_id,
    schedule_event_id as _schedule_event_id,
    schedule_id as _schedule_id,
    snapshot_id as _snapshot_id,
    topological_order,
)

_DISCLAIMER = ("Autonomous Experiment Scheduler 데이터 — SCHEDULE ≠ EXECUTION · PLAN ≠ RUN · PRIORITY ≠ "
               "APPROVAL. 실험 스케줄링·기록 전용 — 실험 실행·거래·배포·자본 배분·권한 변경 없음.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class AutonomousExperimentSchedulerEngine:
    """자율 실험 스케줄러 엔진. 불변·append-only·이벤트 소싱·결정적. 실행 권한 없음."""

    # ══════════════ create_schedule (Queue Registry) ══════════════
    def create_schedule(self, name: str, mandate: str = "", now: str = "",
                     *, commit: bool = False) -> ScheduleRecord:
        """실험 큐/스케줄 등록(불변). **등록만.**"""
        sid = _schedule_id(name)
        existing = ledger.get_schedule(sid)
        if existing is not None:
            if existing.get("mandate") != mandate:
                raise ImmutableScheduleError(f"{sid} 스케줄 불변 — 변경 불가")
            return ScheduleRecord(**{k: v for k, v in existing.items()
                                     if k in ScheduleRecord.__dataclass_fields__})
        rec = ScheduleRecord(schedule_id=sid, name=name, mandate=mandate, created_at=now,
                             input_hash=input_digest(name), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.schedule_exists(sid):
            head = ledger.registry_head()
            ledger.append_schedule(_seal(rec, head["record_hash"] if head else GENESIS))
        return ScheduleRecord(**rec)

    def _require_schedule(self, sid: str) -> dict:
        rec = ledger.get_schedule(sid)
        if rec is None:
            raise UnknownScheduleError(f"미등록 스케줄 {sid}")
        return rec

    # ══════════════ 요청 생애주기(event-sourced) ══════════════
    def _request_event(self, request: str, schedule: str, experiment_ref: str, frm: str, to: str,
                    note: str, now: str, *, commit: bool) -> ScheduleEventRecord:
        seq = len(ledger.request_events(request))
        eid = _schedule_event_id(request, to, seq)
        rec = ScheduleEventRecord(schedule_event_id=eid, request_id=request, schedule_id=schedule,
                                  experiment_ref=experiment_ref, from_state=frm, to_state=to,
                                  note=note, occurred_at=now,
                                  input_hash=input_digest(request, to, seq),
                                  previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.schedule_event_exists(eid):
            head = ledger.schedules_head()
            ledger.append_schedule_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return ScheduleEventRecord(**rec)

    def _request_meta(self, request: str) -> dict:
        evs = ledger.request_events(request)
        if not evs:
            raise UnknownRequestError(f"미등록 요청 {request}")
        g = evs[0]
        return {"request_id": request, "schedule_id": g.get("schedule_id"),
                "experiment_ref": g.get("experiment_ref"), "state": evs[-1].get("to_state")}

    def current_state(self, request: str) -> str | None:
        evs = ledger.request_events(request)
        return evs[-1].get("to_state") if evs else None

    def _require_request(self, request: str) -> str:
        st = self.current_state(request)
        if st is None:
            raise UnknownRequestError(f"미등록 요청 {request}")
        return st

    # ══════════════ register_experiment_request ══════════════
    def register_experiment_request(self, schedule: str, experiment_ref: str, note: str = "",
                                 now: str = "", *, commit: bool = False) -> ScheduleEventRecord:
        """실험 요청 등록(genesis REQUESTED). 중복 실행 요청 거부. **큐잉만.**"""
        self._require_schedule(schedule)
        req = _request_id(schedule, experiment_ref)
        if ledger.request_events(req):
            raise DuplicateRequestError(f"중복 실행 요청 {experiment_ref} — 거부")
        return self._request_event(req, schedule, experiment_ref, GENESIS, Q_REQUESTED, note or
                                   "requested", now, commit=commit)

    # ══════════════ assign_priority (Priority Rules) ══════════════
    def assign_priority(self, request: str, priority: int, rule: str = "", now: str = "",
                     *, commit: bool = False) -> PriorityRecord:
        """우선순위 배정(불변). 무단 변경 거부. **기록만.**"""
        self._require_request(request)
        pid = _priority_id(request)
        existing = ledger.get_priority(pid)
        if existing is not None:
            if int(existing.get("priority", 0)) != int(priority):
                raise PriorityChangeError(f"{request} 우선순위 무단 변경 거부")
            return PriorityRecord(**{k: v for k, v in existing.items()
                                     if k in PriorityRecord.__dataclass_fields__})
        rec = PriorityRecord(priority_id=pid, request_id=request, priority=int(priority), rule=rule,
                             created_at=now, input_hash=input_digest(request),
                             previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.priority_exists(pid):
            head = ledger.priorities_head()
            ledger.append_priority(_seal(rec, head["record_hash"] if head else GENESIS))
        return PriorityRecord(**rec)

    def request_priority(self, request: str) -> int:
        p = ledger.get_priority(_priority_id(request))
        return int(p.get("priority", 0)) if p else 0

    # ══════════════ create_scheduling_policy (Scheduling Policies) ══════════════
    def create_scheduling_policy(self, schedule: str, name: str, rule: str = "", now: str = "",
                              *, commit: bool = False) -> PolicyRecord:
        """스케줄링 정책 정의(불변). **정의만.**"""
        self._require_schedule(schedule)
        pid = _policy_id(schedule, name)
        cur = None
        for r in ledger.schedule_policies(schedule):
            if r.get("policy_id") == pid:
                cur = r
                break
        if cur is not None:
            if cur.get("rule") != rule:
                raise ImmutablePolicyError(f"{pid} 정책 불변 — 변경 불가")
            return PolicyRecord(**{k: v for k, v in cur.items()
                                   if k in PolicyRecord.__dataclass_fields__})
        rec = PolicyRecord(policy_id=pid, schedule_id=schedule, name=name, rule=rule, created_at=now,
                           input_hash=input_digest(schedule, name),
                           previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.policy_exists(pid):
            head = ledger.policies_head()
            ledger.append_policy(_seal(rec, head["record_hash"] if head else GENESIS))
        return PolicyRecord(**rec)

    # ══════════════ resolve_dependencies (Dependency Graph) ══════════════
    def _dep_edges(self) -> list:
        return [(r.get("request_id"), r.get("depends_on")) for r in ledger.read_dependencies()]

    def resolve_dependencies(self, request: str, depends_on, now: str = "",
                          *, commit: bool = False) -> list:
        """의존 등록(불변). 무효 의존·순환 스케줄 거부. **기록만.** 반환: DependencyRecord 리스트."""
        self._require_request(request)
        deps = sorted(set(depends_on or []))
        out: list = []
        for dep in deps:
            if not ledger.request_events(dep):
                raise DanglingDependencyError(f"무효 의존 요청 {dep}")
            edges = self._dep_edges() + [(request, dep)]
            if request == dep or _cycle(edges):
                raise CircularScheduleError(f"순환 스케줄 의존 — 거부 {request}->{dep}")
            did = _dependency_id(request, dep)
            rec = DependencyRecord(dependency_id=did, request_id=request, depends_on=dep,
                                   created_at=now, input_hash=input_digest(request, dep),
                                   previous_hash=GENESIS).to_dict()
            rec["record_hash"] = content_hash(rec)
            if commit and not ledger.dependency_exists(did):
                head = ledger.dependencies_head()
                ledger.append_dependency(_seal(rec, head["record_hash"] if head else GENESIS))
            out.append(DependencyRecord(**rec))
        return out

    def request_dependencies(self, request: str) -> list:
        return sorted(r.get("depends_on") for r in ledger.request_dependencies(request))

    # ══════════════ update_schedule_state (lifecycle) ══════════════
    def update_schedule_state(self, request: str, to_state: str, note: str = "", now: str = "",
                           *, commit: bool = False) -> ScheduleEventRecord:
        """스케줄 상태 전이(오직 유효 선형 전이). **전이 기록만.**"""
        frm = self._require_request(request)
        if not can_transition(frm, to_state):
            raise IllegalScheduleTransition(f"{request} {frm}→{to_state} 불가")
        m = self._request_meta(request)
        return self._request_event(request, m["schedule_id"], m["experiment_ref"], frm, to_state,
                                   note or "advanced", now, commit=commit)

    # ══════════════ build_execution_plan (실행 윈도 계획, 실행 아님) ══════════════
    def build_execution_plan(self, schedule: str, scope: str = "SCHEDULABLE", now: str = "",
                          *, commit: bool = False) -> SnapshotRecord:
        """실행 계획(의존 위상 정렬 + 우선순위, 결정적). **계획·기록만 — 실행 아님.**"""
        self._require_schedule(schedule)
        reqs = [r for r in ledger.schedule_requests(schedule)
                if self.current_state(r) in SCHEDULABLE_STATES]
        edges = [(r.get("request_id"), r.get("depends_on")) for r in ledger.read_dependencies()
                 if r.get("request_id") in reqs and r.get("depends_on") in reqs]
        prio = {r: self.request_priority(r) for r in reqs}
        plan = topological_order(reqs, edges, prio)
        state_dist: dict = {}
        for r in ledger.schedule_requests(schedule):
            st = self.current_state(r)
            state_dist[st] = state_dist.get(st, 0) + 1
        sid = _snapshot_id(schedule, scope, now)
        rec = SnapshotRecord(snapshot_id=sid, schedule_id=schedule, scope=scope, plan=plan,
                             request_count=len(ledger.schedule_requests(schedule)),
                             state_distribution=dict(sorted(state_dist.items())), taken_at=now,
                             input_hash=input_digest(schedule, scope, now),
                             previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.snapshot_exists(sid):
            head = ledger.snapshots_head()
            ledger.append_snapshot(_seal(rec, head["record_hash"] if head else GENESIS))
        return SnapshotRecord(**rec)

    # ══════════════ generate_schedule_report ══════════════
    def generate_schedule_report(self, schedule: str, scope: str = "ALL", now: str = "",
                              *, commit: bool = False) -> ScheduleReportRecord:
        """스케줄링 리포트(요청·스케줄·완료·의존·정책 분포). **is_binding=False, 관찰만.**"""
        self._require_schedule(schedule)
        reqs = ledger.schedule_requests(schedule)
        state_dist: dict = {}
        scheduled = completed = 0
        for r in reqs:
            st = self.current_state(r)
            state_dist[st] = state_dist.get(st, 0) + 1
            if st in (Q_SCHEDULED, Q_COMPLETED, Q_ARCHIVED):
                scheduled += 1
            if st in (Q_COMPLETED, Q_ARCHIVED):
                completed += 1
        dep_count = len([d for d in ledger.read_dependencies() if d.get("request_id") in set(reqs)])
        rid = _report_id(schedule, scope, now)
        rec = ScheduleReportRecord(
            report_id=rid, schedule_id=schedule, scope=scope, request_count=len(reqs),
            scheduled_count=scheduled, completed_count=completed, dependency_count=dep_count,
            policy_count=len(ledger.schedule_policies(schedule)),
            state_distribution=dict(sorted(state_dist.items())), is_binding=False,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(schedule, scope, now),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        return ScheduleReportRecord(**rec)

    # ══════════════ verify_integrity ══════════════
    def verify_integrity(self) -> dict:
        from jarvis.autonomous_experiment_scheduler.verify import verify_chain
        return verify_chain()

    # ══════════════ 조회 편의 ══════════════
    def list_requests(self, schedule: str = "") -> list:
        if schedule:
            return ledger.schedule_requests(schedule)
        return ledger.request_ids()

    def requests_in_state(self, state: str) -> list:
        return sorted(r for r in ledger.request_ids() if self.current_state(r) == state)

    # ══════════════ Summary ══════════════
    def summary(self, now: str = "") -> SchedulerSummary:
        return SchedulerSummary(
            timestamp=now, schedule_count=len(ledger.read_schedules()),
            schedule_event_count=len(ledger.read_schedule_events()),
            policy_count=len(ledger.read_policies()),
            priority_count=len(ledger.read_priorities()),
            dependency_count=len(ledger.read_dependencies()),
            snapshot_count=len(ledger.read_snapshots()), report_count=len(ledger.read_reports()))


def _cycle(edges: list) -> list:
    from jarvis.autonomous_experiment_scheduler.models import detect_cycle
    return detect_cycle(edges)
