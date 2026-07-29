"""Experiment Tracking 원장 (P42) — 7개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 expt_ 접두사(EXPeriment Tracking). 각 레코드: id · timestamp · previous_hash · record_hash. 실험 추적
기록만 — 실행 없음. 상위 계층은 **READ ONLY** — 파일만 읽는다(소유 결합 없음, 변경 없음).
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

EXPERIMENTS = ("expt_experiments.jsonl", "experiment_id")        # 실험 레지스트리
RUNS = ("expt_runs.jsonl", "run_id")                            # 실행(run)
PARAMETERS = ("expt_parameters.jsonl", "parameter_id")          # 파라미터
RESULTS = ("expt_results.jsonl", "result_id")                  # 결과·지표
COMPARISONS = ("expt_comparisons.jsonl", "comparison_id")      # 비교
REPORTS = ("expt_reports.jsonl", "report_id")                 # 리포트
ARTIFACTS = ("expt_artifacts.jsonl", "artifact_id")          # 아티팩트·계보

ALL_LEDGERS = (EXPERIMENTS, RUNS, PARAMETERS, RESULTS, COMPARISONS, REPORTS, ARTIFACTS)

# ── 참조 대상(READ ONLY 소스) — import 결합 없음, 파일만 읽는다. ──
SOURCE_LAYERS = {
    "data_infrastructure": ("dinf_datasets.jsonl", "dataset_event_id"),  # P41
    "strategy_generation": ("rsg_candidates.jsonl", "candidate_event_id"),  # P29
    "simulation": ("sim_scenarios.jsonl", "event_id"),                  # P10.8
}


def _append(filename, record) -> None:
    p = state_path(filename)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def read_jsonl(filename) -> list[dict]:
    p = state_path(filename)
    if not os.path.exists(p):
        return []
    out: list[dict] = []
    with open(p) as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except (ValueError, json.JSONDecodeError):
                continue
    return out


def _head(filename):
    recs = read_jsonl(filename)
    return recs[-1] if recs else None


def _exists(filename, id_field, rid) -> bool:
    return any(r.get(id_field) == rid for r in read_jsonl(filename))


def source_count(layer) -> int:
    spec = SOURCE_LAYERS.get(layer)
    if not spec:
        return 0
    return len(read_jsonl(spec[0]))


def source_present(layer) -> bool:
    spec = SOURCE_LAYERS.get(layer)
    if not spec:
        return False
    return os.path.exists(state_path(spec[0]))


def all_source_counts() -> dict:
    return {k: source_count(k) for k in sorted(SOURCE_LAYERS)}


def _readers(spec):
    fname, idf = spec

    def append(rec):
        _append(fname, rec)

    def read():
        return read_jsonl(fname)

    def head():
        return _head(fname)

    def exists(rid):
        return _exists(fname, idf, rid)

    return append, read, head, exists


append_experiment, read_experiments, experiments_head, experiment_exists = _readers(EXPERIMENTS)
append_run, read_runs, runs_head, run_exists = _readers(RUNS)
append_parameter, read_parameters, parameters_head, parameter_exists = _readers(PARAMETERS)
append_result, read_results, results_head, result_exists = _readers(RESULTS)
append_comparison, read_comparisons, comparisons_head, comparison_exists = _readers(COMPARISONS)
append_report, read_reports, reports_head, report_exists = _readers(REPORTS)
append_artifact, read_artifacts, artifacts_head, artifact_exists = _readers(ARTIFACTS)


def experiment_by_id(exp):
    return next((r for r in read_experiments() if r.get("experiment_id") == exp), None)


def run_by_id(run):
    return next((r for r in read_runs() if r.get("run_id") == run), None)


def runs_for(exp) -> list[dict]:
    return [r for r in read_runs() if r.get("experiment_id") == exp]


def parameters_for(run) -> list[dict]:
    return [r for r in read_parameters() if r.get("run_id") == run]


def results_for(run) -> list[dict]:
    return [r for r in read_results() if r.get("run_id") == run]
