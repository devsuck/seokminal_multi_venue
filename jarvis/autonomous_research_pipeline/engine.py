"""Autonomous Research Pipeline Engine (P12.1) — 중앙 연구 자동화 파이프라인. **오케스트레이션 전용.**

고립된 연구 컴포넌트를 반복 가능한 연구 사이클로 조정한다. **거래 실행·전략 배포·자본 배분·라이브 시스템 수정·
프로덕션 모델 승인·권한 변경을 하지 않는다.** execution/broker/portfolio/risk/permission/deployment/live
import·호출 없음. PIPELINE ≠ EXECUTION · STAGE ≠ DEPLOYMENT · COLLECT ≠ APPROVAL. 결정적·불변·append-only·
이벤트 소싱. 스킵·역행·무단 완료 전이는 거부된다.
"""
from __future__ import annotations

from jarvis.autonomous_research_pipeline import ledger
from jarvis.autonomous_research_pipeline.models import (
    ART_CYCLE,
    ART_OBJECTIVE,
    ART_REPORT,
    ART_RUN,
    GENESIS,
    HIST_REFERENCE,
    HIST_RESULT,
    HIST_REVIEW,
    REF_RESULT,
    REF_REVIEW,
    REF_TYPES,
    S_COMPLETED,
    S_KNOWLEDGE_UPDATE,
    S_OBJECTIVE_CREATED,
    S_RESULT_ANALYSIS,
    S_REVIEW_PENDING,
    STAGE_ORDER,
    ArtifactRecord,
    CycleRecord,
    DanglingReferenceError,
    HistoryRecord,
    IllegalStageTransition,
    ImmutableCycleError,
    ImmutableObjectiveError,
    ImmutablePipelineError,
    ImmutableRunError,
    ImmutableStageError,
    InvalidReferenceType,
    ObjectiveRecord,
    PipelineRecord,
    PipelineReportRecord,
    PipelineSummary,
    RunRecord,
    StageRecord,
    TransitionRecord,
    UnknownCycleError,
    UnknownObjectiveError,
    UnknownPipelineError,
    artifact_id as _artifact_id,
    can_transition,
    content_hash,
    cycle_id as _cycle_id,
    history_id as _history_id,
    input_digest,
    objective_id as _objective_id,
    pipeline_id as _pipeline_id,
    report_id as _report_id,
    run_id as _run_id,
    stage_id as _stage_id,
    transition_event_id as _transition_event_id,
)

_DISCLAIMER = ("Autonomous Research Pipeline 데이터 — PIPELINE ≠ EXECUTION · STAGE ≠ DEPLOYMENT · COLLECT ≠ "
               "APPROVAL. 연구 사이클 오케스트레이션·기록 전용 — 거래 실행·전략 배포·자본 배분·라이브 수정·모델 "
               "승인·권한/설정 변경 없음.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class AutonomousResearchPipelineEngine:
    """자율 연구 파이프라인 엔진. 불변·append-only·이벤트 소싱·결정적. 실행/배포/승인/할당 권한 없음."""

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

    # ══════════════ register_pipeline (Registry) ══════════════
    def register_pipeline(self, name: str, mandate: str = "", now: str = "",
                       *, commit: bool = False) -> PipelineRecord:
        """파이프라인 레지스트리 등록(불변). **등록만.**"""
        pid = _pipeline_id(name)
        existing = ledger.get_pipeline(pid)
        if existing is not None:
            if existing.get("mandate") != mandate:
                raise ImmutablePipelineError(f"{pid} 파이프라인 불변 — 변경 불가")
            return PipelineRecord(**{k: v for k, v in existing.items()
                                     if k in PipelineRecord.__dataclass_fields__})
        rec = PipelineRecord(pipeline_id=pid, name=name, mandate=mandate, created_at=now,
                             input_hash=input_digest(name), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.pipeline_exists(pid):
            head = ledger.registry_head()
            ledger.append_pipeline(_seal(rec, head["record_hash"] if head else GENESIS))
        return PipelineRecord(**rec)

    def _require_pipeline(self, pid: str) -> dict:
        rec = ledger.get_pipeline(pid)
        if rec is None:
            raise UnknownPipelineError(f"미등록 파이프라인 {pid}")
        return rec

    # ══════════════ create_research_objective (Objective Manager) ══════════════
    def create_research_objective(self, pipeline: str, title: str, description: str = "",
                               target_metric: str = "", evidence_ref: str = "", now: str = "",
                               *, commit: bool = False) -> ObjectiveRecord:
        """연구 목표 인테이크(불변). **정의만.**"""
        self._require_pipeline(pipeline)
        oid = _objective_id(pipeline, title)
        existing = ledger.get_objective(oid)
        if existing is not None:
            if existing.get("description") != description:
                raise ImmutableObjectiveError(f"{oid} 목표 불변 — 변경 불가")
            return ObjectiveRecord(**{k: v for k, v in existing.items()
                                      if k in ObjectiveRecord.__dataclass_fields__})
        rec = ObjectiveRecord(objective_id=oid, pipeline_id=pipeline, title=title,
                              description=description, target_metric=target_metric,
                              evidence_ref=evidence_ref, created_at=now,
                              input_hash=input_digest(pipeline, title),
                              previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.objective_exists(oid):
            head = ledger.objectives_head()
            ledger.append_objective(_seal(rec, head["record_hash"] if head else GENESIS))
        self._artifact(ART_OBJECTIVE, oid, "", now, commit=commit)
        return ObjectiveRecord(**rec)

    def _require_objective(self, oid: str) -> dict:
        rec = ledger.get_objective(oid)
        if rec is None:
            raise UnknownObjectiveError(f"미등록 목표 {oid}")
        return rec

    # ══════════════ 스테이지 이벤트(event-sourced) ══════════════
    def _transition(self, cycle: str, frm: str, to: str, note: str, now: str,
                  *, commit: bool) -> TransitionRecord:
        seq = len(ledger.cycle_transitions(cycle))
        eid = _transition_event_id(cycle, to, seq)
        rec = TransitionRecord(transition_event_id=eid, cycle_id=cycle, from_stage=frm, to_stage=to,
                               valid=True, note=note, occurred_at=now,
                               input_hash=input_digest(cycle, to, seq),
                               previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.transition_exists(eid):
            head = ledger.transitions_head()
            ledger.append_transition(_seal(rec, head["record_hash"] if head else GENESIS))
        return TransitionRecord(**rec)

    def _stage_record(self, cycle: str, stage: str, note: str, now: str,
                    *, commit: bool) -> StageRecord:
        sid = _stage_id(cycle, stage)
        rec = StageRecord(stage_id=sid, cycle_id=cycle, stage=stage, sequence=STAGE_ORDER[stage],
                          note=note, entered_at=now, input_hash=input_digest(cycle, stage),
                          previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.stage_exists(sid):
            head = ledger.stages_head()
            ledger.append_stage(_seal(rec, head["record_hash"] if head else GENESIS))
        return StageRecord(**rec)

    def current_stage(self, cycle: str) -> str | None:
        trs = ledger.cycle_transitions(cycle)
        return trs[-1].get("to_stage") if trs else None

    def _require_cycle(self, cycle: str) -> str:
        st = self.current_stage(cycle)
        if st is None:
            raise UnknownCycleError(f"미등록 사이클 {cycle}")
        return st

    # ══════════════ initialize_cycle (Cycle Tracker) ══════════════
    def initialize_cycle(self, objective: str, iteration: int = 1, now: str = "",
                      *, commit: bool = False) -> CycleRecord:
        """연구 사이클 초기화(genesis OBJECTIVE_CREATED). **추적 시작만.**"""
        obj = self._require_objective(objective)
        cid = _cycle_id(objective, iteration)
        existing = ledger.get_cycle(cid)
        if existing is not None:
            return CycleRecord(**{k: v for k, v in existing.items()
                                  if k in CycleRecord.__dataclass_fields__})
        rec = CycleRecord(cycle_id=cid, objective_id=objective, pipeline_id=obj.get("pipeline_id"),
                          iteration=int(iteration), created_at=now,
                          input_hash=input_digest(objective, iteration),
                          previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.cycle_exists(cid):
            head = ledger.cycles_head()
            ledger.append_cycle(_seal(rec, head["record_hash"] if head else GENESIS))
        self._transition(cid, GENESIS, S_OBJECTIVE_CREATED, "objective_created", now, commit=commit)
        self._stage_record(cid, S_OBJECTIVE_CREATED, "genesis", now, commit=commit)
        parent = _artifact_id(ART_OBJECTIVE, objective)
        self._artifact(ART_CYCLE, cid, parent if ledger.artifact_exists(parent) else "", now,
                       commit=commit)
        return CycleRecord(**rec)

    # ══════════════ create_pipeline_run ══════════════
    def create_pipeline_run(self, cycle: str, label: str = "run", note: str = "", now: str = "",
                         *, commit: bool = False) -> RunRecord:
        """파이프라인 런 기록(불변). **기록만.**"""
        self._require_cycle(cycle)
        rid = _run_id(cycle, label)
        existing = None
        for r in ledger.cycle_runs(cycle):
            if r.get("run_id") == rid:
                existing = r
                break
        if existing is not None:
            if existing.get("note") != note:
                raise ImmutableRunError(f"{rid} 런 불변 — 변경 불가")
            return RunRecord(**{k: v for k, v in existing.items()
                                if k in RunRecord.__dataclass_fields__})
        rec = RunRecord(run_id=rid, cycle_id=cycle, label=label, note=note, created_at=now,
                        input_hash=input_digest(cycle, label), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.run_exists(rid):
            head = ledger.runs_head()
            ledger.append_run(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = _artifact_id(ART_CYCLE, cycle)
        self._artifact(ART_RUN, rid, parent if ledger.artifact_exists(parent) else "", now,
                       commit=commit)
        return RunRecord(**rec)

    # ══════════════ advance_stage (전이 규칙 강제) ══════════════
    def advance_stage(self, cycle: str, to_stage: str, note: str = "", now: str = "",
                   *, commit: bool = False) -> TransitionRecord:
        """스테이지 전이(오직 유효 선형 전이). 스킵·역행·무단 완료 거부. **전이 기록만.**"""
        frm = self._require_cycle(cycle)
        if not can_transition(frm, to_stage):
            raise IllegalStageTransition(f"{cycle} {frm}→{to_stage} 불가(스킵/역행/무단 완료)")
        tr = self._transition(cycle, frm, to_stage, note or "advanced", now, commit=commit)
        self._stage_record(cycle, to_stage, note or "", now, commit=commit)
        return tr

    # ══════════════ attach_research_task (Experiment Router / 상태 모델) ══════════════
    def _history(self, cycle: str, kind: str, ref_type: str, ref_id: str, detail: str, now: str,
              *, commit: bool) -> HistoryRecord:
        seq = len(ledger.cycle_history(cycle))
        hid = _history_id(cycle, kind, ref_id, seq)
        rec = HistoryRecord(history_id=hid, cycle_id=cycle, kind=kind, ref_type=ref_type,
                            ref_id=ref_id, detail=detail, recorded_at=now,
                            input_hash=input_digest(cycle, kind, ref_id, seq),
                            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.history_exists(hid):
            head = ledger.history_head()
            ledger.append_history(_seal(rec, head["record_hash"] if head else GENESIS))
        return HistoryRecord(**rec)

    def attach_research_task(self, cycle: str, ref_type: str, ref_id: str, detail: str = "",
                          now: str = "", *, commit: bool = False) -> HistoryRecord:
        """연구 참조 부착(가설/실험/에이전트/데이터셋/리뷰/메모리). 상태 모델 append-only. **기록만.**"""
        st = self._require_cycle(cycle)
        if ref_type not in REF_TYPES:
            raise InvalidReferenceType(f"미등록 참조 유형 {ref_type}")
        if st == S_COMPLETED:
            raise IllegalStageTransition(f"{cycle} 완료됨 — 참조 추가 불가")
        return self._history(cycle, HIST_REFERENCE, ref_type, ref_id, detail, now, commit=commit)

    # ══════════════ collect_results (Result Collector) ══════════════
    def collect_results(self, cycle: str, result_ref: str, detail: str = "", now: str = "",
                     *, commit: bool = False) -> HistoryRecord:
        """결과 수집(EXPERIMENT_RUNNING/RESULT_ANALYSIS 단계). **수집·기록만.**"""
        st = self._require_cycle(cycle)
        if st not in ("EXPERIMENT_RUNNING", S_RESULT_ANALYSIS):
            raise IllegalStageTransition(f"{cycle} {st} 단계에서 결과 수집 불가")
        return self._history(cycle, HIST_RESULT, REF_RESULT, result_ref, detail, now, commit=commit)

    # ══════════════ trigger_review_stage (Review Coordinator) ══════════════
    def trigger_review_stage(self, cycle: str, review_ref: str = "", now: str = "",
                          *, commit: bool = False) -> TransitionRecord:
        """리뷰 라우팅(RESULT_ANALYSIS→REVIEW_PENDING) + 리뷰 참조. **라우팅·기록만.**"""
        st = self._require_cycle(cycle)
        if st != S_RESULT_ANALYSIS:
            raise IllegalStageTransition(f"{cycle} RESULT_ANALYSIS 아님({st}) — 리뷰 라우팅 불가")
        tr = self.advance_stage(cycle, S_REVIEW_PENDING, "review_routing", now, commit=commit)
        if review_ref:
            self._history(cycle, HIST_REVIEW, REF_REVIEW, review_ref, "review", now, commit=commit)
        return tr

    # ══════════════ complete_cycle (Knowledge Connector 종결) ══════════════
    def complete_cycle(self, cycle: str, now: str = "", *, commit: bool = False) -> TransitionRecord:
        """사이클 완료(KNOWLEDGE_UPDATE→COMPLETED). 무단 완료 거부. **종결 기록만.**"""
        st = self._require_cycle(cycle)
        if st != S_KNOWLEDGE_UPDATE:
            raise IllegalStageTransition(f"{cycle} KNOWLEDGE_UPDATE 아님({st}) — 무단 완료 거부")
        return self.advance_stage(cycle, S_COMPLETED, "completed", now, commit=commit)

    # ══════════════ 상태 모델 조회 ══════════════
    def cycle_state_model(self, cycle: str) -> dict:
        """사이클 상태 모델(objective + 참조 유형별 집합). 결정적."""
        c = ledger.get_cycle(cycle)
        if c is None:
            raise UnknownCycleError(f"미등록 사이클 {cycle}")
        model: dict = {t: [] for t in REF_TYPES}
        model["objective"] = [c.get("objective_id")]
        for h in ledger.cycle_history(cycle):
            rt = h.get("ref_type")
            if rt in model and h.get("ref_id"):
                model[rt].append(h.get("ref_id"))
        return {k: sorted(set(v)) for k, v in model.items()}

    def stage_history(self, cycle: str) -> list:
        return [t.get("to_stage") for t in ledger.cycle_transitions(cycle)]

    # ══════════════ generate_pipeline_report ══════════════
    def generate_pipeline_report(self, scope_id: str, scope: str = "PIPELINE", now: str = "",
                              *, commit: bool = False) -> PipelineReportRecord:
        """파이프라인 리포트(사이클·목표·런·스테이지·완료·이력 분포). **is_binding=False, 관찰만.**"""
        cycles = ledger.read_cycles()
        if scope == "PIPELINE":
            cycles = [c for c in cycles if c.get("pipeline_id") == scope_id]
        elif scope == "CYCLE":
            cycles = [c for c in cycles if c.get("cycle_id") == scope_id]
        cids = {c.get("cycle_id") for c in cycles}
        stage_dist: dict = {}
        completed = 0
        for cid in cids:
            st = self.current_stage(cid)
            stage_dist[st] = stage_dist.get(st, 0) + 1
            if st == S_COMPLETED:
                completed += 1
        rid = _report_id(scope, scope_id, now)
        rec = PipelineReportRecord(
            report_id=rid, scope=scope, scope_id=scope_id, cycle_count=len(cids),
            objective_count=len({c.get("objective_id") for c in cycles}),
            run_count=sum(len(ledger.cycle_runs(c)) for c in cids),
            stage_count=sum(len(ledger.cycle_stages(c)) for c in cids),
            completed_count=completed,
            history_count=sum(len(ledger.cycle_history(c)) for c in cids),
            stage_distribution=dict(sorted(stage_dist.items())), is_binding=False,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(scope, scope_id, now),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        self._artifact(ART_REPORT, rid, "", now, commit=commit)
        return PipelineReportRecord(**rec)

    # ══════════════ verify_integrity ══════════════
    def verify_integrity(self) -> dict:
        from jarvis.autonomous_research_pipeline.verify import verify_chain
        return verify_chain()

    # ══════════════ 조회 편의 ══════════════
    def list_cycles(self, pipeline: str = "") -> list:
        cs = ledger.read_cycles()
        if pipeline:
            cs = [c for c in cs if c.get("pipeline_id") == pipeline]
        return sorted(c.get("cycle_id") for c in cs)

    def cycles_in_stage(self, stage: str) -> list:
        return sorted(c for c in ledger.cycle_ids() if self.current_stage(c) == stage)

    # ══════════════ Summary ══════════════
    def summary(self, now: str = "") -> PipelineSummary:
        return PipelineSummary(
            timestamp=now, pipeline_count=len(ledger.read_pipelines()),
            objective_count=len(ledger.read_objectives()), cycle_count=len(ledger.read_cycles()),
            run_count=len(ledger.read_runs()), stage_count=len(ledger.read_stages()),
            transition_count=len(ledger.read_transitions()),
            history_count=len(ledger.read_history()), report_count=len(ledger.read_reports()),
            artifact_count=len(ledger.read_artifacts()))
