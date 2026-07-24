"""Autonomous Research Manager Engine (P12.9) — 연구 워크플로 조정. **계획·추적·모니터링 전용.**

실행 관리자가 아니다. **거래 시작·주문 실행·모델 배포를 하지 않는다.** execution/broker/portfolio/risk/permission/
deployment/live import·호출 없음. MANAGE ≠ EXECUTION · PLAN ≠ DEPLOYMENT · TRACK ≠ TRADING. 결정적·불변·
append-only·이벤트 소싱.
"""
from __future__ import annotations

from jarvis.research_manager import ledger
from jarvis.research_manager.models import (
    ART_PLAN,
    ART_TASK,
    GENESIS,
    P_ARCHIVED,
    P_COMPLETED,
    P_CREATED,
    P_PLANNED,
    P_REVIEWED,
    P_RUNNING,
    ArtifactRecord,
    CircularDependencyError,
    DanglingDependencyError,
    DependencyRecord,
    IllegalPlanTransition,
    ImmutableDependencyError,
    ImmutablePlanError,
    ImmutableTaskError,
    ManagerSummary,
    PlanEventRecord,
    ProgressRecord,
    StatusReportRecord,
    TaskRecord,
    UnknownPlanError,
    UnknownTaskError,
    artifact_id as _artifact_id,
    can_transition,
    content_hash,
    dependency_id as _dependency_id,
    detect_cycle,
    input_digest,
    plan_event_id as _plan_event_id,
    plan_id as _plan_id,
    progress_id as _progress_id,
    report_id as _report_id,
    task_id as _task_id,
    topological_order,
)

_DISCLAIMER = ("Autonomous Research Manager 데이터 — MANAGE ≠ EXECUTION · PLAN ≠ DEPLOYMENT · TRACK ≠ TRADING. "
               "연구 워크플로 계획·추적·모니터링 전용 — 거래 시작·주문 실행·모델 배포·자본 배분 없음.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class AutonomousResearchManagerEngine:
    """자율 연구 관리자 엔진. 불변·append-only·이벤트 소싱·결정적. 실행/배포/거래 권한 없음."""

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

    # ══════════════ 계획 생애주기(event-sourced) ══════════════
    def _plan_event(self, plan: str, name: str, objective: str, frm: str, to: str, note: str,
                 now: str, *, commit: bool) -> PlanEventRecord:
        seq = len(ledger.plan_events(plan))
        eid = _plan_event_id(plan, to, seq)
        rec = PlanEventRecord(plan_event_id=eid, plan_id=plan, name=name, objective=objective,
                              from_state=frm, to_state=to, note=note, occurred_at=now,
                              input_hash=input_digest(plan, to, seq),
                              previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.plan_event_exists(eid):
            head = ledger.plans_head()
            ledger.append_plan_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return PlanEventRecord(**rec)

    def _meta(self, plan: str) -> dict:
        evs = ledger.plan_events(plan)
        if not evs:
            raise UnknownPlanError(f"미등록 계획 {plan}")
        g = evs[0]
        return {"plan_id": plan, "name": g.get("name"), "objective": g.get("objective"),
                "state": evs[-1].get("to_state")}

    def current_state(self, plan: str) -> str | None:
        evs = ledger.plan_events(plan)
        return evs[-1].get("to_state") if evs else None

    def _require_plan(self, plan: str) -> str:
        st = self.current_state(plan)
        if st is None:
            raise UnknownPlanError(f"미등록 계획 {plan}")
        return st

    def _transition(self, plan: str, to: str, note: str, now: str,
                  *, commit: bool) -> PlanEventRecord:
        frm = self._require_plan(plan)
        if not can_transition(frm, to):
            raise IllegalPlanTransition(f"{plan} {frm}→{to} 불가")
        m = self._meta(plan)
        return self._plan_event(plan, m["name"], m["objective"], frm, to, note, now, commit=commit)

    # ══════════════ create_research_plan ══════════════
    def create_research_plan(self, name: str, objective: str = "", now: str = "",
                          *, commit: bool = False) -> PlanEventRecord:
        """연구 계획 생성(genesis CREATED). **계획 시작만.**"""
        pid = _plan_id(name)
        evs = ledger.plan_events(pid)
        if evs:
            g = evs[0]
            if g.get("objective") != objective:
                raise ImmutablePlanError(f"{pid} 계획 불변 — 변경 불가")
            return PlanEventRecord(**{k: v for k, v in g.items()
                                      if k in PlanEventRecord.__dataclass_fields__})
        ev = self._plan_event(pid, name, objective, GENESIS, P_CREATED, "created", now, commit=commit)
        self._artifact(ART_PLAN, pid, "", now, commit=commit)
        return ev

    # ══════════════ create_task (Research Task Registry, →PLANNED) ══════════════
    def create_task(self, plan: str, name: str, description: str = "", owner: str = "", now: str = "",
                 *, commit: bool = False) -> TaskRecord:
        """연구 작업 생성(불변). 첫 작업에서 CREATED→PLANNED. **계획 정의만.**"""
        st = self._require_plan(plan)
        tid = _task_id(plan, name)
        existing = ledger.get_task(tid)
        if existing is not None:
            if existing.get("description") != description:
                raise ImmutableTaskError(f"{tid} 작업 불변 — 변경 불가")
            return TaskRecord(**{k: v for k, v in existing.items()
                                 if k in TaskRecord.__dataclass_fields__})
        rec = TaskRecord(task_id=tid, plan_id=plan, name=name, description=description, owner=owner,
                         created_at=now, input_hash=input_digest(plan, name),
                         previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.task_exists(tid):
            head = ledger.tasks_head()
            ledger.append_task(_seal(rec, head["record_hash"] if head else GENESIS))
        if st == P_CREATED:
            self._transition(plan, P_PLANNED, "planned", now, commit=commit)
        parent = _artifact_id(ART_PLAN, plan)
        self._artifact(ART_TASK, tid, parent if ledger.artifact_exists(parent) else "", now,
                       commit=commit)
        return TaskRecord(**rec)

    def _require_task(self, tid: str) -> dict:
        rec = ledger.get_task(tid)
        if rec is None:
            raise UnknownTaskError(f"미등록 작업 {tid}")
        return rec

    # ══════════════ resolve_dependency (Dependencies) ══════════════
    def _dep_edges(self) -> list:
        return [(r.get("task_id"), r.get("depends_on")) for r in ledger.read_dependencies()]

    def resolve_dependency(self, task: str, depends_on: str, now: str = "",
                        *, commit: bool = False) -> DependencyRecord:
        """작업 의존 등록(불변). dangling·순환 거부. **매핑·기록만.**"""
        self._require_task(task)
        if not ledger.task_exists(depends_on):
            raise DanglingDependencyError(f"무효 의존 작업 {depends_on}")
        if task == depends_on:
            raise CircularDependencyError(f"자기 의존 불가 {task}")
        did = _dependency_id(task, depends_on)
        existing = ledger.dependency_exists(did)
        if not existing:
            edges = self._dep_edges() + [(task, depends_on)]
            if detect_cycle(edges):
                raise CircularDependencyError(f"순환 작업 의존 — 거부 {task}->{depends_on}")
        rec = DependencyRecord(dependency_id=did, task_id=task, depends_on=depends_on, created_at=now,
                               input_hash=input_digest(task, depends_on),
                               previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not existing:
            head = ledger.dependencies_head()
            ledger.append_dependency(_seal(rec, head["record_hash"] if head else GENESIS))
        return DependencyRecord(**rec)

    def task_order(self, plan: str) -> list:
        """계획 작업의 의존 위상 정렬(결정적)."""
        tasks = [t.get("task_id") for t in ledger.plan_tasks(plan)]
        edges = [(d.get("task_id"), d.get("depends_on")) for d in ledger.read_dependencies()
                 if d.get("task_id") in tasks and d.get("depends_on") in tasks]
        return topological_order(tasks, edges)

    # ══════════════ track_progress (Progress Tracking, →RUNNING) ══════════════
    def track_progress(self, task: str, percent: int = 0, status: str = "IN_PROGRESS",
                    note: str = "", now: str = "", *, commit: bool = False) -> ProgressRecord:
        """작업 진행 추적(불변) + 계획 PLANNED→RUNNING. **추적 기록만 — 실행 아님.**"""
        t = self._require_task(task)
        plan = t.get("plan_id")
        st = self._require_plan(plan)
        if st == P_PLANNED:
            self._transition(plan, P_RUNNING, "running", now, commit=commit)
        seq = len(ledger.task_progress(task))
        pid = _progress_id(task, seq)
        rec = ProgressRecord(progress_id=pid, task_id=task, plan_id=plan, percent=int(percent),
                             status=status, note=note, recorded_at=now,
                             input_hash=input_digest(task, seq), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.progress_exists(pid):
            head = ledger.progress_head()
            ledger.append_progress(_seal(rec, head["record_hash"] if head else GENESIS))
        return ProgressRecord(**rec)

    def complete_plan(self, plan: str, now: str = "", *, commit: bool = False) -> PlanEventRecord:
        """계획 완료(RUNNING→COMPLETED). **상태 기록만.**"""
        return self._transition(plan, P_COMPLETED, "completed", now, commit=commit)

    def review_plan(self, plan: str, now: str = "", *, commit: bool = False) -> PlanEventRecord:
        """계획 리뷰(COMPLETED→REVIEWED). **상태 기록만.**"""
        return self._transition(plan, P_REVIEWED, "reviewed", now, commit=commit)

    # ══════════════ archive_plan ══════════════
    def archive_plan(self, plan: str, now: str = "", *, commit: bool = False) -> PlanEventRecord:
        """계획 보관(REVIEWED→ARCHIVED). **상태 기록만.**"""
        return self._transition(plan, P_ARCHIVED, "archived", now, commit=commit)

    # ══════════════ generate_status_report ══════════════
    def generate_status_report(self, plan: str, scope: str = "PLAN", now: str = "",
                            *, commit: bool = False) -> StatusReportRecord:
        """상태 리포트(작업·완료·의존·진행·상태 분포). **is_binding=False, 관찰·모니터링만.**"""
        self._require_plan(plan)
        tasks = ledger.plan_tasks(plan)
        prog = ledger.plan_progress(plan)
        status_dist: dict = {}
        done = 0
        for p in prog:
            status_dist[p.get("status")] = status_dist.get(p.get("status"), 0) + 1
        # 작업별 최신 status 기준 done 집계
        latest: dict = {}
        for p in prog:
            latest[p.get("task_id")] = p.get("status")
        done = sum(1 for s in latest.values() if s == "DONE")
        dep_count = len([d for d in ledger.read_dependencies()
                         if d.get("task_id") in {t.get("task_id") for t in tasks}])
        rid = _report_id(plan, scope, now)
        rec = StatusReportRecord(
            report_id=rid, plan_id=plan, scope=scope, task_count=len(tasks), done_count=done,
            dependency_count=dep_count, progress_count=len(prog), plan_state=self.current_state(plan),
            status_distribution=dict(sorted(status_dist.items())), is_binding=False,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(plan, scope, now),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        return StatusReportRecord(**rec)

    # ══════════════ verify_integrity ══════════════
    def verify_integrity(self) -> dict:
        from jarvis.research_manager.verify import verify_chain
        return verify_chain()

    # ══════════════ 조회 편의 ══════════════
    def list_plans(self) -> list:
        return ledger.plan_ids()

    def plans_in_state(self, state: str) -> list:
        return sorted(p for p in ledger.plan_ids() if self.current_state(p) == state)

    def plan_meta(self, plan: str) -> dict:
        return self._meta(plan)

    def list_tasks(self, plan: str) -> list:
        return sorted(t.get("task_id") for t in ledger.plan_tasks(plan))

    # ══════════════ Summary ══════════════
    def summary(self, now: str = "") -> ManagerSummary:
        return ManagerSummary(
            timestamp=now, plan_event_count=len(ledger.read_plan_events()),
            task_count=len(ledger.read_tasks()),
            dependency_count=len(ledger.read_dependencies()),
            progress_count=len(ledger.read_progress()), report_count=len(ledger.read_reports()),
            artifact_count=len(ledger.read_artifacts()))
