"""Research Orchestration Engine (P10.17) — 연구 과정 가시성·조정. **기록·조직 전용, 실행 없음.**

P9.8~P10.16 연구 생태계를 READ ONLY 로 참조(파일 기반, import 없음)해 워크플로 레지스트리·파이프라인 정의·
태스크·의존 그래프·실행 이력·이벤트 이력·병목 레지스트리·오케스트레이션 리포트·연구 계보를 관리한다.
**연구를 실행하지 않는다.** execution/broker/order/portfolio execution/capital allocation/live trading/
permission/risk controller import·호출 없음. strategy·signal 실행·portfolio 수정·order 생성·capital 배분·
model 배포·자동 연구 트리거·자동 최적화·config/permission 변경 없음. WORKFLOW STATE ≠ EXECUTION STATE ·
TASK READY ≠ RUNNING PROCESS · WORKFLOW COMPLETED ≠ DEPLOYMENT · ORCHESTRATION ≠ AUTOMATION. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.research_orchestration import ledger
from jarvis.research_orchestration.models import (
    ACKNOWLEDGED,
    ARCHIVED,
    ART_BOTTLENECK,
    ART_DEPENDENCY,
    ART_EVENT,
    ART_PIPELINE,
    ART_REPORT,
    ART_RUN,
    ART_TASK,
    ART_WORKFLOW,
    BOTTLENECK_CATEGORIES,
    COMPLETED,
    CREATED,
    EV_STATE_CHANGED,
    GENESIS,
    OPEN,
    RESOLVED,
    BottleneckEvent,
    DependencyEdge,
    IllegalTransition,
    ImmutablePipelineError,
    ImmutableWorkflowError,
    InvalidBottleneckCategory,
    InvalidDependencyGraph,
    OrchestrationArtifact,
    OrchestrationEvent,
    OrchestrationReport,
    OrchestrationSummary,
    PipelineVersion,
    TaskEvent,
    UnknownBottleneck,
    UnknownTask,
    UnknownWorkflow,
    WorkflowEvent,
    WorkflowRun,
    artifact_id as _artifact_id,
    bottleneck_event_id,
    bottleneck_id as _bottleneck_id,
    can_transition_bottleneck,
    can_transition_task,
    can_transition_workflow,
    content_hash,
    dependency_id as _dependency_id,
    detect_cycle,
    event_id as _event_id,
    input_digest,
    metadata_hash as _metadata_hash,
    orchestration_health,
    orchestration_score,
    pipeline_id as _pipeline_id,
    report_id as _report_id,
    run_id as _run_id,
    task_event_id,
    task_id as _task_id,
    workflow_event_id,
    workflow_id as _workflow_id,
)

_DISCLAIMER = ("연구 오케스트레이션 데이터 — WORKFLOW STATE ≠ EXECUTION STATE · TASK READY ≠ RUNNING "
               "PROCESS · WORKFLOW COMPLETED ≠ DEPLOYMENT · ORCHESTRATION ≠ AUTOMATION. 실행/거래/배포/"
               "배분/자동트리거 아님.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchOrchestrationEngine:
    """연구 오케스트레이션 엔진. 불변·append-only·결정적. 실행/거래/배포/트리거/배분 권한 없음."""

    # ── 아티팩트 계보(내부) ──
    def _record_artifact(self, artifact_type: str, ref_id: str, parent_artifact: str,
                         now: str, *, commit: bool) -> dict:
        aid = _artifact_id(artifact_type, ref_id)
        rec = OrchestrationArtifact(
            artifact_id=aid, artifact_type=artifact_type, ref_id=ref_id,
            parent_artifact=parent_artifact, created_at=now,
            input_hash=input_digest(artifact_type, ref_id), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    # ── Workflow Registry (이벤트 소싱, 불변) ──
    def workflow_state(self, workflow_id: str) -> str:
        evs = ledger.workflow_events_for(workflow_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _workflow_meta(self, workflow_id: str) -> dict | None:
        evs = ledger.workflow_events_for(workflow_id)
        return evs[0] if evs else None

    def _emit_workflow_event(self, meta: dict, frm: str, to: str, now: str,
                             *, commit: bool) -> dict:
        if not can_transition_workflow(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(workflow)")
        wid = meta["workflow_id"]
        eid = workflow_event_id(wid, frm, to)
        rec = WorkflowEvent(
            event_id=eid, workflow_id=wid, name=meta["name"], version=meta["version"],
            objective=meta["objective"], metadata_hash=meta["metadata_hash"], from_state=frm,
            to_state=to, status=to, created_at=now, input_hash=input_digest(wid, frm, to),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.workflow_event_exists(eid):
            head = ledger.workflows_head()
            ledger.append_workflow_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def create_workflow(self, name: str, version: str = "1.0", objective: str = "",
                        metadata: dict | None = None, now: str = "",
                        *, commit: bool = False) -> WorkflowEvent:
        """연구 워크플로 등록(CREATED). 동일 name 재등록 시 metadata 상이 → 불변 위반."""
        wid = _workflow_id(name)
        mh = _metadata_hash({"version": version, "objective": objective,
                             "metadata": dict(metadata or {})})
        existing = ledger.workflow_events_for(wid)
        if existing:
            if existing[0].get("metadata_hash") != mh:
                raise ImmutableWorkflowError(f"{wid} 워크플로 불변 — 변경 불가")
            return WorkflowEvent(**existing[-1])
        meta = {"workflow_id": wid, "name": name, "version": version, "objective": objective,
                "metadata_hash": mh}
        rec = self._emit_workflow_event(meta, "", CREATED, now, commit=commit)
        self._record_artifact(ART_WORKFLOW, wid, "", now, commit=commit)
        return WorkflowEvent(**rec)

    def update_workflow_state(self, workflow_id: str, to: str, now: str = "", *,
                             commit: bool = False) -> dict:
        meta = self._workflow_meta(workflow_id)
        if meta is None:
            raise UnknownWorkflow(f"미존재 워크플로 {workflow_id}")
        rec = self._emit_workflow_event(meta, self.workflow_state(workflow_id), to, now,
                                        commit=commit)
        self.record_event(workflow_id, EV_STATE_CHANGED, f"{workflow_id}:{to}", now, commit=commit)
        return rec

    # ── Pipeline Definition Registry (불변 버전) ──
    def create_pipeline(self, workflow_id: str, stages: list | None = None, version: str = "1.0",
                       metadata: dict | None = None, now: str = "",
                       *, commit: bool = False) -> PipelineVersion:
        """워크플로 파이프라인 정의를 불변 버전으로 등록. 동일 버전·상이 stages → 불변 위반."""
        if not ledger.workflow_exists(workflow_id):
            raise UnknownWorkflow(f"미존재 워크플로 {workflow_id}")
        pid = _pipeline_id(workflow_id, version)
        mh = _metadata_hash({"stages": list(stages or []), "metadata": dict(metadata or {})})
        existing = ledger.get_pipeline(pid)
        if existing is not None:
            if existing.get("metadata_hash") != mh:
                raise ImmutablePipelineError(f"{pid} 파이프라인 버전 불변 — 변경 불가")
            return PipelineVersion(**{k: v for k, v in existing.items()
                                      if k in PipelineVersion.__dataclass_fields__})
        rec = PipelineVersion(
            pipeline_id=pid, workflow_id=workflow_id, stages=list(stages or []), version=version,
            metadata_hash=mh, created_at=now, input_hash=input_digest(workflow_id, version),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.pipeline_exists(pid):
            head = ledger.pipelines_head()
            ledger.append_pipeline(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = _artifact_id(ART_WORKFLOW, workflow_id) if ledger.artifact_exists(
            _artifact_id(ART_WORKFLOW, workflow_id)) else ""
        self._record_artifact(ART_PIPELINE, pid, parent, now, commit=commit)
        return PipelineVersion(**rec)

    # ── Task Registry (이벤트 소싱) ──
    def task_state(self, task_id: str) -> str:
        evs = ledger.task_events_for(task_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _task_meta(self, task_id: str) -> dict | None:
        evs = ledger.task_events_for(task_id)
        return evs[0] if evs else None

    def _emit_task_event(self, meta: dict, frm: str, to: str, now: str, *, commit: bool) -> dict:
        if not can_transition_task(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(task)")
        tid = meta["task_id"]
        eid = task_event_id(tid, frm, to)
        rec = TaskEvent(
            event_id=eid, task_id=tid, workflow_id=meta["workflow_id"], name=meta["name"],
            task_type=meta["task_type"], dependencies=meta["dependencies"], from_state=frm,
            to_state=to, status=to, created_at=now, input_hash=input_digest(tid, frm, to),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.task_event_exists(eid):
            head = ledger.tasks_head()
            ledger.append_task_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def register_task(self, workflow_id: str, name: str, task_type: str = "ANALYSIS",
                     dependencies: list | None = None, now: str = "",
                     *, commit: bool = False) -> TaskEvent:
        """워크플로 태스크 등록(CREATED). **TASK READY ≠ RUNNING PROCESS — 실행 아님.**"""
        if not ledger.workflow_exists(workflow_id):
            raise UnknownWorkflow(f"미존재 워크플로 {workflow_id}")
        tid = _task_id(workflow_id, name)
        existing = ledger.task_events_for(tid)
        if existing:
            return TaskEvent(**existing[-1])
        meta = {"task_id": tid, "workflow_id": workflow_id, "name": name, "task_type": task_type,
                "dependencies": list(dependencies or [])}
        rec = self._emit_task_event(meta, "", CREATED, now, commit=commit)
        parent = _artifact_id(ART_WORKFLOW, workflow_id) if ledger.artifact_exists(
            _artifact_id(ART_WORKFLOW, workflow_id)) else ""
        self._record_artifact(ART_TASK, tid, parent, now, commit=commit)
        return TaskEvent(**rec)

    def update_task_state(self, task_id: str, to: str, now: str = "", *,
                         commit: bool = False) -> dict:
        meta = self._task_meta(task_id)
        if meta is None:
            raise UnknownTask(f"미존재 태스크 {task_id}")
        rec = self._emit_task_event(meta, self.task_state(task_id), to, now, commit=commit)
        self.record_event(meta["workflow_id"], EV_STATE_CHANGED, f"{task_id}:{to}", now,
                          commit=commit)
        return rec

    # ── Task Dependency Graph ──
    def add_dependency(self, from_task: str, to_task: str, relation: str = "REQUIRES", now: str = "",
                      *, commit: bool = False) -> DependencyEdge:
        """태스크 의존(from_task requires to_task) 기록. 미등록 노드·자기참조·순환 차단."""
        if from_task == to_task:
            raise InvalidDependencyGraph(f"자기참조 의존 차단 {from_task}")
        if not ledger.task_exists(from_task):
            raise InvalidDependencyGraph(f"미등록 태스크 {from_task}")
        if not ledger.task_exists(to_task):
            raise InvalidDependencyGraph(f"미등록 태스크 {to_task}")
        did = _dependency_id(from_task, to_task)
        if not ledger.dependency_exists(did):
            edges = [(d.get("from_task"), d.get("to_task")) for d in ledger.read_dependencies()]
            cyc = detect_cycle(edges + [(from_task, to_task)])
            if cyc:
                raise InvalidDependencyGraph("의존 순환 차단: " + "->".join(cyc))
        rec = DependencyEdge(
            dependency_id=did, from_task=from_task, to_task=to_task, relation=relation,
            created_at=now, input_hash=input_digest(from_task, to_task),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.dependency_exists(did):
            head = ledger.dependencies_head()
            ledger.append_dependency(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = _artifact_id(ART_TASK, from_task) if ledger.artifact_exists(
            _artifact_id(ART_TASK, from_task)) else ""
        self._record_artifact(ART_DEPENDENCY, did, parent, now, commit=commit)
        return DependencyEdge(**rec)

    def dependency_cycle(self) -> list:
        edges = [(d.get("from_task"), d.get("to_task")) for d in ledger.read_dependencies()]
        return detect_cycle(edges)

    def task_dependencies(self, task_id: str) -> list:
        return [d.get("to_task") for d in ledger.read_dependencies()
                if d.get("from_task") == task_id]

    # ── Workflow Run History ──
    def record_run(self, workflow_id: str, trigger: str = "MANUAL", status: str = "RECORDED",
                  note: str = "", now: str = "", *, commit: bool = False) -> WorkflowRun:
        """워크플로 실행 이력을 기록(사후 기록만 — 실제 실행/트리거 아님)."""
        if not ledger.workflow_exists(workflow_id):
            raise UnknownWorkflow(f"미존재 워크플로 {workflow_id}")
        seq = len(ledger.runs_for(workflow_id)) + 1
        rid = _run_id(workflow_id, seq)
        rec = WorkflowRun(
            run_id=rid, workflow_id=workflow_id, sequence=seq, trigger=trigger, status=status,
            note=note, created_at=now, input_hash=input_digest(workflow_id, seq),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.run_exists(rid):
            head = ledger.runs_head()
            ledger.append_run(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = _artifact_id(ART_WORKFLOW, workflow_id) if ledger.artifact_exists(
            _artifact_id(ART_WORKFLOW, workflow_id)) else ""
        self._record_artifact(ART_RUN, rid, parent, now, commit=commit)
        return WorkflowRun(**rec)

    # ── Workflow Event History ──
    def record_event(self, scope: str, event_type: str, reference: str, now: str = "",
                    *, commit: bool = False) -> OrchestrationEvent:
        eid = _event_id(scope, event_type, reference)
        rec = OrchestrationEvent(
            event_id=eid, scope=scope, event_type=event_type, reference=reference,
            timestamp=now, created_at=now, input_hash=input_digest(scope, event_type, reference),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.event_exists(eid):
            head = ledger.events_head()
            ledger.append_event(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_EVENT, eid, "", now, commit=commit)
        return OrchestrationEvent(**rec)

    # ── Bottleneck Registry (이벤트 소싱, 해소 추적) ──
    def bottleneck_state(self, bottleneck_id: str) -> str:
        evs = ledger.bottleneck_events_for(bottleneck_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _bottleneck_meta(self, bottleneck_id: str) -> dict | None:
        evs = ledger.bottleneck_events_for(bottleneck_id)
        return evs[0] if evs else None

    def _emit_bottleneck_event(self, meta: dict, frm: str, to: str, now: str,
                               *, commit: bool) -> dict:
        if not can_transition_bottleneck(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(bottleneck)")
        bid = meta["bottleneck_id"]
        eid = bottleneck_event_id(bid, frm, to)
        rec = BottleneckEvent(
            event_id=eid, bottleneck_id=bid, source_task=meta["source_task"],
            category=meta["category"], severity=meta["severity"], evidence=meta["evidence"],
            from_state=frm, to_state=to, status=to, created_at=now,
            input_hash=input_digest(bid, frm, to), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.bottleneck_event_exists(eid):
            head = ledger.bottlenecks_head()
            ledger.append_bottleneck_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def detect_bottleneck(self, source_task: str, category: str, severity: str = "MEDIUM",
                         evidence: list | None = None, now: str = "",
                         *, commit: bool = False) -> BottleneckEvent:
        """연구 과정 병목을 플래그(OPEN). category 는 정의된 범주만 허용. **기록만.**"""
        if category not in BOTTLENECK_CATEGORIES:
            raise InvalidBottleneckCategory(f"미등록 병목 범주 {category}")
        bid = _bottleneck_id(source_task, category)
        existing = ledger.bottleneck_events_for(bid)
        if existing:
            return BottleneckEvent(**existing[-1])
        meta = {"bottleneck_id": bid, "source_task": source_task, "category": category,
                "severity": severity, "evidence": list(evidence or [])}
        rec = self._emit_bottleneck_event(meta, "", OPEN, now, commit=commit)
        parent = _artifact_id(ART_TASK, source_task) if ledger.artifact_exists(
            _artifact_id(ART_TASK, source_task)) else ""
        self._record_artifact(ART_BOTTLENECK, bid, parent, now, commit=commit)
        return BottleneckEvent(**rec)

    def transition_bottleneck(self, bottleneck_id: str, to: str, now: str = "", *,
                              commit: bool = False) -> dict:
        meta = self._bottleneck_meta(bottleneck_id)
        if meta is None:
            raise UnknownBottleneck(f"미존재 병목 {bottleneck_id}")
        return self._emit_bottleneck_event(meta, self.bottleneck_state(bottleneck_id), to, now,
                                           commit=commit)

    def resolve_bottleneck(self, bottleneck_id: str, now: str = "", *,
                          commit: bool = False) -> dict:
        """OPEN→ACKNOWLEDGED→RESOLVED. **해소 기록일 뿐 자동 조치 없음.**"""
        meta = self._bottleneck_meta(bottleneck_id)
        if meta is None:
            raise UnknownBottleneck(f"미존재 병목 {bottleneck_id}")
        cur = self.bottleneck_state(bottleneck_id)
        if cur == OPEN:
            self._emit_bottleneck_event(meta, OPEN, ACKNOWLEDGED, now, commit=commit)
        self._emit_bottleneck_event(meta, ACKNOWLEDGED, RESOLVED, now, commit=commit)
        return {"bottleneck_id": bottleneck_id, "state": self.bottleneck_state(bottleneck_id)}

    # ── 계보 검증 ──
    def verify_lineage(self) -> dict:
        """연구 계보(아티팩트 parent 체인): dangling parent·순환 탐지 + 의존 그래프 순환. **읽기 전용.**"""
        issues: list = []
        arts = ledger.read_artifacts()
        ids = {a.get("artifact_id") for a in arts}
        edges: list = []
        for a in arts:
            parent = a.get("parent_artifact")
            if parent:
                if parent not in ids:
                    issues.append(f"dangling:{a.get('artifact_id')}->{parent}")
                edges.append((a.get("artifact_id"), parent))
        cyc = detect_cycle(edges)
        if cyc:
            issues.append("lineage_cycle:" + "->".join(cyc))
        dep_cyc = self.dependency_cycle()
        if dep_cyc:
            issues.append("dependency_cycle:" + "->".join(dep_cyc))
        return {"ok": not issues, "issues": sorted(set(issues)), "n_artifacts": len(arts)}

    def trace_lineage(self, artifact_ref: str) -> list:
        by_id = {a.get("artifact_id"): a for a in ledger.read_artifacts()}
        out: list = []
        seen: set = set()
        cur = by_id.get(artifact_ref)
        while cur:
            parent = cur.get("parent_artifact")
            if not parent or parent in seen:
                break
            seen.add(parent)
            out.append(parent)
            cur = by_id.get(parent)
        return out

    # ── 분석 프레임워크 ──
    def analyze(self, metrics: dict) -> dict:
        """오케스트레이션 지표 → SCORE/HEALTH. **ORCHESTRATION ≠ AUTOMATION — 실행 신호 아님.**"""
        return {"orchestration_score": orchestration_score(metrics),
                "orchestration_health": orchestration_health(metrics)}

    # ── Orchestration Report ──
    def generate_report(self, scope: str = "GLOBAL", metrics: dict | None = None, now: str = "",
                       *, commit: bool = False) -> OrchestrationReport:
        m = dict(metrics or {})
        wfs = ledger.distinct_workflows()
        wstate: dict = {}
        for w in wfs:
            st = self.workflow_state(w.get("workflow_id"))
            wstate[st] = wstate.get(st, 0) + 1
        tasks = ledger.distinct_tasks()
        tstate: dict = {}
        for t in tasks:
            st = self.task_state(t.get("task_id"))
            tstate[st] = tstate.get(st, 0) + 1
        bns = ledger.distinct_bottlenecks()
        bstate: dict = {}
        for b in bns:
            st = self.bottleneck_state(b.get("bottleneck_id"))
            bstate[st] = bstate.get(st, 0) + 1
        rid = _report_id(scope)
        rec = OrchestrationReport(
            report_id=rid, scope=scope, workflow_count=len(wfs),
            workflow_state_distribution=dict(sorted(wstate.items())),
            pipeline_count=len(ledger.read_pipelines()), task_count=len(tasks),
            task_state_distribution=dict(sorted(tstate.items())),
            dependency_count=len(ledger.read_dependencies()), run_count=len(ledger.read_runs()),
            bottleneck_count=len(bns), bottleneck_state_distribution=dict(sorted(bstate.items())),
            metrics=m, orchestration_score=orchestration_score(m),
            orchestration_health=orchestration_health(m), disclaimer=_DISCLAIMER, created_at=now,
            input_hash=input_digest(scope), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_REPORT, rid, "", now, commit=commit)
        return OrchestrationReport(**rec)

    # ── 상위 레이어 READ ONLY 조회 ──
    def list_source_objects(self, layer: str, limit: int = 0) -> list:
        spec = ledger.SOURCE_LEDGERS.get(layer)
        if not spec:
            return []
        filename, id_field = spec
        seen: set = set()
        out: list = []
        for r in ledger.read_source(filename):
            ref = r.get(id_field)
            if ref and ref not in seen:
                seen.add(ref)
                out.append(f"{layer}:{ref}")
            if limit and len(out) >= limit:
                break
        return out

    # ── Summary ──
    def summary(self, now: str = "") -> OrchestrationSummary:
        wfs = ledger.distinct_workflows()
        wstate: dict = {}
        for w in wfs:
            st = self.workflow_state(w.get("workflow_id"))
            wstate[st] = wstate.get(st, 0) + 1
        tasks = ledger.distinct_tasks()
        tstate: dict = {}
        for t in tasks:
            st = self.task_state(t.get("task_id"))
            tstate[st] = tstate.get(st, 0) + 1
        bns = ledger.distinct_bottlenecks()
        bstate: dict = {}
        for b in bns:
            st = self.bottleneck_state(b.get("bottleneck_id"))
            bstate[st] = bstate.get(st, 0) + 1
        return OrchestrationSummary(
            timestamp=now, workflow_count=len(wfs),
            workflow_state_distribution=dict(sorted(wstate.items())),
            pipeline_count=len(ledger.read_pipelines()), task_count=len(tasks),
            task_state_distribution=dict(sorted(tstate.items())),
            dependency_count=len(ledger.read_dependencies()), run_count=len(ledger.read_runs()),
            event_count=len(ledger.read_events()), bottleneck_count=len(bns),
            bottleneck_state_distribution=dict(sorted(bstate.items())),
            report_count=len(ledger.read_reports()))
