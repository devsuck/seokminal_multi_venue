"""Research Operations Engine (P18) — 워크플로 조정·계획·추적. **조정·기록 전용, 실행 없음.**

**거래·전략 배포·권한 변경·자동 실행·자동 승인을 하지 않는다.** execution/broker/portfolio/permission/deployment/
live import·호출 없음. ORCHESTRATE ≠ EXECUTE · PLAN ≠ DEPLOYMENT · SCHEDULE ≠ TRADING. 결정적·불변·append-only·
이벤트 소싱.
"""
from __future__ import annotations

from jarvis.research_operations import ledger
from jarvis.research_operations.models import (
    ART_REPORT,
    ART_RUN,
    ART_TASK,
    ART_WORKFLOW,
    GENESIS,
    T_COMPLETED,
    T_CREATED,
    T_FAILED,
    T_QUEUED,
    T_RUNNING,
    W_ARCHIVED,
    W_COMPLETED,
    W_DEFINED,
    W_DRAFT,
    W_FAILED,
    W_PAUSED,
    W_READY,
    W_RUNNING,
    ArtifactRecord,
    CircularDependencyError,
    DanglingDependencyError,
    DependencyRecord,
    ExecutionPlanRecord,
    IllegalTaskTransition,
    IllegalWorkflowTransition,
    ImmutableTaskError,
    ImmutableWorkflowError,
    OperationReportRecord,
    OperationsSummary,
    OrchestrationEventRecord,
    RunRecord,
    TaskEventRecord,
    UnknownTaskError,
    UnknownWorkflowError,
    WorkflowEventRecord,
    artifact_id as _artifact_id,
    can_task_transition,
    can_workflow_transition,
    content_hash,
    dependency_id as _dependency_id,
    detect_cycle,
    event_id as _event_id,
    input_digest,
    plan_id as _plan_id,
    report_id as _report_id,
    run_id as _run_id,
    task_event_id as _task_event_id,
    task_id as _task_id,
    topological_order,
    workflow_event_id as _workflow_event_id,
    workflow_id as _workflow_id,
)

_DISCLAIMER = ("Research Operations 데이터 — ORCHESTRATE ≠ EXECUTE · PLAN ≠ DEPLOYMENT · SCHEDULE ≠ TRADING. "
               "연구 워크플로 조정·계획·추적 전용 — 거래·전략 배포·권한 변경·자동 실행·자동 승인 없음.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchOperationsEngine:
    """연구 운영 오케스트레이터. 불변·append-only·이벤트 소싱·결정적. 실행/배포/거래/승인 권한 없음."""

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

    # ══════════════ 이벤트 로그(record_event) ══════════════
    def record_event(self, workflow: str, event_type: str, subject: str = "", detail: str = "",
                  metadata: dict | None = None, now: str = "",
                  *, commit: bool = False) -> OrchestrationEventRecord:
        """오케스트레이션 이벤트 기록(불변). **기록만 — 외부 동작 없음.**"""
        seq = len(ledger.read_events())
        eid = _event_id(workflow, event_type, seq)
        rec = OrchestrationEventRecord(event_id=eid, workflow_id=workflow, event_type=event_type,
                                       subject=subject, detail=detail,
                                       metadata=dict(metadata or {}), recorded_at=now,
                                       input_hash=input_digest(workflow, event_type, seq),
                                       previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.event_exists(eid):
            head = ledger.events_head()
            ledger.append_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return OrchestrationEventRecord(**rec)

    # ══════════════ 워크플로 생애주기(event-sourced) ══════════════
    def _wf_event(self, wf: str, name: str, desc: str, frm: str, to: str, note: str, now: str,
               *, commit: bool) -> WorkflowEventRecord:
        seq = len(ledger.workflow_events(wf))
        eid = _workflow_event_id(wf, to, seq)
        rec = WorkflowEventRecord(workflow_event_id=eid, workflow_id=wf, name=name,
                                  description=desc, from_state=frm, to_state=to, note=note,
                                  occurred_at=now, input_hash=input_digest(wf, to, seq),
                                  previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.workflow_event_exists(eid):
            head = ledger.workflows_head()
            ledger.append_workflow_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return WorkflowEventRecord(**rec)

    def _wf_meta(self, wf: str) -> dict:
        evs = ledger.workflow_events(wf)
        if not evs:
            raise UnknownWorkflowError(f"미등록 워크플로 {wf}")
        g = evs[0]
        return {"workflow_id": wf, "name": g.get("name"), "description": g.get("description"),
                "state": evs[-1].get("to_state")}

    def workflow_state(self, wf: str) -> str | None:
        evs = ledger.workflow_events(wf)
        return evs[-1].get("to_state") if evs else None

    def _require_workflow(self, wf: str) -> str:
        st = self.workflow_state(wf)
        if st is None:
            raise UnknownWorkflowError(f"미등록 워크플로 {wf}")
        return st

    def _wf_transition(self, wf: str, to: str, note: str, now: str,
                    *, commit: bool) -> WorkflowEventRecord:
        frm = self._require_workflow(wf)
        if not can_workflow_transition(frm, to):
            raise IllegalWorkflowTransition(f"{wf} {frm}→{to} 불가")
        m = self._wf_meta(wf)
        return self._wf_event(wf, m["name"], m["description"], frm, to, note, now, commit=commit)

    # ══════════════ create_workflow ══════════════
    def create_workflow(self, name: str, description: str = "", now: str = "",
                     *, commit: bool = False) -> WorkflowEventRecord:
        """연구 워크플로 생성(genesis DRAFT). **정의 시작만.**"""
        wid = _workflow_id(name)
        evs = ledger.workflow_events(wid)
        if evs:
            g = evs[0]
            if g.get("description") != description:
                raise ImmutableWorkflowError(f"{wid} 워크플로 불변 — 변경 불가")
            return WorkflowEventRecord(**{k: v for k, v in g.items()
                                          if k in WorkflowEventRecord.__dataclass_fields__})
        ev = self._wf_event(wid, name, description, GENESIS, W_DRAFT, "created", now, commit=commit)
        self._artifact(ART_WORKFLOW, wid, "", now, commit=commit)
        self.record_event(wid, "WORKFLOW_CREATED", wid, name, {}, now, commit=commit)
        return ev

    def define_workflow(self, wf: str, now: str = "", *, commit: bool = False) -> WorkflowEventRecord:
        """DRAFT→DEFINED. **정의 완료 표기.**"""
        return self._wf_transition(wf, W_DEFINED, "defined", now, commit=commit)

    def ready_workflow(self, wf: str, now: str = "", *, commit: bool = False) -> WorkflowEventRecord:
        """DEFINED→READY. 작업 ≥1 필요. **실행 준비 표기(자동 실행 아님).**"""
        if not ledger.workflow_tasks(wf):
            raise IllegalWorkflowTransition(f"{wf} 작업 없음 — READY 불가")
        return self._wf_transition(wf, W_READY, "ready", now, commit=commit)

    def pause_workflow(self, wf: str, now: str = "", *, commit: bool = False) -> WorkflowEventRecord:
        return self._wf_transition(wf, W_PAUSED, "paused", now, commit=commit)

    def resume_workflow(self, wf: str, now: str = "", *, commit: bool = False) -> WorkflowEventRecord:
        return self._wf_transition(wf, W_RUNNING, "resumed", now, commit=commit)

    def complete_workflow(self, wf: str, now: str = "", *, commit: bool = False) -> WorkflowEventRecord:
        ev = self._wf_transition(wf, W_COMPLETED, "completed", now, commit=commit)
        self.record_event(wf, "WORKFLOW_COMPLETED", wf, "", {}, now, commit=commit)
        return ev

    def fail_workflow(self, wf: str, now: str = "", *, commit: bool = False) -> WorkflowEventRecord:
        ev = self._wf_transition(wf, W_FAILED, "failed", now, commit=commit)
        self.record_event(wf, "WORKFLOW_FAILED", wf, "", {}, now, commit=commit)
        return ev

    def archive_workflow(self, wf: str, now: str = "", *, commit: bool = False) -> WorkflowEventRecord:
        return self._wf_transition(wf, W_ARCHIVED, "archived", now, commit=commit)

    # ══════════════ 작업 생애주기(event-sourced) ══════════════
    def _task_event(self, task: str, wf: str, name: str, desc: str, owner: str, priority: int,
                 frm: str, to: str, note: str, metadata: dict, now: str,
                 *, commit: bool) -> TaskEventRecord:
        seq = len(ledger.task_events(task))
        eid = _task_event_id(task, to, seq)
        rec = TaskEventRecord(task_event_id=eid, task_id=task, workflow_id=wf, name=name,
                              description=desc, owner=owner, priority=int(priority), from_status=frm,
                              to_status=to, note=note, metadata=dict(metadata or {}),
                              occurred_at=now, input_hash=input_digest(task, to, seq),
                              previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.task_event_exists(eid):
            head = ledger.tasks_head()
            ledger.append_task_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return TaskEventRecord(**rec)

    def _task_meta(self, task: str) -> dict:
        evs = ledger.task_events(task)
        if not evs:
            raise UnknownTaskError(f"미등록 작업 {task}")
        g = evs[0]
        return {"task_id": task, "workflow_id": g.get("workflow_id"), "name": g.get("name"),
                "description": g.get("description"), "owner": g.get("owner"),
                "priority": g.get("priority"), "metadata": g.get("metadata", {}),
                "status": evs[-1].get("to_status")}

    def task_status(self, task: str) -> str | None:
        evs = ledger.task_events(task)
        return evs[-1].get("to_status") if evs else None

    def _require_task(self, task: str) -> str:
        st = self.task_status(task)
        if st is None:
            raise UnknownTaskError(f"미등록 작업 {task}")
        return st

    def _task_transition(self, task: str, to: str, note: str, now: str,
                      *, commit: bool) -> TaskEventRecord:
        frm = self._require_task(task)
        if not can_task_transition(frm, to):
            raise IllegalTaskTransition(f"{task} {frm}→{to} 불가")
        m = self._task_meta(task)
        return self._task_event(task, m["workflow_id"], m["name"], m["description"], m["owner"],
                                m["priority"], frm, to, note, m["metadata"], now, commit=commit)

    # ══════════════ add_task ══════════════
    def add_task(self, workflow: str, name: str, description: str = "", owner: str = "",
              priority: int = 0, metadata: dict | None = None, now: str = "",
              *, commit: bool = False) -> TaskEventRecord:
        """작업 생성(genesis CREATED). 워크플로 정의 단계에서만. **정의만.**"""
        st = self._require_workflow(workflow)
        if st not in (W_DRAFT, W_DEFINED):
            raise IllegalWorkflowTransition(f"{workflow} 상태 {st} — 작업 추가 불가(정의 단계만)")
        tid = _task_id(workflow, name)
        existing = ledger.task_events(tid)
        if existing:
            g = existing[0]
            if g.get("description") != description:
                raise ImmutableTaskError(f"{tid} 작업 불변 — 변경 불가")
            return TaskEventRecord(**{k: v for k, v in g.items()
                                      if k in TaskEventRecord.__dataclass_fields__})
        if st == W_DRAFT:
            self._wf_transition(workflow, W_DEFINED, "defining", now, commit=commit)
        ev = self._task_event(tid, workflow, name, description, owner, priority, GENESIS, T_CREATED,
                              "created", metadata or {}, now, commit=commit)
        parent = _artifact_id(ART_WORKFLOW, workflow)
        self._artifact(ART_TASK, tid, parent if ledger.artifact_exists(parent) else "", now,
                       commit=commit)
        self.record_event(workflow, "TASK_CREATED", tid, name, {}, now, commit=commit)
        return ev

    def queue_task(self, task: str, now: str = "", *, commit: bool = False) -> TaskEventRecord:
        return self._task_transition(task, T_QUEUED, "queued", now, commit=commit)

    def start_task(self, task: str, now: str = "", *, commit: bool = False) -> TaskEventRecord:
        return self._task_transition(task, T_RUNNING, "running", now, commit=commit)

    def complete_task(self, task: str, now: str = "", *, commit: bool = False) -> TaskEventRecord:
        """작업 완료(RUNNING→COMPLETED). **진행 기록만.**"""
        ev = self._task_transition(task, T_COMPLETED, "completed", now, commit=commit)
        self.record_event(self._task_meta(task)["workflow_id"], "TASK_COMPLETED", task, "", {},
                          now, commit=commit)
        return ev

    def fail_task(self, task: str, now: str = "", *, commit: bool = False) -> TaskEventRecord:
        """작업 실패(RUNNING→FAILED). **진행 기록만.**"""
        ev = self._task_transition(task, T_FAILED, "failed", now, commit=commit)
        self.record_event(self._task_meta(task)["workflow_id"], "TASK_FAILED", task, "", {},
                          now, commit=commit)
        return ev

    def block_task(self, task: str, now: str = "", *, commit: bool = False) -> TaskEventRecord:
        from jarvis.research_operations.models import T_BLOCKED
        return self._task_transition(task, T_BLOCKED, "blocked", now, commit=commit)

    def cancel_task(self, task: str, now: str = "", *, commit: bool = False) -> TaskEventRecord:
        from jarvis.research_operations.models import T_CANCELLED
        return self._task_transition(task, T_CANCELLED, "cancelled", now, commit=commit)

    # ══════════════ add_dependency (DAG) ══════════════
    def _dep_edges(self) -> list:
        return [(r.get("task_id"), r.get("depends_on")) for r in ledger.read_dependencies()]

    def add_dependency(self, task: str, depends_on: str, now: str = "",
                    *, commit: bool = False) -> DependencyRecord:
        """작업 의존 추가(불변). DAG 강제 — dangling·순환 거부. **매핑만.**"""
        wf = self._task_meta(task)["workflow_id"]
        if self.task_status(depends_on) is None:
            raise DanglingDependencyError(f"무효 의존 작업 {depends_on}")
        if task == depends_on:
            raise CircularDependencyError(f"자기 의존 불가 {task}")
        did = _dependency_id(task, depends_on)
        existing = ledger.dependency_exists(did)
        if not existing:
            edges = self._dep_edges() + [(task, depends_on)]
            if detect_cycle(edges):
                raise CircularDependencyError(f"순환 의존 — 거부 {task}->{depends_on}")
        rec = DependencyRecord(dependency_id=did, task_id=task, depends_on=depends_on,
                               workflow_id=wf, created_at=now,
                               input_hash=input_digest(task, depends_on),
                               previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not existing:
            head = ledger.dependencies_head()
            ledger.append_dependency(_seal(rec, head["record_hash"] if head else GENESIS))
        self.record_event(wf, "DEPENDENCY_ADDED", task, depends_on, {}, now, commit=commit)
        return DependencyRecord(**rec)

    def task_order(self, workflow: str) -> list:
        """워크플로 작업의 의존 위상 정렬(결정적). 순환이면 []."""
        tasks = ledger.workflow_tasks(workflow)
        tset = set(tasks)
        edges = [(d.get("task_id"), d.get("depends_on")) for d in ledger.read_dependencies()
                 if d.get("task_id") in tset and d.get("depends_on") in tset]
        return topological_order(tasks, edges)

    def missing_dependencies(self, workflow: str) -> list:
        """워크플로 밖(미등록) 작업을 참조하는 의존 목록."""
        tset = set(ledger.workflow_tasks(workflow))
        out = []
        for d in ledger.read_dependencies():
            if d.get("workflow_id") == workflow and d.get("depends_on") not in tset:
                out.append(d.get("dependency_id"))
        return sorted(out)

    # ══════════════ 스케줄링(계획 제안만) ══════════════
    def build_execution_plan(self, workflow: str, now: str = "",
                          *, commit: bool = False) -> ExecutionPlanRecord:
        """실행 계획 제안(위상 순서·우선순위·자원 추정·예상 소요·의존 준비). **제안일 뿐 자동 실행 없음.**"""
        self._require_workflow(workflow)
        order = self.task_order(workflow)
        priorities: dict = {}
        resource = 0.0
        duration = 0.0
        for t in ledger.workflow_tasks(workflow):
            m = self._task_meta(t)
            priorities[t] = m["priority"]
            md = m.get("metadata") or {}
            resource += float(md.get("resource", 0) or 0)
            duration += float(md.get("duration", 0) or 0)
        dep_ready = order != [] or not ledger.workflow_tasks(workflow)
        pid = _plan_id(workflow, now)
        rec = ExecutionPlanRecord(
            plan_id=pid, workflow_id=workflow,
            ordered_tasks=sorted(order, key=lambda t: (-priorities.get(t, 0), order.index(t))),
            priorities=dict(sorted(priorities.items())), resource_estimate=round(resource, 6),
            expected_duration=round(duration, 6), dependency_ready=dep_ready, is_proposal=True,
            created_at=now, input_hash=input_digest(workflow, now), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.plan_exists(pid):
            head = ledger.plans_head()
            ledger.append_plan(_seal(rec, head["record_hash"] if head else GENESIS))
        return ExecutionPlanRecord(**rec)

    # ══════════════ start_run ══════════════
    def start_run(self, workflow: str, plan: str = "", note: str = "", now: str = "",
               *, commit: bool = False) -> RunRecord:
        """런 시작 기록 + 워크플로 READY→RUNNING. **진행 추적만 — 외부 실행 아님.**"""
        st = self._require_workflow(workflow)
        if st == W_READY:
            self._wf_transition(workflow, W_RUNNING, "run started", now, commit=commit)
        seq = len(ledger.workflow_runs(workflow))
        rid = _run_id(workflow, seq)
        rec = RunRecord(run_id=rid, workflow_id=workflow, plan_id=plan, note=note, started_at=now,
                        input_hash=input_digest(workflow, seq), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.run_exists(rid):
            head = ledger.runs_head()
            ledger.append_run(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = _artifact_id(ART_WORKFLOW, workflow)
        self._artifact(ART_RUN, rid, parent if ledger.artifact_exists(parent) else "", now,
                       commit=commit)
        self.record_event(workflow, "RUN_STARTED", rid, "", {}, now, commit=commit)
        return RunRecord(**rec)

    # ══════════════ generate_report ══════════════
    def generate_report(self, workflow: str, scope: str = "WORKFLOW", now: str = "",
                     *, commit: bool = False) -> OperationReportRecord:
        """운영 리포트(작업 상태 분포·의존·런·이벤트). **is_binding=False, 관찰·보고만.**"""
        self._require_workflow(workflow)
        tasks = ledger.workflow_tasks(workflow)
        dist: dict = {}
        for t in tasks:
            s = self.task_status(t)
            dist[s] = dist.get(s, 0) + 1
        dep_count = len([d for d in ledger.read_dependencies()
                         if d.get("workflow_id") == workflow])
        rid = _report_id(workflow, scope, now)
        rec = OperationReportRecord(
            report_id=rid, workflow_id=workflow, scope=scope, workflow_state=self.workflow_state(workflow),
            task_count=len(tasks), task_status_distribution=dict(sorted(dist.items())),
            dependency_count=dep_count, run_count=len(ledger.workflow_runs(workflow)),
            event_count=len(ledger.workflow_event_log(workflow)), is_binding=False,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(workflow, scope, now),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = _artifact_id(ART_WORKFLOW, workflow)
        self._artifact(ART_REPORT, rid, parent if ledger.artifact_exists(parent) else "", now,
                       commit=commit)
        return OperationReportRecord(**rec)

    # ══════════════ verify / 조회 / summary ══════════════
    def verify_integrity(self) -> dict:
        from jarvis.research_operations.verify import verify_chain
        return verify_chain()

    def list_workflows(self) -> list:
        return ledger.workflow_ids()

    def workflows_in_state(self, state: str) -> list:
        return sorted(w for w in ledger.workflow_ids() if self.workflow_state(w) == state)

    def list_tasks(self, workflow: str) -> list:
        return ledger.workflow_tasks(workflow)

    def workflow_meta(self, workflow: str) -> dict:
        return self._wf_meta(workflow)

    def task_meta(self, task: str) -> dict:
        return self._task_meta(task)

    def summary(self, now: str = "") -> OperationsSummary:
        return OperationsSummary(
            timestamp=now, workflow_event_count=len(ledger.read_workflow_events()),
            task_event_count=len(ledger.read_task_events()),
            dependency_count=len(ledger.read_dependencies()), run_count=len(ledger.read_runs()),
            plan_count=len(ledger.read_plans()), event_count=len(ledger.read_events()),
            report_count=len(ledger.read_reports()), artifact_count=len(ledger.read_artifacts()))
