"""Local Automation 원장 (P45) — 5개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 la_ 접두사(Local Automation). 잡 생애주기·스케줄·실행 이력·로그·리포트만 기록한다.
자동 거래·자동 배포·자동 배분 없음. 상위/기존 원장은 **READ ONLY** — 파일만 읽는다(소유 결합 없음, 변경 없음).
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

JOBS = ("la_jobs.jsonl", "job_event_id")          # 잡 생애주기(ES)
SCHEDULES = ("la_schedules.jsonl", "schedule_id")  # 스케줄 디스크립터
RUNS = ("la_runs.jsonl", "run_id")                  # 실행 이력
LOGS = ("la_logs.jsonl", "log_id")                   # 자동화 로그
REPORTS = ("la_reports.jsonl", "report_id")           # 리포트

ALL_LEDGERS = (JOBS, SCHEDULES, RUNS, LOGS, REPORTS)

# ── 참조 대상(READ ONLY 소스) — import 결합 없음, 파일만 읽는다. ──
SOURCE_LAYERS = {
    "experiment_tracking": ("expt_runs.jsonl", "run_id"),
    "memory_intelligence": ("rmi_memories.jsonl", "memory_id"),
    "data_infrastructure": ("dinf_datasets.jsonl", "dataset_event_id"),
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


append_job_event, read_job_events, jobs_head, job_event_exists = _readers(JOBS)
append_schedule, read_schedules, schedules_head, schedule_exists = _readers(SCHEDULES)
append_run, read_runs, runs_head, run_exists = _readers(RUNS)
append_log, read_logs, logs_head, log_exists = _readers(LOGS)
append_report, read_reports, reports_head, report_exists = _readers(REPORTS)


def job_events(job) -> list[dict]:
    return [r for r in read_job_events() if r.get("job_id") == job]


def job_ids() -> list[str]:
    return sorted({r.get("job_id") for r in read_job_events() if r.get("job_id")})


def runs_for(job) -> list[dict]:
    return [r for r in read_runs() if r.get("job_id") == job]


def schedule_for(job) -> dict | None:
    scheds = [r for r in read_schedules() if r.get("job_id") == job]
    return scheds[-1] if scheds else None
