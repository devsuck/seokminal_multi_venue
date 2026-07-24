"""Research Coordinator Engine (P11.7) — 다중 연구 에이전트 조율 계층. **조율·기록 전용.**

연구 태스크 배정·의존성 조율·진행 모니터링·워크로드 재분배·정체 탐지·조율 리포트를 수행한다.
**연구를 실행하지 않는다. 거래하지 않는다. 배포하지 않는다. 어떤 상위 상태도 변경하지 않는다.**
execution/broker/portfolio/risk/permission/deployment/live import·호출 없음. COORDINATION ≠ EXECUTION ·
ASSIGNMENT ≠ TRADE · REBALANCE ≠ DEPLOYMENT · REPORT ≠ APPROVAL. 순환 의존성 거부·완료 태스크 불변·태스크 결과/
연구 결론 무수정. 불변·append-only·이벤트 소싱·결정적.
"""
from __future__ import annotations

from jarvis.research_coordinator import ledger
from jarvis.research_coordinator.models import (
    ART_ASSIGNMENT,
    ART_COORDINATOR,
    ART_PLAN,
    ART_REPORT,
    EDITABLE_PLAN_STATES,
    EV_BLOCKER_DETECTED,
    EV_DEPENDENCY_ADDED,
    EV_ISSUE_ESCALATED,
    EV_PLAN_TRANSITION,
    EV_PROGRESS_UPDATED,
    EV_TASK_ASSIGNED,
    EV_TASK_REASSIGNED,
    EV_WORKLOAD_REBALANCED,
    GENESIS,
    P_ARCHIVED,
    P_ASSIGNING,
    P_BLOCKED,
    P_COMPLETED,
    P_CREATED,
    P_PLANNING,
    P_REBALANCING,
    P_RUNNING,
    SEVERITIES,
    T_ASSIGNED,
    T_BLOCKED,
    T_COMPLETED,
    T_IN_PROGRESS,
    ArtifactRecord,
    AssignmentEventRecord,
    CompletedTaskError,
    CompletionReportRecord,
    CoordinationEventRecord,
    CoordinatorRecord,
    CoordinatorSummary,
    DependencyCycleError,
    DependencyRecord,
    EscalationRecord,
    IllegalPlanTransition,
    IllegalTaskTransition,
    ImmutableCoordinatorError,
    InvalidSeverity,
    PlanClosedError,
    PlanEventRecord,
    ProgressRecord,
    ScheduleRecord,
    SelfDependencyError,
    UnknownCoordinatorError,
    UnknownPlanError,
    UnknownTaskError,
    WorkloadRecord,
    artifact_id as _artifact_id,
    assignment_event_id as _assignment_event_id,
    build_waves,
    can_transition_plan,
    can_transition_task,
    content_hash,
    coordinator_id as _coordinator_id,
    dependency_id as _dependency_id,
    detect_cycle,
    escalation_id as _escalation_id,
    event_id as _event_id,
    input_digest,
    plan_event_id as _plan_event_id,
    plan_id as _plan_id,
    progress_id as _progress_id,
    report_id as _report_id,
    schedule_id as _schedule_id,
    suggest_moves,
    task_id as _task_id,
    topological_sort,
    workload_id as _workload_id,
    workload_imbalance,
)

_DISCLAIMER = ("Research Coordinator 데이터 — COORDINATION ≠ EXECUTION · ASSIGNMENT ≠ TRADE · REBALANCE ≠ "
               "DEPLOYMENT · REPORT ≠ APPROVAL. 조율·기록 전용 — 실행/거래/배포/할당/권한·설정 변경/승격 없음. "
               "완료 태스크·연구 결론은 결코 수정되지 않는다.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchCoordinatorEngine:
    """자율 연구 코디네이터. 불변·append-only·이벤트 소싱·결정적. 실행/거래/배포/상위수정 권한 없음."""

    # ══════════════ 아티팩트 계보(내부) ══════════════
    def _artifact(self, atype: str, ref: str, parent: str, plan: str, now: str,
                *, commit: bool) -> ArtifactRecord:
        aid = _artifact_id(atype, ref)
        rec = ArtifactRecord(artifact_id=aid, artifact_type=atype, ref_id=ref,
                             parent_artifact=parent, plan_id=plan, created_at=now,
                             input_hash=input_digest(atype, ref), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return ArtifactRecord(**rec)

    def _event(self, plan: str, kind: str, reference: str, detail: str, now: str,
             *, commit: bool) -> CoordinationEventRecord:
        seq = len(ledger.plan_events_log(plan))
        eid = _event_id(plan, kind, seq)
        rec = CoordinationEventRecord(event_id=eid, plan_id=plan, kind=kind, reference=reference,
                                      detail=detail, occurred_at=now,
                                      input_hash=input_digest(plan, kind, seq),
                                      previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.event_exists(eid):
            head = ledger.events_head()
            ledger.append_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return CoordinationEventRecord(**rec)

    # ══════════════ register_coordinator ══════════════
    def register_coordinator(self, name: str, mandate: str = "", now: str = "",
                           *, commit: bool = False) -> CoordinatorRecord:
        """코디네이터 등록(불변). **조율 등록만 — 실행 권한 아님.**"""
        cid = _coordinator_id(name)
        existing = ledger.get_coordinator(cid)
        if existing is not None:
            if existing.get("name") != name:
                raise ImmutableCoordinatorError(f"{cid} 코디네이터 불변 — 변경 불가")
            return CoordinatorRecord(**{k: v for k, v in existing.items()
                                        if k in CoordinatorRecord.__dataclass_fields__})
        rec = CoordinatorRecord(coordinator_id=cid, name=name, mandate=mandate, created_at=now,
                                input_hash=input_digest(name), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.coordinator_exists(cid):
            head = ledger.coordinators_head()
            ledger.append_coordinator(_seal(rec, head["record_hash"] if head else GENESIS))
        self._artifact(ART_COORDINATOR, cid, "", "", now, commit=commit)
        return CoordinatorRecord(**rec)

    def _require_coordinator(self, cid: str) -> dict:
        rec = ledger.get_coordinator(cid)
        if rec is None:
            raise UnknownCoordinatorError(f"미등록 코디네이터 {cid}")
        return rec

    # ══════════════ create_plan (event-sourced) ══════════════
    def _plan_event(self, plan: str, coordinator: str, name: str, objective: str, frm: str,
                  to: str, note: str, now: str, *, commit: bool) -> PlanEventRecord:
        seq = len(ledger.plan_events(plan))
        peid = _plan_event_id(plan, to, seq)
        rec = PlanEventRecord(plan_event_id=peid, plan_id=plan, coordinator_id=coordinator,
                              name=name, objective=objective, from_state=frm, to_state=to,
                              note=note, occurred_at=now, input_hash=input_digest(plan, to, seq),
                              previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.plan_event_exists(peid):
            head = ledger.plans_head()
            ledger.append_plan_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return PlanEventRecord(**rec)

    def create_plan(self, coordinator: str, name: str, objective: str = "", now: str = "",
                  *, commit: bool = False) -> PlanEventRecord:
        """연구 플랜 생성(CREATED). **조율 계획만 — 실행 없음.**"""
        self._require_coordinator(coordinator)
        plan = _plan_id(coordinator, name)
        evs = ledger.plan_events(plan)
        if evs:
            g = evs[0]
            return PlanEventRecord(**{k: v for k, v in g.items()
                                      if k in PlanEventRecord.__dataclass_fields__})
        ev = self._plan_event(plan, coordinator, name, objective, GENESIS, P_CREATED, "created",
                            now, commit=commit)
        parent = _artifact_id(ART_COORDINATOR, coordinator)
        self._artifact(ART_PLAN, plan, parent if ledger.artifact_exists(parent) else "", plan,
                       now, commit=commit)
        return ev

    def current_state(self, plan: str) -> str | None:
        evs = ledger.plan_events(plan)
        return evs[-1].get("to_state") if evs else None

    def plan_meta(self, plan: str) -> dict:
        evs = ledger.plan_events(plan)
        if not evs:
            raise UnknownPlanError(f"미등록 플랜 {plan}")
        g = evs[0]
        return {"plan_id": plan, "coordinator_id": g.get("coordinator_id"), "name": g.get("name"),
                "objective": g.get("objective"), "state": evs[-1].get("to_state")}

    def _require_plan(self, plan: str) -> str:
        st = self.current_state(plan)
        if st is None:
            raise UnknownPlanError(f"미등록 플랜 {plan}")
        return st

    def _require_editable(self, plan: str) -> str:
        st = self._require_plan(plan)
        if st not in EDITABLE_PLAN_STATES:
            raise PlanClosedError(f"{plan} 종료({st}) — 편집 불가")
        return st

    def _transition(self, plan: str, to: str, note: str, now: str, *, commit: bool) -> PlanEventRecord:
        frm = self._require_plan(plan)
        if not can_transition_plan(frm, to):
            raise IllegalPlanTransition(f"{plan} {frm}→{to} 불가")
        m = self.plan_meta(plan)
        ev = self._plan_event(plan, m["coordinator_id"], m["name"], m["objective"], frm, to, note,
                            now, commit=commit)
        self._event(plan, EV_PLAN_TRANSITION, plan, f"{frm}->{to}", now, commit=commit)
        return ev

    def start_planning(self, plan, now="", *, commit=False):
        return self._transition(plan, P_PLANNING, "planning", now, commit=commit)

    def start_assigning(self, plan, now="", *, commit=False):
        return self._transition(plan, P_ASSIGNING, "assigning", now, commit=commit)

    def start_running(self, plan, now="", *, commit=False):
        return self._transition(plan, P_RUNNING, "running", now, commit=commit)

    def mark_blocked(self, plan, now="", *, commit=False):
        return self._transition(plan, P_BLOCKED, "blocked", now, commit=commit)

    def resume_running(self, plan, now="", *, commit=False):
        return self._transition(plan, P_RUNNING, "resumed", now, commit=commit)

    def start_rebalancing(self, plan, now="", *, commit=False):
        return self._transition(plan, P_REBALANCING, "rebalancing", now, commit=commit)

    def archive_plan(self, plan, now="", *, commit=False):
        return self._transition(plan, P_ARCHIVED, "archived", now, commit=commit)

    # ══════════════ 태스크 배정(event-sourced) ══════════════
    def current_task(self, task: str) -> dict | None:
        evs = ledger.task_events(task)
        return evs[-1] if evs else None

    def _assignment_event(self, task: str, plan: str, task_name: str, owner: str, state: str,
                        is_reassign: bool, note: str, now: str, *, commit: bool) -> AssignmentEventRecord:
        seq = len(ledger.task_events(task))
        aeid = _assignment_event_id(task, seq)
        rec = AssignmentEventRecord(
            assignment_event_id=aeid, task_id=task, plan_id=plan, task_name=task_name, owner=owner,
            state=state, is_reassignment=is_reassign, note=note, occurred_at=now,
            input_hash=input_digest(task, seq), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.assignment_event_exists(aeid):
            head = ledger.assignments_head()
            ledger.append_assignment(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = _artifact_id(ART_PLAN, plan)
        self._artifact(ART_ASSIGNMENT, task, parent if ledger.artifact_exists(parent) else "",
                       plan, now, commit=commit)
        return AssignmentEventRecord(**rec)

    def assign_task(self, plan: str, task_name: str, owner: str, now: str = "",
                  *, commit: bool = False) -> AssignmentEventRecord:
        """연구 태스크 배정(ASSIGNED). **배정만 — 실행/결과 생성 아님.**"""
        self._require_editable(plan)
        task = _task_id(plan, task_name)
        cur = self.current_task(task)
        if cur is not None:
            return AssignmentEventRecord(**{k: v for k, v in cur.items()
                                            if k in AssignmentEventRecord.__dataclass_fields__})
        ev = self._assignment_event(task, plan, task_name, owner, T_ASSIGNED, False, "assigned",
                                  now, commit=commit)
        self._event(plan, EV_TASK_ASSIGNED, task, f"{task_name}->{owner}", now, commit=commit)
        return ev

    def reassign_task(self, plan: str, task_name: str, new_owner: str, now: str = "",
                    *, commit: bool = False) -> AssignmentEventRecord:
        """태스크 소유권 재분배(완료 태스크 불변). **소유권 이전만 — 결과 무수정.**"""
        self._require_editable(plan)
        task = _task_id(plan, task_name)
        cur = self.current_task(task)
        if cur is None:
            raise UnknownTaskError(f"미등록 태스크 {task_name}")
        if cur.get("state") == T_COMPLETED:
            raise CompletedTaskError(f"{task_name} 완료 — 재분배 불가(불변)")
        ev = self._assignment_event(task, plan, task_name, new_owner, T_ASSIGNED, True,
                                  f"reassigned from {cur.get('owner')}", now, commit=commit)
        self._event(plan, EV_TASK_REASSIGNED, task, f"{cur.get('owner')}->{new_owner}", now,
                    commit=commit)
        return ev

    # ══════════════ update_progress ══════════════
    def update_progress(self, plan: str, task_name: str, percent: int, state: str, note: str = "",
                      now: str = "", *, commit: bool = False) -> ProgressRecord:
        """태스크 진행 갱신 + 상태 전이(완료 태스크 불변). **진행 기록만 — 결과 무수정.**"""
        self._require_editable(plan)
        task = _task_id(plan, task_name)
        cur = self.current_task(task)
        if cur is None:
            raise UnknownTaskError(f"미등록 태스크 {task_name}")
        frm = cur.get("state")
        if frm == T_COMPLETED:
            raise CompletedTaskError(f"{task_name} 완료 — 진행 갱신 불가(불변)")
        if state != frm and not can_transition_task(frm, state):
            raise IllegalTaskTransition(f"{task_name} {frm}→{state} 불가")
        if state != frm:
            self._assignment_event(task, plan, task_name, cur.get("owner"), state, False,
                                 f"progress {percent}%", now, commit=commit)
        seq = len(ledger.task_progress(task))
        pid = _progress_id(task, seq)
        rec = ProgressRecord(progress_id=pid, task_id=task, plan_id=plan,
                             percent=max(0, min(100, int(percent))), state=state, note=note,
                             recorded_at=now, input_hash=input_digest(task, seq),
                             previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.progress_exists(pid):
            head = ledger.progress_head()
            ledger.append_progress(_seal(rec, head["record_hash"] if head else GENESIS))
        self._event(plan, EV_PROGRESS_UPDATED, task, f"{task_name}:{state}:{percent}%", now,
                    commit=commit)
        return ProgressRecord(**rec)

    # ══════════════ 의존성 그래프 ══════════════
    def add_dependency(self, plan: str, upstream_task: str, downstream_task: str, now: str = "",
                     *, commit: bool = False) -> DependencyRecord:
        """태스크 의존성 추가(upstream→downstream). 순환 거부(DAG 유지). **조율 구조만.**"""
        self._require_editable(plan)
        if upstream_task == downstream_task:
            raise SelfDependencyError(f"자기 의존성 {upstream_task}")
        up = _task_id(plan, upstream_task)
        dn = _task_id(plan, downstream_task)
        for t, nm in ((up, upstream_task), (dn, downstream_task)):
            if self.current_task(t) is None:
                raise UnknownTaskError(f"미등록 태스크 {nm}")
        did = _dependency_id(plan, up, dn)
        if ledger.dependency_exists(did):
            for r in ledger.plan_dependencies(plan):
                if r.get("dependency_id") == did:
                    return DependencyRecord(**{k: v for k, v in r.items()
                                               if k in DependencyRecord.__dataclass_fields__})
        edges = self._edges(plan) + [(up, dn)]
        cyc = detect_cycle(edges)
        if cyc:
            raise DependencyCycleError(f"순환 발생 — 거부: {'->'.join(cyc)}")
        rec = DependencyRecord(dependency_id=did, plan_id=plan, upstream_task=up,
                               downstream_task=dn, created_at=now,
                               input_hash=input_digest(plan, up, dn),
                               previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.dependency_exists(did):
            head = ledger.dependencies_head()
            ledger.append_dependency(_seal(rec, head["record_hash"] if head else GENESIS))
        self._event(plan, EV_DEPENDENCY_ADDED, did, f"{upstream_task}->{downstream_task}", now,
                    commit=commit)
        return DependencyRecord(**rec)

    def _nodes(self, plan: str) -> list:
        return sorted(ledger.plan_task_ids(plan))

    def _edges(self, plan: str) -> list:
        return [(d.get("upstream_task"), d.get("downstream_task"))
                for d in ledger.plan_dependencies(plan)]

    def build_schedule(self, plan: str, now: str = "", *, commit: bool = False) -> ScheduleRecord:
        """위상 순서·병렬 웨이브 스케줄 구성(결정적). **스케줄 메타 — 실행 트리거 아님.**"""
        self._require_plan(plan)
        nodes = self._nodes(plan)
        edges = self._edges(plan)
        order = topological_sort(nodes, edges) or []
        waves = build_waves(nodes, edges) or []
        seq = len(ledger.plan_schedules(plan))
        sid = _schedule_id(plan, seq)
        rec = ScheduleRecord(schedule_id=sid, plan_id=plan, order=order, waves=waves,
                             task_count=len(nodes), created_at=now, input_hash=input_digest(plan, seq),
                             previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.schedule_exists(sid):
            head = ledger.schedules_head()
            ledger.append_schedule(_seal(rec, head["record_hash"] if head else GENESIS))
        return ScheduleRecord(**rec)

    # ══════════════ detect_blocker (정체 탐지) ══════════════
    def detect_blocker(self, plan: str, now: str = "", *, commit: bool = False) -> dict:
        """정체·차단 태스크 탐지: BLOCKED 상태 + 의존성 미충족 대기 태스크. **탐지·기록만.**"""
        self._require_plan(plan)
        state_by_task = {t: (self.current_task(t) or {}).get("state") for t in self._nodes(plan)}
        completed = {t for t, s in state_by_task.items() if s == T_COMPLETED}
        blocked = sorted(t for t, s in state_by_task.items() if s == T_BLOCKED)
        waiting: list = []
        deps: dict = {}
        for u, d in self._edges(plan):
            deps.setdefault(d, set()).add(u)
        for t in self._nodes(plan):
            if state_by_task.get(t) == T_COMPLETED:
                continue
            ups = deps.get(t, set())
            if ups and not ups.issubset(completed):
                waiting.append(t)
        waiting = sorted(waiting)
        stalled = sorted(set(blocked) | set(waiting))
        if commit and stalled:
            self._event(plan, EV_BLOCKER_DETECTED, plan, f"{len(stalled)} stalled", now,
                        commit=commit)
        return {"blocked": blocked, "waiting": waiting, "stalled": stalled,
                "stalled_count": len(stalled)}

    # ══════════════ rebalance_workload (워크로드 균형) ══════════════
    def rebalance_workload(self, plan: str, now: str = "", *, commit: bool = False) -> WorkloadRecord:
        """소유자별 활성 태스크 워크로드 스냅샷·재분배 제안(결정적). **제안 기록만 — 자동 이전 아님.**"""
        self._require_plan(plan)
        dist: dict = {}
        for t in self._nodes(plan):
            cur = self.current_task(t) or {}
            if cur.get("state") == T_COMPLETED:
                continue
            owner = cur.get("owner")
            if owner:
                dist[owner] = dist.get(owner, 0) + 1
        dist = dict(sorted(dist.items()))
        imbalance = workload_imbalance(dist)
        moves = suggest_moves(dist)
        seq = len(ledger.plan_workloads(plan))
        wid = _workload_id(plan, seq)
        rec = WorkloadRecord(workload_id=wid, plan_id=plan, distribution=dist, imbalance=imbalance,
                             suggested_moves=moves, created_at=now, input_hash=input_digest(plan, seq),
                             previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.workload_exists(wid):
            head = ledger.workloads_head()
            ledger.append_workload(_seal(rec, head["record_hash"] if head else GENESIS))
        self._event(plan, EV_WORKLOAD_REBALANCED, wid, f"imbalance={imbalance}", now, commit=commit)
        return WorkloadRecord(**rec)

    # ══════════════ escalate_issue ══════════════
    def escalate_issue(self, plan: str, task_name: str, reason: str, severity: str = "WARNING",
                     now: str = "", *, commit: bool = False) -> EscalationRecord:
        """이슈 에스컬레이션 기록(불변). **보고만 — 조치 실행 아님.**"""
        self._require_plan(plan)
        if severity not in SEVERITIES:
            raise InvalidSeverity(f"미등록 심각도 {severity}")
        task = _task_id(plan, task_name) if task_name else ""
        seq = len(ledger.plan_escalations(plan))
        xid = _escalation_id(plan, task, seq)
        rec = EscalationRecord(escalation_id=xid, plan_id=plan, task_id=task, reason=reason,
                               severity=severity, resolved=False, created_at=now,
                               input_hash=input_digest(plan, task, seq),
                               previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.escalation_exists(xid):
            head = ledger.escalations_head()
            ledger.append_escalation(_seal(rec, head["record_hash"] if head else GENESIS))
        self._event(plan, EV_ISSUE_ESCALATED, xid, f"{severity}:{reason}", now, commit=commit)
        return EscalationRecord(**rec)

    # ══════════════ complete_plan ══════════════
    def complete_plan(self, plan: str, now: str = "", *, commit: bool = False) -> PlanEventRecord:
        """플랜 완료(RUNNING→COMPLETED). **완료 기록만.**"""
        return self._transition(plan, P_COMPLETED, "completed", now, commit=commit)

    # ══════════════ generate_report ══════════════
    def generate_report(self, plan: str, scope: str = "PLAN", now: str = "",
                      *, commit: bool = False) -> CompletionReportRecord:
        """조율/완료 리포트(태스크·완료·차단·의존성·DAG·에스컬레이션). **관측 리포트 — is_binding=False.**"""
        st = self._require_plan(plan)
        m = self.plan_meta(plan)
        nodes = self._nodes(plan)
        completed = sum(1 for t in nodes if (self.current_task(t) or {}).get("state") == T_COMPLETED)
        blocked = sum(1 for t in nodes if (self.current_task(t) or {}).get("state") == T_BLOCKED)
        edges = self._edges(plan)
        rid = _report_id(plan, scope, now)
        rec = CompletionReportRecord(
            report_id=rid, plan_id=plan, coordinator_id=m["coordinator_id"], scope=scope,
            lifecycle_state=st, task_count=len(nodes), completed_count=completed,
            blocked_count=blocked, dependency_count=len(edges),
            is_dag=topological_sort(nodes, edges) is not None,
            escalation_count=len(ledger.plan_escalations(plan)), is_binding=False,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(plan, scope, now),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = _artifact_id(ART_PLAN, plan)
        self._artifact(ART_REPORT, rid, parent if ledger.artifact_exists(parent) else "", plan,
                       now, commit=commit)
        return CompletionReportRecord(**rec)

    # ══════════════ verify_integrity ══════════════
    def verify_integrity(self) -> dict:
        from jarvis.research_coordinator.verify import verify_chain
        return verify_chain()

    # ══════════════ 조회 편의 ══════════════
    def list_plans(self, coordinator: str = "") -> list:
        pids = ledger.plan_ids()
        if coordinator:
            pids = [p for p in pids
                    if any(ev.get("coordinator_id") == coordinator for ev in ledger.plan_events(p))]
        return sorted(pids)

    def list_tasks(self, plan: str) -> list:
        return sorted((self.current_task(t) or {}).get("task_name")
                      for t in self._nodes(plan) if self.current_task(t))

    def task_owner(self, plan: str, task_name: str) -> str:
        cur = self.current_task(_task_id(plan, task_name))
        return cur.get("owner") if cur else ""

    def task_state(self, plan: str, task_name: str) -> str:
        cur = self.current_task(_task_id(plan, task_name))
        return cur.get("state") if cur else ""

    # ══════════════ Summary ══════════════
    def summary(self, now: str = "") -> CoordinatorSummary:
        return CoordinatorSummary(
            timestamp=now, coordinator_count=len(ledger.read_coordinators()),
            plan_event_count=len(ledger.read_plan_events()),
            assignment_event_count=len(ledger.read_assignments()),
            dependency_count=len(ledger.read_dependencies()),
            progress_count=len(ledger.read_progress()), schedule_count=len(ledger.read_schedules()),
            workload_count=len(ledger.read_workloads()), event_count=len(ledger.read_events()),
            escalation_count=len(ledger.read_escalations()), report_count=len(ledger.read_reports()),
            artifact_count=len(ledger.read_artifacts()))
