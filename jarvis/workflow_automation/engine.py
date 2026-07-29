"""Workflow Automation Engine (P44) — 연구 워크플로 조율. **자율 실행 없음, 동작 없음.**

워크플로·태스크·의존성·검토 요청을 기록·조율한다. **자율 실행 아님 — 사람 승인 필수.** execution/broker/live_trading/
portfolio_execution import·호출 없음. WORKFLOW AUTOMATION ≠ AUTONOMOUS EXECUTION · Human approval remains required.
결정적·불변·append-only·이벤트 소싱. 엔진은 execute()/trade()/deploy()/allocate()/approve() 를 노출하지 않는다.
advance_state 는 계획 의도를 **기록**할 뿐 아무것도 실행하지 않는다. 상위 계층은 READ ONLY.
"""
from __future__ import annotations

from jarvis.workflow_automation import ledger
from jarvis.workflow_automation import models as M
from jarvis.workflow_automation.models import (
    GENESIS,
    ApprovalRequestRecord,
    ArtifactRecord,
    DependencyCycleError,
    DependencyRecord,
    IllegalTaskTransition,
    IllegalWorkflowTransition,
    TaskEventRecord,
    UnknownEntityError,
    WorkflowEventRecord,
    WorkflowMetadataRecord,
    WorkflowReportRecord,
    WorkflowSummary,
    content_hash,
    input_digest,
)

_DISCLAIMER = ("Workflow Automation Layer 데이터 — WORKFLOW AUTOMATION ≠ AUTONOMOUS EXECUTION. "
               "연구 워크플로 조율·기록 전용, 사람 승인 필수(Human approval remains required) — 자율 실행·거래·배포·"
               "자본 배분 없음. 상태 전이는 계획 의도의 기록일 뿐 실행이 아님.")


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class WorkflowAutomationEngine:
    """워크플로 조율 엔진. 불변·append-only·이벤트 소싱·결정적. 자율 실행/거래/배포/배분 권한 없음."""

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

    # ══════════════ 워크플로 생애주기(event-sourced) ══════════════
    def _workflow_event(self, wf, name, desc, frm, to, note, now, *, commit):
        seq = len(ledger.workflow_events(wf))
        eid = M.workflow_event_id(wf, to, seq)
        rec = WorkflowEventRecord(
            workflow_event_id=eid, workflow_id=wf, name=name, description=desc, from_state=frm,
            to_state=to, note=note, occurred_at=now, input_hash=input_digest(wf, to, seq),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.workflow_event_exists, ledger.workflows_head,
                         ledger.append_workflow_event, eid, rec, commit=commit)
        return WorkflowEventRecord(**rec)

    def workflow_state(self, wf) -> str | None:
        evs = ledger.workflow_events(wf)
        return evs[-1].get("to_state") if evs else None

    def _workflow_meta(self, wf) -> dict:
        evs = ledger.workflow_events(wf)
        if not evs:
            raise UnknownEntityError(f"미등록 워크플로 {wf}")
        g = evs[0]
        return {"name": g.get("name"), "description": g.get("description"),
                "state": evs[-1].get("to_state")}

    def create_workflow(self, name, description="", now="", *, commit=False) -> WorkflowEventRecord:
        """워크플로 등록(genesis CREATED, 이벤트 소싱). **조율·기록만 — 실행 아님.**"""
        wf = M.workflow_id(name)
        evs = ledger.workflow_events(wf)
        if evs:
            return WorkflowEventRecord(**{k: v for k, v in evs[0].items()
                                          if k in WorkflowEventRecord.__dataclass_fields__})
        ev = self._workflow_event(wf, name, description, GENESIS, M.W_CREATED, "created", now,
                                  commit=commit)
        self._artifact(M.ART_WORKFLOW, wf, "", now, commit=commit)
        return ev

    def advance_state(self, wf, to_state, note="", now="", *, commit=False) -> WorkflowEventRecord:
        """워크플로 상태 전이 기록(CREATED→PLANNED→RUNNING→COMPLETED→ARCHIVED). **계획 기록 — 실행 아님.**"""
        m = self._workflow_meta(wf)
        frm = m["state"]
        if to_state not in M.WORKFLOW_STATES:
            raise ValueError(f"미지원 상태 {to_state}")
        if not M.can_workflow_transition(frm, to_state):
            raise IllegalWorkflowTransition(f"워크플로 {wf} {frm}→{to_state} 불가")
        return self._workflow_event(wf, m["name"], m["description"], frm, to_state,
                                    note or to_state.lower(), now, commit=commit)

    def plan_workflow(self, wf, note="planned", now="", *, commit=False):
        return self.advance_state(wf, M.W_PLANNED, note, now, commit=commit)

    def start_workflow(self, wf, note="running", now="", *, commit=False):
        return self.advance_state(wf, M.W_RUNNING, note, now, commit=commit)

    def complete_workflow(self, wf, note="completed", now="", *, commit=False):
        return self.advance_state(wf, M.W_COMPLETED, note, now, commit=commit)

    def archive_workflow(self, wf, note="archived", now="", *, commit=False):
        return self.advance_state(wf, M.W_ARCHIVED, note, now, commit=commit)

    # ══════════════ 태스크(event-sourced) ══════════════
    def _task_event(self, tsk, wf, name, kind, frm, to, note, now, *, commit):
        seq = len(ledger.task_events(tsk))
        eid = M.task_event_id(tsk, to, seq)
        rec = TaskEventRecord(
            task_event_id=eid, task_id=tsk, workflow_id=wf, name=name, kind=kind, from_state=frm,
            to_state=to, note=note, occurred_at=now, input_hash=input_digest(tsk, to, seq),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.task_event_exists, ledger.tasks_head, ledger.append_task_event,
                         eid, rec, commit=commit)
        return TaskEventRecord(**rec)

    def task_state(self, tsk) -> str | None:
        evs = ledger.task_events(tsk)
        return evs[-1].get("to_state") if evs else None

    def _task_meta(self, tsk) -> dict:
        evs = ledger.task_events(tsk)
        if not evs:
            raise UnknownEntityError(f"미등록 태스크 {tsk}")
        g = evs[0]
        return {"workflow_id": g.get("workflow_id"), "name": g.get("name"), "kind": g.get("kind"),
                "state": evs[-1].get("to_state")}

    def add_task(self, wf, name, kind="ANALYSIS", now="", *, commit=False) -> TaskEventRecord:
        """워크플로에 태스크 추가(genesis PENDING). **정의·기록만 — 실행 아님.**"""
        self._workflow_meta(wf)
        if kind not in M.TASK_KINDS:
            raise ValueError(f"미지원 kind {kind}")
        tsk = M.task_id(wf, name)
        evs = ledger.task_events(tsk)
        if evs:
            return TaskEventRecord(**{k: v for k, v in evs[0].items()
                                      if k in TaskEventRecord.__dataclass_fields__})
        ev = self._task_event(tsk, wf, name, kind, GENESIS, M.T_PENDING, "added", now, commit=commit)
        self._artifact(M.ART_TASK, tsk, M.artifact_id(M.ART_WORKFLOW, wf), now, commit=commit)
        return ev

    def advance_task(self, tsk, to_state, note="", now="", *, commit=False) -> TaskEventRecord:
        """태스크 상태 전이 기록(PENDING→READY→RUNNING→COMPLETED, BLOCKED). **기록 — 자동 실행 아님.**"""
        m = self._task_meta(tsk)
        frm = m["state"]
        if to_state not in M.TASK_STATES:
            raise ValueError(f"미지원 상태 {to_state}")
        if not M.can_task_transition(frm, to_state):
            raise IllegalTaskTransition(f"태스크 {tsk} {frm}→{to_state} 불가")
        return self._task_event(tsk, m["workflow_id"], m["name"], m["kind"], frm, to_state,
                                note or to_state.lower(), now, commit=commit)

    # ══════════════ track_dependency (사이클 차단) ══════════════
    def track_dependency(self, wf, from_task, to_task, now="", *, commit=False) -> DependencyRecord:
        """태스크 의존성 기록(from_task 는 to_task 에 의존). 사이클 차단, 결정적. **조율 메타만.**"""
        self._workflow_meta(wf)
        self._task_meta(from_task)
        self._task_meta(to_task)
        if from_task == to_task:
            raise DependencyCycleError(f"자기 의존 금지 {from_task}")
        did = M.dependency_id(wf, from_task, to_task)
        existing = next((d for d in ledger.dependencies_for(wf)
                         if d.get("dependency_id") == did), None)
        if existing:
            return DependencyRecord(**{k: v for k, v in existing.items()
                                       if k in DependencyRecord.__dataclass_fields__})
        edges = [(d.get("from_task"), d.get("to_task")) for d in ledger.dependencies_for(wf)]
        edges.append((from_task, to_task))
        if M.detect_cycle_check(edges):
            raise DependencyCycleError(f"의존성 사이클 {from_task}->{to_task}")
        rec = DependencyRecord(
            dependency_id=did, workflow_id=wf, from_task=from_task, to_task=to_task, created_at=now,
            input_hash=input_digest(wf, from_task, to_task), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.dependency_exists, ledger.dependencies_head, ledger.append_dependency,
                         did, rec, commit=commit)
        return DependencyRecord(**rec)

    def task_execution_order(self, wf) -> list | None:
        """의존성 위상 정렬(결정적, READ ONLY). **권고 순서일 뿐 자동 실행 아님.** 사이클이면 None."""
        self._workflow_meta(wf)
        nodes = ledger.task_ids_for(wf)
        edges = [(d.get("from_task"), d.get("to_task")) for d in ledger.dependencies_for(wf)]
        return M.topological_order(nodes, edges)

    # ══════════════ request_review (사람 검토 요청 — 절대 자동 승인 없음) ══════════════
    def request_review(self, wf, stage, note="", now="", *, commit=False) -> ApprovalRequestRecord:
        """사람 검토 요청 기록(status=PENDING_HUMAN_REVIEW, is_granted=False). **승인 부여 없음 — 사람만 가능.**"""
        self._workflow_meta(wf)
        seq = len([a for a in ledger.approvals_for(wf) if a.get("stage") == stage])
        aid = M.approval_id(wf, stage, seq)
        rec = ApprovalRequestRecord(
            approval_id=aid, workflow_id=wf, stage=stage, status=M.REVIEW_PENDING, is_granted=False,
            requires_human_approval=True, note=note, created_at=now,
            input_hash=input_digest(wf, stage, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.approval_exists, ledger.approvals_head, ledger.append_approval, aid,
                         rec, commit=commit)
        return ApprovalRequestRecord(**rec)

    # ══════════════ record_metadata ══════════════
    def record_metadata(self, wf, key, value, now="", *, commit=False) -> WorkflowMetadataRecord:
        """워크플로 메타데이터 기록(불변)."""
        self._workflow_meta(wf)
        mid = M.metadata_id(wf, key)
        existing = next((m for m in ledger.read_metadata() if m.get("metadata_id") == mid), None)
        if existing:
            return WorkflowMetadataRecord(**{k: v for k, v in existing.items()
                                             if k in WorkflowMetadataRecord.__dataclass_fields__})
        rec = WorkflowMetadataRecord(metadata_id=mid, workflow_id=wf, key=key, value=str(value),
                                     created_at=now, input_hash=input_digest(wf, key),
                                     previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.metadata_exists, ledger.metadata_head, ledger.append_metadata, mid,
                         rec, commit=commit)
        return WorkflowMetadataRecord(**rec)

    # ══════════════ generate_workflow_report ══════════════
    def generate_workflow_report(self, scope="SYSTEM", now="", *, commit=False) -> WorkflowReportRecord:
        """워크플로 조율 리포트(워크플로·태스크·의존성·검토 집계). **is_binding=False, 자율 실행 아님.**"""
        wfs = ledger.workflow_ids()
        states = {w: self.workflow_state(w) for w in wfs}
        st_dist: dict = {}
        for st in states.values():
            st_dist[st] = st_dist.get(st, 0) + 1
        tasks = sorted({r.get("task_id") for r in ledger.read_task_events() if r.get("task_id")})
        ts_dist: dict = {}
        for t in tasks:
            s = self.task_state(t)
            ts_dist[s] = ts_dist.get(s, 0) + 1
        pending = sum(1 for a in ledger.read_approvals() if a.get("status") == M.REVIEW_PENDING)
        rid = M.report_id(scope, now)
        rec = WorkflowReportRecord(
            report_id=rid, scope=scope, workflow_count=len(wfs),
            running_workflow_count=sum(1 for st in states.values() if st == M.W_RUNNING),
            completed_workflow_count=sum(1 for st in states.values() if st == M.W_COMPLETED),
            task_count=len(tasks), dependency_count=len(ledger.read_dependencies()),
            pending_review_count=pending, metadata_count=len(ledger.read_metadata()),
            state_distribution=dict(sorted(st_dist.items())),
            task_status_distribution=dict(sorted(ts_dist.items())), requires_human_approval=True,
            is_binding=False, disclaimer=_DISCLAIMER, created_at=now,
            input_hash=input_digest(scope, now), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.report_exists, ledger.reports_head, ledger.append_report, rid, rec,
                         commit=commit)
        self._artifact(M.ART_REPORT, rid, "", now, commit=commit)
        return WorkflowReportRecord(**rec)

    def verify_integrity(self) -> dict:
        from jarvis.workflow_automation.verify import verify_chain
        return verify_chain()

    def list_workflows(self) -> list:
        return ledger.workflow_ids()

    def workflows_in_state(self, state) -> list:
        return sorted(w for w in ledger.workflow_ids() if self.workflow_state(w) == state)

    def list_tasks(self, wf) -> list:
        return ledger.task_ids_for(wf)

    def summary(self, now="") -> WorkflowSummary:
        return WorkflowSummary(
            timestamp=now, workflow_event_count=len(ledger.read_workflow_events()),
            workflow_count=len(ledger.workflow_ids()),
            task_event_count=len(ledger.read_task_events()),
            task_count=len({r.get("task_id") for r in ledger.read_task_events() if r.get("task_id")}),
            dependency_count=len(ledger.read_dependencies()),
            approval_count=len(ledger.read_approvals()), metadata_count=len(ledger.read_metadata()),
            report_count=len(ledger.read_reports()), artifact_count=len(ledger.read_artifacts()))
