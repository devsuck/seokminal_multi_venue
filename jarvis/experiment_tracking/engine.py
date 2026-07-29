"""Experiment Tracking Engine (P42) — 모든 연구 실험 추적. **실행 없음, 동작 없음.**

실험·실행·파라미터·아티팩트·결과·비교를 기록한다. 데이터셋 버전·코드 버전·파라미터·지표·결과를 추적한다. **실행 없음 —
외부에서 사람이 수행한 실험의 기록만.** execution/broker/live_trading/portfolio_execution import·호출 없음.
TRACK ≠ EXECUTE · RECORD ≠ RUN. 결정적·불변·append-only. 상위 계층은 READ ONLY.
"""
from __future__ import annotations

from jarvis.experiment_tracking import ledger
from jarvis.experiment_tracking import models as M
from jarvis.experiment_tracking.models import (
    GENESIS,
    ArtifactRecord,
    ComparisonRecord,
    ExperimentRecord,
    ExperimentReportRecord,
    ParameterRecord,
    ResultRecord,
    RunRecord,
    TrackingSummary,
    UnknownEntityError,
    content_hash,
    input_digest,
)

_DISCLAIMER = ("Experiment Tracking Platform 데이터 — TRACK ≠ EXECUTE · RECORD ≠ RUN. 실험·실행·파라미터·"
               "아티팩트·결과·비교 추적 전용 — 실행·거래·배포·자본 배분 없음. 외부에서 사람이 수행한 실험의 기록만.")


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ExperimentTrackingEngine:
    """실험 추적 엔진. 불변·append-only·결정적. 실행/거래/배포/배분 권한 없음 — 추적만."""

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

    # ══════════════ create_experiment ══════════════
    def create_experiment(self, name, objective="", tags=None, now="",
                          *, commit=False) -> ExperimentRecord:
        """실험 등록(불변)."""
        eid = M.experiment_id(name)
        existing = ledger.experiment_by_id(eid)
        if existing:
            return ExperimentRecord(**{k: v for k, v in existing.items()
                                       if k in ExperimentRecord.__dataclass_fields__})
        rec = ExperimentRecord(experiment_id=eid, name=name, objective=objective,
                               tags=list(tags or []), created_at=now, input_hash=input_digest(name),
                               previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.experiment_exists, ledger.experiments_head, ledger.append_experiment,
                         eid, rec, commit=commit)
        self._artifact(M.ART_EXPERIMENT, eid, "", now, commit=commit)
        return ExperimentRecord(**rec)

    # ══════════════ record_run ══════════════
    def record_run(self, experiment, dataset_version="", code_version="", note="", now="",
                   *, commit=False) -> RunRecord:
        """실행(run) 기록(불변, status=RECORDED). **외부 실행 결과 기록만 — 실행 아님.**"""
        if not ledger.experiment_by_id(experiment):
            raise UnknownEntityError(f"미등록 실험 {experiment}")
        seq = len(ledger.runs_for(experiment))
        rid = M.run_id(experiment, seq)
        rec = RunRecord(run_id=rid, experiment_id=experiment, dataset_version=dataset_version,
                        code_version=code_version, status="RECORDED", note=note, created_at=now,
                        input_hash=input_digest(experiment, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.run_exists, ledger.runs_head, ledger.append_run, rid, rec,
                         commit=commit)
        self._artifact(M.ART_RUN, rid, M.artifact_id(M.ART_EXPERIMENT, experiment), now,
                       commit=commit)
        return RunRecord(**rec)

    # ══════════════ record_parameter ══════════════
    def record_parameter(self, run, key, value, now="", *, commit=False) -> ParameterRecord:
        """파라미터 기록(불변)."""
        if not ledger.run_by_id(run):
            raise UnknownEntityError(f"미등록 run {run}")
        pid = M.parameter_id(run, key)
        existing = next((p for p in ledger.parameters_for(run) if p.get("parameter_id") == pid), None)
        if existing:
            return ParameterRecord(**{k: v for k, v in existing.items()
                                      if k in ParameterRecord.__dataclass_fields__})
        rec = ParameterRecord(parameter_id=pid, run_id=run, key=key, value=str(value), created_at=now,
                              input_hash=input_digest(run, key), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.parameter_exists, ledger.parameters_head, ledger.append_parameter,
                         pid, rec, commit=commit)
        return ParameterRecord(**rec)

    # ══════════════ record_result ══════════════
    def record_result(self, run, metric, value, now="", *, commit=False) -> ResultRecord:
        """결과·지표 기록(불변)."""
        if not ledger.run_by_id(run):
            raise UnknownEntityError(f"미등록 run {run}")
        rid = M.result_id(run, metric)
        existing = next((r for r in ledger.results_for(run) if r.get("result_id") == rid), None)
        if existing:
            return ResultRecord(**{k: v for k, v in existing.items()
                                   if k in ResultRecord.__dataclass_fields__})
        rec = ResultRecord(result_id=rid, run_id=run, metric=metric, value=float(value),
                           created_at=now, input_hash=input_digest(run, metric),
                           previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.result_exists, ledger.results_head, ledger.append_result, rid, rec,
                         commit=commit)
        return ResultRecord(**rec)

    # ══════════════ attach_artifact ══════════════
    def attach_artifact(self, run, artifact_ref, artifact_type="LOG", now="",
                        *, commit=False) -> ArtifactRecord:
        """실행에 아티팩트 연결(불변, 계보). **첨부·기록만.**"""
        if not ledger.run_by_id(run):
            raise UnknownEntityError(f"미등록 run {run}")
        if artifact_type not in M.ARTIFACT_TYPES:
            raise ValueError(f"미지원 artifact_type {artifact_type}")
        return self._artifact(M.ART_ATTACHED, f"{run}:{artifact_ref}",
                              M.artifact_id(M.ART_RUN, run), now, commit=commit)

    # ══════════════ compare_runs (결정적 비교) ══════════════
    def compare_runs(self, run_a, run_b, now="", *, commit=False) -> ComparisonRecord:
        """두 실행 지표 비교(결정적 델타). **비교·기록만 — 선택/승인 아님.**"""
        ra, rb = ledger.run_by_id(run_a), ledger.run_by_id(run_b)
        if not ra or not rb:
            raise UnknownEntityError(f"미등록 run {run_a if not ra else run_b}")
        results_a = {r.get("metric"): r.get("value") for r in ledger.results_for(run_a)}
        results_b = {r.get("metric"): r.get("value") for r in ledger.results_for(run_b)}
        metrics = sorted(set(results_a) | set(results_b))
        deltas = {m: M.metric_delta(results_a.get(m, 0.0), results_b.get(m, 0.0)) for m in metrics}
        cid = M.comparison_id(run_a, run_b)
        rec = ComparisonRecord(
            comparison_id=cid, experiment_id=ra.get("experiment_id"), run_a=run_a, run_b=run_b,
            metric_deltas=deltas, created_at=now, input_hash=input_digest(run_a, run_b),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.comparison_exists, ledger.comparisons_head, ledger.append_comparison,
                         cid, rec, commit=commit)
        return ComparisonRecord(**rec)

    # ══════════════ generate_summary ══════════════
    def generate_summary(self, experiment) -> dict:
        """실험 요약(실행·결과 집계, 결정적, READ ONLY). **요약만.**"""
        if not ledger.experiment_by_id(experiment):
            raise UnknownEntityError(f"미등록 실험 {experiment}")
        runs = ledger.runs_for(experiment)
        run_ids = [r.get("run_id") for r in runs]
        best: dict = {}
        for run in run_ids:
            for r in ledger.results_for(run):
                m, v = r.get("metric"), r.get("value")
                if m not in best or v > best[m]["value"]:
                    best[m] = {"run_id": run, "value": v}
        return {"experiment_id": experiment, "run_count": len(runs), "runs": sorted(run_ids),
                "best_by_metric": best}

    # ══════════════ generate_report ══════════════
    def generate_report(self, scope="SYSTEM", now="", *, commit=False) -> ExperimentReportRecord:
        """추적 리포트(실험·실행·파라미터·결과·비교 집계). **is_binding=False, TRACK ≠ EXECUTE.**"""
        runs = ledger.read_runs()
        st_dist: dict = {}
        for r in runs:
            st_dist[r.get("status")] = st_dist.get(r.get("status"), 0) + 1
        attached = sum(1 for a in ledger.read_artifacts() if a.get("artifact_type") == M.ART_ATTACHED)
        rid = M.report_id(scope, now)
        rec = ExperimentReportRecord(
            report_id=rid, scope=scope, experiment_count=len(ledger.read_experiments()),
            run_count=len(runs), parameter_count=len(ledger.read_parameters()),
            result_count=len(ledger.read_results()), comparison_count=len(ledger.read_comparisons()),
            attached_artifact_count=attached, status_distribution=dict(sorted(st_dist.items())),
            is_binding=False, disclaimer=_DISCLAIMER, created_at=now,
            input_hash=input_digest(scope, now), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.report_exists, ledger.reports_head, ledger.append_report, rid, rec,
                         commit=commit)
        self._artifact(M.ART_REPORT, rid, "", now, commit=commit)
        return ExperimentReportRecord(**rec)

    def verify_integrity(self) -> dict:
        from jarvis.experiment_tracking.verify import verify_chain
        return verify_chain()

    def list_experiments(self) -> list:
        return sorted(e.get("experiment_id") for e in ledger.read_experiments())

    def summary(self, now="") -> TrackingSummary:
        return TrackingSummary(
            timestamp=now, experiment_count=len(ledger.read_experiments()),
            run_count=len(ledger.read_runs()), parameter_count=len(ledger.read_parameters()),
            result_count=len(ledger.read_results()), comparison_count=len(ledger.read_comparisons()),
            report_count=len(ledger.read_reports()), artifact_count=len(ledger.read_artifacts()))
