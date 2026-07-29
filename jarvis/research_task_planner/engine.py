"""Research Task Planner Engine (P11.2) — AI 에이전트 연구 워크플로 계획. **계획 전용.**

연구 목표로부터 연구 태스크 그래프(DAG)를 계획한다. 계획 생애주기 REQUESTED→PLANNED→RUNNING→COMPLETED→
REVIEWED. **계획만 한다 — 실행 없음. 자동 승인·자동 배포 없음.** 그래프는 REQUESTED 에서만 편집 가능하며 PLANNED
이후 불변(동결). 의존성 추가 시 순환을 거부해 DAG 를 유지한다. execution/broker/order/portfolio execution/
capital allocation/live trading/permission/risk controller import·호출 없음. PLAN ≠ EXECUTE · SCHEDULE ≠ DEPLOY ·
GRAPH ≠ APPROVAL. 불변·append-only·결정적.
"""
from __future__ import annotations

from jarvis.research_task_planner import ledger
from jarvis.research_task_planner.models import (
    EDITABLE_STATES,
    GENESIS,
    PLAN_COMPLETED,
    PLAN_PLANNED,
    PLAN_REQUESTED,
    PLAN_REVIEWED,
    PLAN_RUNNING,
    TASK_KINDS,
    DependencyCycleError,
    DependencyRecord,
    IllegalPlanTransition,
    ImmutableDependencyError,
    ImmutablePlanError,
    ImmutableReportError,
    ImmutableScheduleError,
    ImmutableTaskError,
    InvalidTaskKind,
    PlanEventRecord,
    PlanFrozenError,
    PlanReportRecord,
    PlannerSummary,
    ScheduleRecord,
    SelfDependencyError,
    TaskRecord,
    UnknownPlanError,
    UnknownTaskError,
    ancestors,
    build_waves,
    can_transition_plan,
    content_hash,
    dependency_id as _dependency_id,
    descendants,
    detect_cycle,
    input_digest,
    leaves as _leaves,
    lineage_chain,
    plan_event_id as _plan_event_id,
    plan_id as _plan_id,
    redundant_edges,
    report_id as _report_id,
    roots as _roots,
    schedule_id as _schedule_id,
    task_id as _task_id,
    topological_sort,
)

_DISCLAIMER = ("Research Task Planner 데이터 — PLAN ≠ EXECUTE · SCHEDULE ≠ DEPLOY · GRAPH ≠ APPROVAL. 계획 전용 — "
               "실행/자동 승인/자동 배포 없음. RUNNING 은 관측 상태 라벨이며 본 계층은 태스크를 실행하지 않는다.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchTaskPlannerEngine:
    """자율 연구 태스크 플래너. 불변·append-only·결정적. 실행/자동승인/자동배포 권한 없음."""

    # ══════════════ 계획 생애주기(이벤트 소싱) ══════════════
    def _plan_event(self, plan: str, objective: str, title: str, requested_by: str, frm: str,
                  to: str, note: str, now: str, *, commit: bool) -> PlanEventRecord:
        peid = _plan_event_id(plan, to)
        rec = PlanEventRecord(
            plan_event_id=peid, plan_id=plan, objective=objective, title=title,
            requested_by=requested_by, from_state=frm, to_state=to, note=note, occurred_at=now,
            input_hash=input_digest(plan, to), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.plan_event_exists(peid):
            head = ledger.plans_head()
            ledger.append_plan_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return PlanEventRecord(**rec)

    def request_plan(self, objective: str, requested_by: str, title: str = "", now: str = "",
                   *, commit: bool = False) -> PlanEventRecord:
        """연구 목표로 계획을 요청(REQUESTED). **자동 승인/진행 없음 — REQUESTED 로만 시작.**"""
        plan = _plan_id(objective, requested_by, title)
        evs = ledger.plan_events(plan)
        if evs:
            first = evs[0]
            return PlanEventRecord(**{k: v for k, v in first.items()
                                      if k in PlanEventRecord.__dataclass_fields__})
        return self._plan_event(plan, objective, title, requested_by, GENESIS, PLAN_REQUESTED,
                                "requested", now, commit=commit)

    def current_plan_state(self, plan: str) -> str | None:
        evs = ledger.plan_events(plan)
        return evs[-1].get("to_state") if evs else None

    def plan_meta(self, plan: str) -> dict:
        evs = ledger.plan_events(plan)
        if not evs:
            raise UnknownPlanError(f"미등록 계획 {plan}")
        g = evs[0]
        return {"plan_id": plan, "objective": g.get("objective"), "title": g.get("title"),
                "requested_by": g.get("requested_by"), "state": evs[-1].get("to_state")}

    def _require_plan(self, plan: str) -> str:
        st = self.current_plan_state(plan)
        if st is None:
            raise UnknownPlanError(f"미등록 계획 {plan}")
        return st

    def _transition(self, plan: str, to: str, note: str, now: str, *, commit: bool) -> PlanEventRecord:
        frm = self._require_plan(plan)
        if not can_transition_plan(frm, to):
            raise IllegalPlanTransition(f"{plan} {frm}→{to} 불가")
        meta = self.plan_meta(plan)
        return self._plan_event(plan, meta["objective"], meta["title"], meta["requested_by"],
                                frm, to, note, now, commit=commit)

    # ══════════════ 태스크(그래프 노드) ══════════════
    def add_task(self, plan: str, name: str, kind: str, objective: str = "", parent_task: str = "",
               now: str = "", *, commit: bool = False) -> TaskRecord:
        """계획에 연구 태스크 추가(REQUESTED 상태에서만 — 이후 동결). 태스크 계보(parent) 지원."""
        st = self._require_plan(plan)
        if st not in EDITABLE_STATES:
            raise PlanFrozenError(f"{plan} 동결({st}) — 태스크 추가 불가")
        if kind not in TASK_KINDS:
            raise InvalidTaskKind(f"미등록 태스크 종류 {kind}")
        tid = _task_id(plan, name)
        existing = ledger.get_task(tid)
        if existing is not None:
            if existing.get("kind") != kind or existing.get("parent_task") != parent_task:
                raise ImmutableTaskError(f"{tid} 태스크 불변 — 변경 불가")
            return TaskRecord(**{k: v for k, v in existing.items()
                                 if k in TaskRecord.__dataclass_fields__})
        if parent_task and not ledger.task_exists(parent_task):
            raise UnknownTaskError(f"미등록 부모 태스크 {parent_task}")
        rec = TaskRecord(task_id=tid, plan_id=plan, name=name, kind=kind, objective=objective,
                         parent_task=parent_task, created_at=now,
                         input_hash=input_digest(plan, name), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.task_exists(tid):
            head = ledger.tasks_head()
            ledger.append_task(_seal(rec, head["record_hash"] if head else GENESIS))
        return TaskRecord(**rec)

    # ══════════════ 의존성(그래프 간선) ══════════════
    def add_dependency(self, plan: str, upstream_task: str, downstream_task: str, now: str = "",
                     *, commit: bool = False) -> DependencyRecord:
        """의존성 추가(upstream→downstream). REQUESTED 에서만. 순환 발생 시 거부(DAG 유지)."""
        st = self._require_plan(plan)
        if st not in EDITABLE_STATES:
            raise PlanFrozenError(f"{plan} 동결({st}) — 의존성 추가 불가")
        if upstream_task == downstream_task:
            raise SelfDependencyError(f"자기 의존성 {upstream_task}")
        for t in (upstream_task, downstream_task):
            if not ledger.task_exists(t):
                raise UnknownTaskError(f"미등록 태스크 {t}")
        did = _dependency_id(plan, upstream_task, downstream_task)
        if ledger.dependency_exists(did):
            return DependencyRecord(**{k: v for k, v in ledger.get_dependency(did).items()
                                       if k in DependencyRecord.__dataclass_fields__})
        # 순환 검사(가상 추가 후 detect_cycle)
        edges = self._edges(plan) + [(upstream_task, downstream_task)]
        cyc = detect_cycle(edges)
        if cyc:
            raise DependencyCycleError(f"순환 발생 — 거부: {'->'.join(cyc)}")
        rec = DependencyRecord(dependency_id=did, plan_id=plan, upstream_task=upstream_task,
                               downstream_task=downstream_task, created_at=now,
                               input_hash=input_digest(plan, upstream_task, downstream_task),
                               previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.dependency_exists(did):
            head = ledger.dependencies_head()
            ledger.append_dependency(_seal(rec, head["record_hash"] if head else GENESIS))
        return DependencyRecord(**rec)

    # ══════════════ 그래프 조회·검증 ══════════════
    def _nodes(self, plan: str) -> list:
        return sorted(t.get("task_id") for t in ledger.plan_tasks(plan))

    def _edges(self, plan: str) -> list:
        return [(d.get("upstream_task"), d.get("downstream_task"))
                for d in ledger.plan_dependencies(plan)]

    def build_task_graph(self, plan: str) -> dict:
        """연구 태스크 그래프(노드·간선·roots·leaves·위상순서·DAG 여부). **계획 산출물, 실행 아님.**"""
        self._require_plan(plan)
        nodes = self._nodes(plan)
        edges = self._edges(plan)
        order = topological_sort(nodes, edges)
        return {"plan_id": plan, "nodes": nodes, "edges": [list(e) for e in edges],
                "node_count": len(nodes), "edge_count": len(edges),
                "roots": _roots(nodes, edges), "leaves": _leaves(nodes, edges),
                "is_dag": order is not None, "order": order or []}

    def validate_dag(self, plan: str) -> dict:
        """DAG 검증: 순환 탐지·고아 간선. **탐지·보고만.**"""
        self._require_plan(plan)
        nodes = set(self._nodes(plan))
        edges = self._edges(plan)
        issues: list = []
        for u, d in edges:
            if u not in nodes:
                issues.append(f"unknown_upstream:{u}")
            if d not in nodes:
                issues.append(f"unknown_downstream:{d}")
        cyc = detect_cycle(edges)
        if cyc:
            issues.append("cycle:" + "->".join(cyc))
        return {"ok": not issues, "issues": sorted(set(issues)), "is_dag": not cyc}

    def dependencies_of(self, plan: str, task: str) -> list:
        """태스크의 모든 상류 의존(전이적). **의존성 탐지.**"""
        return ancestors(self._edges(plan), task)

    def dependents_of(self, plan: str, task: str) -> list:
        return descendants(self._edges(plan), task)

    def redundant_dependencies(self, plan: str) -> list:
        """전이적으로 함의되는 잉여 의존성(정보용). **탐지만.**"""
        return [list(e) for e in redundant_edges(self._edges(plan))]

    # ══════════════ 태스크 계보 ══════════════
    def _parent_map(self, plan: str) -> dict:
        return {t.get("task_id"): t.get("parent_task") for t in ledger.plan_tasks(plan)
                if t.get("parent_task")}

    def trace_lineage(self, plan: str, task: str) -> list:
        """태스크 계보(부모 체인). **조회 전용.**"""
        return lineage_chain(self._parent_map(plan), task)

    def validate_lineage(self, plan: str) -> dict:
        """태스크 계보 무결성: dangling 부모·순환 탐지."""
        tasks = ledger.plan_tasks(plan)
        ids = {t.get("task_id") for t in tasks}
        pm = {t.get("task_id"): t.get("parent_task") for t in tasks if t.get("parent_task")}
        issues: list = []
        for tid, parent in sorted(pm.items()):
            if parent not in ids:
                issues.append(f"dangling_parent:{tid}->{parent}")
        cyc = detect_cycle(list(pm.items()))
        if cyc:
            issues.append("lineage_cycle:" + "->".join(cyc))
        return {"ok": not issues, "issues": sorted(set(issues))}

    # ══════════════ finalize_plan (REQUESTED→PLANNED + 스케줄) ══════════════
    def finalize_plan(self, plan: str, now: str = "", *, commit: bool = False) -> dict:
        """DAG·계보 검증 후 계획 확정(REQUESTED→PLANNED)하고 스케줄 구성. **계획 확정 — 실행/승인 아님.**"""
        st = self._require_plan(plan)
        if st != PLAN_REQUESTED:
            raise IllegalPlanTransition(f"{plan} REQUESTED 아님({st}) — 확정 불가")
        dag = self.validate_dag(plan)
        if not dag["is_dag"]:
            raise DependencyCycleError(f"{plan} 비-DAG — 확정 불가")
        lineage = self.validate_lineage(plan)
        ev = self._transition(plan, PLAN_PLANNED, "finalized", now, commit=commit)
        sched = self.build_schedule(plan, now, commit=commit)
        return {"plan_event": ev.to_dict(), "schedule": sched.to_dict(), "dag": dag,
                "lineage": lineage}

    def build_schedule(self, plan: str, now: str = "", *, commit: bool = False) -> ScheduleRecord:
        """위상 순서·병렬 웨이브 스케줄 구성(결정적). **계획 스케줄 — 실행 트리거 아님.**"""
        nodes = self._nodes(plan)
        edges = self._edges(plan)
        order = topological_sort(nodes, edges) or []
        waves = build_waves(nodes, edges) or []
        sid = _schedule_id(plan)
        existing = ledger.get_schedule(sid)
        if existing is not None:
            if list(existing.get("order", [])) != order:
                raise ImmutableScheduleError(f"{sid} 스케줄 불변 — 변경 불가")
            return ScheduleRecord(**{k: v for k, v in existing.items()
                                     if k in ScheduleRecord.__dataclass_fields__})
        rec = ScheduleRecord(schedule_id=sid, plan_id=plan, order=order, waves=waves,
                             task_count=len(nodes), created_at=now, input_hash=input_digest(plan),
                             previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.schedule_exists(sid):
            head = ledger.schedules_head()
            ledger.append_schedule(_seal(rec, head["record_hash"] if head else GENESIS))
        return ScheduleRecord(**rec)

    # ══════════════ 이후 생애주기(관측 상태만) ══════════════
    def mark_running(self, plan: str, now: str = "", *, commit: bool = False) -> PlanEventRecord:
        """PLANNED→RUNNING(관측 상태 라벨). **본 계층은 실행하지 않음.**"""
        return self._transition(plan, PLAN_RUNNING, "running(observed)", now, commit=commit)

    def mark_completed(self, plan: str, now: str = "", *, commit: bool = False) -> PlanEventRecord:
        return self._transition(plan, PLAN_COMPLETED, "completed(observed)", now, commit=commit)

    def review_plan(self, plan: str, now: str = "", *, commit: bool = False) -> PlanEventRecord:
        return self._transition(plan, PLAN_REVIEWED, "reviewed", now, commit=commit)

    # ══════════════ 리포트 ══════════════
    def generate_report(self, plan: str, scope: str = "PLAN", metrics: dict | None = None,
                      now: str = "", *, commit: bool = False) -> PlanReportRecord:
        """계획 리포트(태스크·의존성·DAG·roots/leaves·종류 분포). **관측 리포트 — 실행 지시 아님.**"""
        st = self._require_plan(plan)
        m = dict(metrics or {})
        g = self.build_task_graph(plan)
        tasks = ledger.plan_tasks(plan)
        kind_dist: dict = {}
        for t in tasks:
            kind_dist[t.get("kind")] = kind_dist.get(t.get("kind"), 0) + 1
        rid = _report_id(plan, scope, now)
        rec = PlanReportRecord(
            report_id=rid, plan_id=plan, scope=scope, lifecycle_state=st,
            task_count=g["node_count"], dependency_count=g["edge_count"], is_dag=g["is_dag"],
            root_count=len(g["roots"]), leaf_count=len(g["leaves"]),
            redundant_edge_count=len(self.redundant_dependencies(plan)),
            kind_distribution=dict(sorted(kind_dist.items())), metrics=m, disclaimer=_DISCLAIMER,
            created_at=now, input_hash=input_digest(plan, scope, now),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        return PlanReportRecord(**rec)

    # ══════════════ 조회 편의 ══════════════
    def list_plans(self) -> list:
        return ledger.plan_ids()

    def list_tasks(self, plan: str) -> list:
        return sorted(t.get("name") for t in ledger.plan_tasks(plan))

    # ══════════════ Summary ══════════════
    def summary(self, now: str = "") -> PlannerSummary:
        return PlannerSummary(
            timestamp=now, plan_event_count=len(ledger.read_plan_events()),
            task_count=len(ledger.read_tasks()),
            dependency_count=len(ledger.read_dependencies()),
            schedule_count=len(ledger.read_schedules()), report_count=len(ledger.read_reports()))
