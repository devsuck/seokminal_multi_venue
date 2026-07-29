"""Experiment Orchestration Engine (P31) — 연구 실험 조정 기록. **실험 실행 없음, 동작 없음.**

**실험을 실행하지 않는다 — 조정 기록만. 사람 승인이 항상 필요하다.** execution/broker/live_trading/
portfolio_execution import·호출 없음. ORCHESTRATION ≠ EXECUTION · APPROVED ≠ EXECUTED · REQUEST ≠ RUN.
결정적·불변·append-only·이벤트 소싱. 상위 계층은 READ ONLY.
"""
from __future__ import annotations

from jarvis.experiment_orchestration import ledger
from jarvis.experiment_orchestration import models as M
from jarvis.experiment_orchestration.models import (
    GENESIS,
    ApproverRequired,
    ArtifactRecord,
    DependencyCycleError,
    DependencyRecord,
    HistoryRecord,
    IllegalPlanTransition,
    IllegalRequestTransition,
    OrchestrationReportRecord,
    OrchestrationSummary,
    PlanEventRecord,
    RequestEventRecord,
    ScheduleRecord,
    UnknownEntityError,
    content_hash,
    input_digest,
)

_DISCLAIMER = ("Experiment Orchestration 데이터 — ORCHESTRATION ≠ EXECUTION · APPROVED ≠ EXECUTED · "
               "REQUEST ≠ RUN. 실험 계획·스케줄·의존성·실행 요청·이력 조정 기록 전용 — 실험 실행·거래·배포·자본 배분 없음. "
               "사람 승인 필수. 승인된 요청도 자동 실행되지 않는다(is_executed=False).")


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ExperimentOrchestrationEngine:
    """실험 조정 엔진. 불변·append-only·이벤트 소싱·결정적. 실험 실행/거래/배포/자동승인 권한 없음."""

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

    # ══════════════ 실험 계획 생애주기(event-sourced) ══════════════
    def _plan_event(self, plan, name, objective, frm, to, note, now, *, commit):
        seq = len(ledger.plan_events(plan))
        eid = M.plan_event_id(plan, to, seq)
        rec = PlanEventRecord(
            plan_event_id=eid, plan_id=plan, name=name, objective=objective, from_state=frm,
            to_state=to, note=note, occurred_at=now, input_hash=input_digest(plan, to, seq),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.plan_event_exists, ledger.plans_head, ledger.append_plan_event, eid,
                         rec, commit=commit)
        return PlanEventRecord(**rec)

    def plan_state(self, plan) -> str | None:
        evs = ledger.plan_events(plan)
        return evs[-1].get("to_state") if evs else None

    def _plan_meta(self, plan) -> dict:
        evs = ledger.plan_events(plan)
        if not evs:
            raise UnknownEntityError(f"미등록 계획 {plan}")
        g = evs[0]
        return {"name": g.get("name"), "objective": g.get("objective"),
                "state": evs[-1].get("to_state")}

    def _plan_transition(self, plan, to, note, now, *, commit):
        m = self._plan_meta(plan)
        frm = m["state"]
        if not M.can_plan_transition(frm, to):
            raise IllegalPlanTransition(f"계획 {plan} {frm}→{to} 불가")
        return self._plan_event(plan, m["name"], m["objective"], frm, to, note, now, commit=commit)

    def create_plan(self, name, objective="", now="", *, commit=False) -> PlanEventRecord:
        """실험 계획 생성(genesis DRAFT). **조정 기록 — 실행 아님.**"""
        plan = M.plan_id(name)
        evs = ledger.plan_events(plan)
        if evs:
            return PlanEventRecord(**{k: v for k, v in evs[0].items()
                                      if k in PlanEventRecord.__dataclass_fields__})
        ev = self._plan_event(plan, name, objective, GENESIS, M.P_DRAFT, "draft", now, commit=commit)
        self._artifact(M.ART_PLAN, plan, "", now, commit=commit)
        return ev

    def schedule_plan(self, plan, scheduled_for="", priority="NORMAL", window="", now="",
                      *, commit=False) -> ScheduleRecord:
        """계획 스케줄링(스케줄 기록 + DRAFT→SCHEDULED 전이). **스케줄 기록만 — 실행 아님.**"""
        self._plan_meta(plan)
        seq = len(ledger.schedules_for(plan))
        sid = M.schedule_id(plan, seq)
        rec = ScheduleRecord(schedule_id=sid, plan_id=plan, scheduled_for=scheduled_for,
                             priority=priority, window=window, created_at=now,
                             input_hash=input_digest(plan, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.schedule_exists, ledger.schedules_head, ledger.append_schedule, sid,
                         rec, commit=commit)
        self._artifact(M.ART_SCHEDULE, sid, M.artifact_id(M.ART_PLAN, plan), now, commit=commit)
        if self.plan_state(plan) == M.P_DRAFT:
            self._plan_transition(plan, M.P_SCHEDULED, "scheduled", now, commit=commit)
        return ScheduleRecord(**rec)

    def mark_ready(self, plan, note="ready", now="", *, commit=False):
        return self._plan_transition(plan, M.P_READY, note, now, commit=commit)

    def conclude_plan(self, plan, note="concluded", now="", *, commit=False):
        return self._plan_transition(plan, M.P_CONCLUDED, note, now, commit=commit)

    def archive_plan(self, plan, note="archived", now="", *, commit=False):
        return self._plan_transition(plan, M.P_ARCHIVED, note, now, commit=commit)

    # ══════════════ add_dependency (순환 방지) ══════════════
    def add_dependency(self, plan, depends_on, dependency_type="SEQUENTIAL", now="",
                       *, commit=False) -> DependencyRecord:
        """의존성 추가(불변). 순환 방지. **조정 기록만.**"""
        self._plan_meta(plan)
        self._plan_meta(depends_on)  # 양쪽 존재 검증
        if dependency_type not in M.DEPENDENCY_TYPES:
            raise ValueError(f"미지원 dependency_type {dependency_type}")
        edges = ledger.all_dependency_edges() + [(plan, depends_on)]
        if M.detect_cycle_check(edges):
            raise DependencyCycleError(f"의존성 순환: {plan}->{depends_on}")
        did = M.dependency_id(plan, depends_on)
        rec = DependencyRecord(dependency_id=did, plan_id=plan, depends_on=depends_on,
                               dependency_type=dependency_type, created_at=now,
                               input_hash=input_digest(plan, depends_on),
                               previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.dependency_exists, ledger.dependencies_head, ledger.append_dependency,
                         did, rec, commit=commit)
        return DependencyRecord(**rec)

    def resolve_dependencies(self, plan) -> dict:
        """계획 의존성 상태(READ ONLY). 모든 의존 계획이 CONCLUDED/ARCHIVED 인지 + 위상 순서."""
        deps = [d.get("depends_on") for d in ledger.dependencies_for(plan)]
        states = {d: self.plan_state(d) for d in deps}
        ready = all(st in (M.P_CONCLUDED, M.P_ARCHIVED) for st in states.values())
        order = M.topological_order(ledger.plan_ids(), ledger.all_dependency_edges())
        return {"plan_id": plan, "dependencies": states, "ready": ready, "topological_order": order}

    # ══════════════ 실행 요청 생애주기(event-sourced, 사람 승인, 실행 없음) ══════════════
    def _request_event(self, req, plan, requester, approver, frm, to, note, now, *, commit):
        seq = len(ledger.request_events(req))
        eid = M.request_event_id(req, to, seq)
        rec = RequestEventRecord(
            request_event_id=eid, request_id=req, plan_id=plan, requester=requester,
            approver=approver, is_executed=False, from_state=frm, to_state=to, note=note,
            created_at=now, input_hash=input_digest(req, to, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.request_event_exists, ledger.requests_head,
                         ledger.append_request_event, eid, rec, commit=commit)
        return RequestEventRecord(**rec)

    def request_state(self, req) -> str | None:
        evs = ledger.request_events(req)
        return evs[-1].get("to_state") if evs else None

    def _request_meta(self, req) -> dict:
        evs = ledger.request_events(req)
        if not evs:
            raise UnknownEntityError(f"미등록 요청 {req}")
        g = evs[0]
        return {"plan_id": g.get("plan_id"), "requester": g.get("requester"),
                "state": evs[-1].get("to_state")}

    def create_execution_request(self, plan, requester, now="",
                                 *, commit=False) -> RequestEventRecord:
        """실행 요청 생성(genesis REQUESTED, is_executed=False). **요청 기록만 — 실행 아님. 사람 승인 대기.**"""
        self._plan_meta(plan)
        seq = len(ledger.requests_for(plan))
        req = M.request_id(plan, seq)
        evs = ledger.request_events(req)
        if evs:
            return RequestEventRecord(**{k: v for k, v in evs[0].items()
                                         if k in RequestEventRecord.__dataclass_fields__})
        ev = self._request_event(req, plan, requester, "", GENESIS, M.R_REQUESTED, "requested", now,
                                 commit=commit)
        self._artifact(M.ART_REQUEST, req, M.artifact_id(M.ART_PLAN, plan), now, commit=commit)
        return ev

    def submit_request(self, req, note="submitted", now="", *, commit=False):
        m = self._request_meta(req)
        return self._request_transition(req, m, M.R_SUBMITTED, "", note, now, commit=commit)

    def approve_request(self, req, approver, note="approved", now="", *, commit=False):
        """실행 요청 승인(SUBMITTED→APPROVED). **사람 승인자 필수. APPROVED ≠ EXECUTED — 실행하지 않는다.**"""
        if not approver:
            raise ApproverRequired("실행 요청 승인은 approver 필수")
        m = self._request_meta(req)
        return self._request_transition(req, m, M.R_APPROVED, approver, note, now, commit=commit)

    def reject_request(self, req, approver, note="rejected", now="", *, commit=False):
        """실행 요청 거절(SUBMITTED→REJECTED). **사람 승인자 필수.**"""
        if not approver:
            raise ApproverRequired("실행 요청 거절은 approver 필수")
        m = self._request_meta(req)
        return self._request_transition(req, m, M.R_REJECTED, approver, note, now, commit=commit)

    def _request_transition(self, req, m, to, approver, note, now, *, commit):
        frm = m["state"]
        if not M.can_request_transition(frm, to):
            raise IllegalRequestTransition(f"요청 {req} {frm}→{to} 불가")
        return self._request_event(req, m["plan_id"], m["requester"], approver, frm, to, note, now,
                                   commit=commit)

    # ══════════════ record_history ══════════════
    def record_history(self, plan, phase, outcome="RECORDED", detail="", now="",
                       *, commit=False) -> HistoryRecord:
        """실험 이력 기록(불변, 사람이 관찰한 결과). **기록만 — 실행 아님.**"""
        self._plan_meta(plan)
        if outcome not in M.HISTORY_OUTCOMES:
            raise ValueError(f"미지원 outcome {outcome}")
        seq = len(ledger.history_for(plan))
        hid = M.history_id(plan, seq)
        rec = HistoryRecord(history_id=hid, plan_id=plan, phase=phase, outcome=outcome, detail=detail,
                            created_at=now, input_hash=input_digest(plan, seq),
                            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.history_exists, ledger.history_head, ledger.append_history, hid, rec,
                         commit=commit)
        return HistoryRecord(**rec)

    # ══════════════ generate_report ══════════════
    def generate_report(self, scope="SYSTEM", now="", *, commit=False) -> OrchestrationReportRecord:
        """조정 리포트(계획·스케줄·의존성·요청·이력 집계). **is_binding=False, ORCHESTRATION ≠ EXECUTION.**"""
        plans = ledger.plan_ids()
        pstates = {p: self.plan_state(p) for p in plans}
        requests = ledger.request_ids()
        rstates = {r: self.request_state(r) for r in requests}
        state_dist: dict = {}
        for st in pstates.values():
            state_dist[st] = state_dist.get(st, 0) + 1
        req_dist: dict = {}
        for st in rstates.values():
            req_dist[st] = req_dist.get(st, 0) + 1
        rid = M.report_id(scope, now)
        rec = OrchestrationReportRecord(
            report_id=rid, scope=scope, plan_count=len(plans),
            active_plan_count=sum(1 for st in pstates.values() if st != M.P_ARCHIVED),
            concluded_plan_count=sum(1 for st in pstates.values()
                                     if st in (M.P_CONCLUDED, M.P_ARCHIVED)),
            schedule_count=len(ledger.read_schedules()),
            dependency_count=len(ledger.read_dependencies()), request_count=len(requests),
            approved_request_count=sum(1 for st in rstates.values() if st == M.R_APPROVED),
            history_count=len(ledger.read_history()),
            state_distribution=dict(sorted(state_dist.items())),
            request_state_distribution=dict(sorted(req_dist.items())), is_binding=False,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(scope, now),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.report_exists, ledger.reports_head, ledger.append_report, rid, rec,
                         commit=commit)
        self._artifact(M.ART_REPORT, rid, "", now, commit=commit)
        return OrchestrationReportRecord(**rec)

    def verify_integrity(self) -> dict:
        from jarvis.experiment_orchestration.verify import verify_chain
        return verify_chain()

    def list_plans(self) -> list:
        return ledger.plan_ids()

    def plans_in_state(self, state) -> list:
        return sorted(p for p in ledger.plan_ids() if self.plan_state(p) == state)

    def summary(self, now="") -> OrchestrationSummary:
        return OrchestrationSummary(
            timestamp=now, plan_event_count=len(ledger.read_plan_events()),
            plan_count=len(ledger.plan_ids()), schedule_count=len(ledger.read_schedules()),
            dependency_count=len(ledger.read_dependencies()),
            request_event_count=len(ledger.read_request_events()),
            request_count=len(ledger.request_ids()), history_count=len(ledger.read_history()),
            report_count=len(ledger.read_reports()), artifact_count=len(ledger.read_artifacts()))
