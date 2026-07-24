"""Research Automation Engine (P22) — 연구 워크플로/파이프라인/작업 자동화 조정·기록. **실행 없음.**

**거래·주문·자본 배분·전략 배포·모델 수정·권한 변경·라이브 승인을 하지 않는다.** execution/broker/portfolio_live/
permission_control/risk_execution import·호출 없음. ORCHESTRATE ≠ EXECUTE · COMPLETED ≠ VALIDATED · VALIDATED ≠
DEPLOYED · RECOMMENDED ≠ ENABLED. 결정적·불변·append-only·이벤트 소싱. 상위 계층은 READ ONLY.
"""
from __future__ import annotations

from jarvis.research_automation import ledger
from jarvis.research_automation import models as M
from jarvis.research_automation.models import (
    GENESIS,
    ArtifactRecord,
    AutomationEventRecord,
    AutomationReportRecord,
    AutomationSummary,
    CircularDependencyError,
    DanglingDependencyError,
    DependencyRecord,
    IllegalPipelineTransition,
    IllegalTaskTransition,
    IllegalWorkflowTransition,
    ImmutablePipelineError,
    ImmutableTaskError,
    ImmutableWorkflowError,
    PipelineEventRecord,
    RunRecord,
    TaskEventRecord,
    UnknownEntityError,
    WorkflowEventRecord,
    content_hash,
    input_digest,
)

_DISCLAIMER = ("Research Automation Orchestration 데이터 — ORCHESTRATE ≠ EXECUTE · COMPLETED ≠ VALIDATED · "
               "VALIDATED ≠ DEPLOYED · RECOMMENDED ≠ ENABLED. 연구 자동화 조정·기록 전용 — 거래·주문·자본 배분·전략 배포·"
               "모델 수정·권한 변경·라이브 승인 없음.")


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchAutomationEngine:
    """연구 자동화 오케스트레이터. 불변·append-only·이벤트 소싱·결정적. 실행/배포/거래/승인 권한 없음."""

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

    def record_event(self, scope, event_type, subject="", detail="", now="",
                     *, commit=False) -> AutomationEventRecord:
        """자동화 감사 이벤트 기록(불변). **기록만 — 외부 동작 없음.**"""
        seq = len(ledger.read_events())
        eid = M.event_id(scope, event_type, seq)
        rec = AutomationEventRecord(event_id=eid, scope_id=scope, event_type=event_type,
                                    subject=subject, detail=detail, recorded_at=now,
                                    input_hash=input_digest(scope, event_type, seq),
                                    previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.event_exists, ledger.events_head, ledger.append_event, eid, rec,
                         commit=commit)
        return AutomationEventRecord(**rec)

    # ══════════════ 워크플로 생애주기(event-sourced) ══════════════
    def _wf_event(self, wf, name, version, desc, layers, frm, to, note, now, *, commit):
        seq = len(ledger.workflow_events(wf))
        eid = M.workflow_event_id(wf, to, seq)
        rec = WorkflowEventRecord(workflow_event_id=eid, workflow_id=wf, name=name, version=version,
                                  description=desc, source_layers=list(layers or []), from_state=frm,
                                  to_state=to, note=note, occurred_at=now,
                                  input_hash=input_digest(wf, to, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.workflow_event_exists, ledger.workflows_head,
                         ledger.append_workflow_event, eid, rec, commit=commit)
        return WorkflowEventRecord(**rec)

    def _wf_meta(self, wf) -> dict:
        evs = ledger.workflow_events(wf)
        if not evs:
            raise UnknownEntityError(f"미등록 워크플로 {wf}")
        g = evs[0]
        return {"name": g.get("name"), "version": g.get("version"), "description": g.get("description"),
                "source_layers": g.get("source_layers", []), "state": evs[-1].get("to_state")}

    def workflow_state(self, wf) -> str | None:
        evs = ledger.workflow_events(wf)
        return evs[-1].get("to_state") if evs else None

    def _require_workflow(self, wf) -> str:
        st = self.workflow_state(wf)
        if st is None:
            raise UnknownEntityError(f"미등록 워크플로 {wf}")
        return st

    def _wf_transition(self, wf, to, note, now, *, commit):
        frm = self._require_workflow(wf)
        if not M.can_workflow_transition(frm, to):
            raise IllegalWorkflowTransition(f"워크플로 {wf} {frm}→{to} 불가")
        m = self._wf_meta(wf)
        return self._wf_event(wf, m["name"], m["version"], m["description"], m["source_layers"],
                              frm, to, note, now, commit=commit)

    def register_workflow(self, name, version="1.0", description="", source_layers=None, now="",
                          *, commit=False) -> WorkflowEventRecord:
        """연구 워크플로 등록(genesis DRAFT). **정의만.**"""
        wf = M.workflow_id(name, version)
        evs = ledger.workflow_events(wf)
        if evs:
            g = evs[0]
            if g.get("description") != description:
                raise ImmutableWorkflowError(f"{wf} 워크플로 불변")
            return WorkflowEventRecord(**{k: v for k, v in g.items()
                                          if k in WorkflowEventRecord.__dataclass_fields__})
        ev = self._wf_event(wf, name, version, description, source_layers or [], GENESIS, M.W_DRAFT,
                            "registered", now, commit=commit)
        self._artifact(M.ART_WORKFLOW, wf, "", now, commit=commit)
        self.record_event(wf, "WORKFLOW_REGISTERED", wf, name, now, commit=commit)
        return ev

    def activate_workflow(self, wf, now="", *, commit=False):
        return self._wf_transition(wf, M.W_ACTIVE, "active", now, commit=commit)

    def run_workflow(self, wf, now="", *, commit=False):
        return self._wf_transition(wf, M.W_RUNNING, "running", now, commit=commit)

    def complete_workflow(self, wf, now="", *, commit=False):
        return self._wf_transition(wf, M.W_COMPLETED, "completed", now, commit=commit)

    def archive_workflow(self, wf, now="", *, commit=False):
        return self._wf_transition(wf, M.W_ARCHIVED, "archived", now, commit=commit)

    # ══════════════ 파이프라인 생애주기(event-sourced) ══════════════
    def _pipe_event(self, pipe, wf, name, steps, frm, to, note, now, *, commit):
        seq = len(ledger.pipeline_events(pipe))
        eid = M.pipeline_event_id(pipe, to, seq)
        rec = PipelineEventRecord(pipeline_event_id=eid, pipeline_id=pipe, workflow_id=wf, name=name,
                                  steps=list(steps or []), from_state=frm, to_state=to, note=note,
                                  occurred_at=now, input_hash=input_digest(pipe, to, seq),
                                  previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.pipeline_event_exists, ledger.pipelines_head,
                         ledger.append_pipeline_event, eid, rec, commit=commit)
        return PipelineEventRecord(**rec)

    def _pipe_meta(self, pipe) -> dict:
        evs = ledger.pipeline_events(pipe)
        if not evs:
            raise UnknownEntityError(f"미등록 파이프라인 {pipe}")
        g = evs[0]
        return {"workflow_id": g.get("workflow_id"), "name": g.get("name"), "steps": g.get("steps", []),
                "state": evs[-1].get("to_state")}

    def pipeline_state(self, pipe) -> str | None:
        evs = ledger.pipeline_events(pipe)
        return evs[-1].get("to_state") if evs else None

    def _pipe_transition(self, pipe, to, note, now, *, commit):
        st = self.pipeline_state(pipe)
        if st is None:
            raise UnknownEntityError(f"미등록 파이프라인 {pipe}")
        if not M.can_pipeline_transition(st, to):
            raise IllegalPipelineTransition(f"파이프라인 {pipe} {st}→{to} 불가")
        m = self._pipe_meta(pipe)
        return self._pipe_event(pipe, m["workflow_id"], m["name"], m["steps"], st, to, note, now,
                                commit=commit)

    def define_pipeline(self, workflow, name, steps=None, now="", *, commit=False) -> PipelineEventRecord:
        """자동화 파이프라인 정의(genesis CREATED). 워크플로 ACTIVE 필요."""
        st = self._require_workflow(workflow)
        if st not in (M.W_ACTIVE, M.W_RUNNING):
            if st == M.W_DRAFT:
                self._wf_transition(workflow, M.W_ACTIVE, "activating for pipeline", now, commit=commit)
            else:
                raise IllegalWorkflowTransition(f"워크플로 {workflow} 상태 {st} — 파이프라인 정의 불가")
        pipe = M.pipeline_id(workflow, name)
        evs = ledger.pipeline_events(pipe)
        if evs:
            g = evs[0]
            if g.get("steps") != list(steps or []):
                raise ImmutablePipelineError(f"{pipe} 파이프라인 불변")
            return PipelineEventRecord(**{k: v for k, v in g.items()
                                          if k in PipelineEventRecord.__dataclass_fields__})
        ev = self._pipe_event(pipe, workflow, name, steps or [], GENESIS, M.P_CREATED, "created",
                              now, commit=commit)
        parent = M.artifact_id(M.ART_WORKFLOW, workflow)
        self._artifact(M.ART_PIPELINE, pipe, parent if ledger.artifact_exists(parent) else "", now,
                       commit=commit)
        self.record_event(pipe, "PIPELINE_DEFINED", pipe, name, now, commit=commit)
        return ev

    def ready_pipeline(self, pipe, now="", *, commit=False):
        """CREATED→READY. 작업 ≥1 필요."""
        if not ledger.pipeline_tasks(pipe):
            raise IllegalPipelineTransition(f"{pipe} 작업 없음 — READY 불가")
        return self._pipe_transition(pipe, M.P_READY, "ready", now, commit=commit)

    def finish_pipeline(self, pipe, now="", *, commit=False):
        return self._pipe_transition(pipe, M.P_FINISHED, "finished", now, commit=commit)

    # ══════════════ 작업 생애주기(event-sourced) ══════════════
    def _task_event(self, task, pipe, wf, ttype, name, inref, frm, to, results, note, now, *, commit):
        seq = len(ledger.task_events(task))
        eid = M.task_event_id(task, to, seq)
        rec = TaskEventRecord(task_event_id=eid, task_id=task, pipeline_id=pipe, workflow_id=wf,
                              task_type=ttype, name=name, input_reference=inref, from_state=frm,
                              to_state=to, results=dict(results or {}), note=note, occurred_at=now,
                              input_hash=input_digest(task, to, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.task_event_exists, ledger.tasks_head, ledger.append_task_event, eid,
                         rec, commit=commit)
        return TaskEventRecord(**rec)

    def _task_meta(self, task) -> dict:
        evs = ledger.task_events(task)
        if not evs:
            raise UnknownEntityError(f"미등록 작업 {task}")
        g = evs[0]
        return {"pipeline_id": g.get("pipeline_id"), "workflow_id": g.get("workflow_id"),
                "task_type": g.get("task_type"), "name": g.get("name"),
                "input_reference": g.get("input_reference"), "state": evs[-1].get("to_state")}

    def task_state(self, task) -> str | None:
        evs = ledger.task_events(task)
        return evs[-1].get("to_state") if evs else None

    def _task_transition(self, task, to, results, note, now, *, commit):
        st = self.task_state(task)
        if st is None:
            raise UnknownEntityError(f"미등록 작업 {task}")
        if not M.can_task_transition(st, to):
            raise IllegalTaskTransition(f"작업 {task} {st}→{to} 불가")
        m = self._task_meta(task)
        return self._task_event(task, m["pipeline_id"], m["workflow_id"], m["task_type"], m["name"],
                                m["input_reference"], st, to, results, note, now, commit=commit)

    def create_task(self, pipeline, name, task_type="research", input_reference="", now="",
                    *, commit=False) -> TaskEventRecord:
        """연구 작업 생성(genesis CREATED). 파이프라인 CREATED/READY 단계에서만."""
        st = self.pipeline_state(pipeline)
        if st is None:
            raise UnknownEntityError(f"미등록 파이프라인 {pipeline}")
        if st not in (M.P_CREATED, M.P_READY):
            raise IllegalPipelineTransition(f"파이프라인 {pipeline} 상태 {st} — 작업 추가 불가")
        m = self._pipe_meta(pipeline)
        tid = M.task_id(pipeline, name)
        evs = ledger.task_events(tid)
        if evs:
            g = evs[0]
            if g.get("task_type") != task_type:
                raise ImmutableTaskError(f"{tid} 작업 불변")
            return TaskEventRecord(**{k: v for k, v in g.items()
                                      if k in TaskEventRecord.__dataclass_fields__})
        ev = self._task_event(tid, pipeline, m["workflow_id"], task_type, name, input_reference,
                              GENESIS, M.T_CREATED, {}, "created", now, commit=commit)
        parent = M.artifact_id(M.ART_PIPELINE, pipeline)
        self._artifact(M.ART_TASK, tid, parent if ledger.artifact_exists(parent) else "", now,
                       commit=commit)
        self.record_event(pipeline, "TASK_CREATED", tid, name, now, commit=commit)
        return ev

    def queue_task(self, task, now="", *, commit=False):
        return self._task_transition(task, M.T_QUEUED, {}, "queued", now, commit=commit)

    def start_task(self, task, now="", *, commit=False):
        return self._task_transition(task, M.T_RUNNING, {}, "running", now, commit=commit)

    def record_task_result(self, task, status, results=None, now="", *, commit=False) -> TaskEventRecord:
        """작업 결과 기록(RUNNING→COMPLETED/FAILED). **결과 기록만 — 실행/배포 아님. COMPLETED ≠ VALIDATED.**"""
        to = M.T_COMPLETED if str(status).upper() == "COMPLETED" else M.T_FAILED
        ev = self._task_transition(task, to, results or {}, "result", now, commit=commit)
        etype = "TASK_COMPLETED" if to == M.T_COMPLETED else "TASK_FAILED"
        self.record_event(self._task_meta(task)["pipeline_id"], etype, task, "", now, commit=commit)
        return ev

    def archive_task(self, task, now="", *, commit=False):
        return self._task_transition(task, M.T_ARCHIVED, {}, "archived", now, commit=commit)

    # ══════════════ 의존(DAG) ══════════════
    def _dep_edges(self) -> list:
        return [(d.get("child_task"), d.get("parent_task")) for d in ledger.read_dependencies()]

    def add_dependency(self, parent_task, child_task, relation="requires", now="",
                       *, commit=False) -> DependencyRecord:
        """작업 의존 추가(불변). child depends_on parent. dangling·순환 거부."""
        if self.task_state(parent_task) is None:
            raise DanglingDependencyError(f"무효 부모 작업 {parent_task}")
        if self.task_state(child_task) is None:
            raise DanglingDependencyError(f"무효 자식 작업 {child_task}")
        if parent_task == child_task:
            raise CircularDependencyError(f"자기 의존 불가 {parent_task}")
        pipe = self._task_meta(child_task)["pipeline_id"]
        did = M.dependency_id(parent_task, child_task)
        existing = ledger.dependency_exists(did)
        if not existing:
            edges = self._dep_edges() + [(child_task, parent_task)]
            if M.detect_cycle(edges):
                raise CircularDependencyError(f"순환 의존 — 거부 {parent_task}->{child_task}")
        rec = DependencyRecord(dependency_id=did, parent_task=parent_task, child_task=child_task,
                               pipeline_id=pipe, relation=relation, created_at=now,
                               input_hash=input_digest(parent_task, child_task),
                               previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.dependency_exists, ledger.dependencies_head, ledger.append_dependency,
                         did, rec, commit=commit and not existing)
        self.record_event(pipe, "DEPENDENCY_ADDED", child_task, parent_task, now, commit=commit)
        return DependencyRecord(**rec)

    def resolve_dependencies(self, pipeline) -> dict:
        """파이프라인 작업 의존 해석 → 위상 순서·순환·누락. **해석·기록만 — 실행 아님.**"""
        tasks = ledger.pipeline_tasks(pipeline)
        tset = set(tasks)
        edges = [(d.get("child_task"), d.get("parent_task")) for d in ledger.read_dependencies()
                 if d.get("child_task") in tset or d.get("parent_task") in tset]
        missing = sorted({p for _c, p in edges if p not in tset}
                         | {c for c, _p in edges if c not in tset})
        cycle = M.detect_cycle([(c, p) for c, p in edges if c in tset and p in tset])
        order = M.topological_order(tasks, [(c, p) for c, p in edges if c in tset and p in tset])
        return {"pipeline_id": pipeline, "order": order, "cycle": cycle,
                "missing_dependencies": missing,
                "resolved": not cycle and not missing and order != [] or not tasks}

    # ══════════════ start_research_run ══════════════
    def start_research_run(self, pipeline, note="", now="", *, commit=False) -> RunRecord:
        """연구 실행 기록 + 파이프라인 READY→EXECUTING + 워크플로 RUNNING. **진행 추적만 — 외부 실행 아님.**"""
        st = self.pipeline_state(pipeline)
        if st is None:
            raise UnknownEntityError(f"미등록 파이프라인 {pipeline}")
        if st == M.P_READY:
            self._pipe_transition(pipeline, M.P_EXECUTING, "executing", now, commit=commit)
        wf = self._pipe_meta(pipeline)["workflow_id"]
        if self.workflow_state(wf) == M.W_ACTIVE:
            self._wf_transition(wf, M.W_RUNNING, "workflow running", now, commit=commit)
        seq = len(ledger.pipeline_runs(pipeline))
        rid = M.run_id(pipeline, seq)
        rec = RunRecord(run_id=rid, pipeline_id=pipeline, workflow_id=wf, status="STARTED",
                        note=note, started_at=now, input_hash=input_digest(pipeline, seq),
                        previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.run_exists, ledger.runs_head, ledger.append_run, rid, rec,
                         commit=commit)
        parent = M.artifact_id(M.ART_PIPELINE, pipeline)
        self._artifact(M.ART_RUN, rid, parent if ledger.artifact_exists(parent) else "", now,
                       commit=commit)
        self.record_event(pipeline, "RUN_STARTED", rid, "", now, commit=commit)
        return RunRecord(**rec)

    # ══════════════ generate_report ══════════════
    def generate_report(self, pipeline, scope="PIPELINE", now="", *, commit=False) -> AutomationReportRecord:
        """자동화 리포트(작업 상태 분포·의존·런). **is_binding=False, COMPLETED ≠ VALIDATED.**"""
        st = self.pipeline_state(pipeline)
        if st is None:
            raise UnknownEntityError(f"미등록 파이프라인 {pipeline}")
        tasks = ledger.pipeline_tasks(pipeline)
        dist: dict = {}
        for t in tasks:
            s = self.task_state(t)
            dist[s] = dist.get(s, 0) + 1
        dep_count = len([d for d in ledger.read_dependencies() if d.get("pipeline_id") == pipeline])
        wf = self._pipe_meta(pipeline)["workflow_id"]
        rid = M.report_id(pipeline, scope, now)
        rec = AutomationReportRecord(
            report_id=rid, pipeline_id=pipeline, workflow_id=wf, scope=scope, pipeline_state=st,
            task_count=len(tasks), task_status_distribution=dict(sorted(dist.items())),
            dependency_count=dep_count, run_count=len(ledger.pipeline_runs(pipeline)),
            is_binding=False, disclaimer=_DISCLAIMER, created_at=now,
            input_hash=input_digest(pipeline, scope, now), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.report_exists, ledger.reports_head, ledger.append_report, rid, rec,
                         commit=commit)
        parent = M.artifact_id(M.ART_PIPELINE, pipeline)
        self._artifact(M.ART_REPORT, rid, parent if ledger.artifact_exists(parent) else "", now,
                       commit=commit)
        return AutomationReportRecord(**rec)

    # ══════════════ verify / 조회 / summary ══════════════
    def verify_integrity(self) -> dict:
        from jarvis.research_automation.verify import verify_chain
        return verify_chain()

    def list_workflows(self) -> list:
        return ledger.workflow_ids()

    def list_pipelines(self, wf) -> list:
        return ledger.workflow_pipelines(wf)

    def list_tasks(self, pipe) -> list:
        return ledger.pipeline_tasks(pipe)

    def summary(self, now="") -> AutomationSummary:
        return AutomationSummary(
            timestamp=now, workflow_event_count=len(ledger.read_workflow_events()),
            pipeline_event_count=len(ledger.read_pipeline_events()),
            task_event_count=len(ledger.read_task_events()),
            dependency_count=len(ledger.read_dependencies()), run_count=len(ledger.read_runs()),
            event_count=len(ledger.read_events()), report_count=len(ledger.read_reports()),
            artifact_count=len(ledger.read_artifacts()))
