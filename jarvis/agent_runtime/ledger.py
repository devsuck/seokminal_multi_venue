"""Agent Runtime 원장 (P45) — 7개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 agrt_ 접두사(AGent RunTime). 각 레코드: id · timestamp · previous_hash · record_hash. 에이전트 생애주기·
태스크 배정·산출물·메모리 참조·로그 기록만 — 거래·배포·실행·자본 결정 없음. 상위 계층은 **READ ONLY** — 파일만
읽는다(소유 결합 없음, 변경 없음).
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

AGENTS = ("agrt_agents.jsonl", "agent_event_id")             # 에이전트 생애주기(ES)
ASSIGNMENTS = ("agrt_assignments.jsonl", "task_id")         # 태스크 배정
OUTPUTS = ("agrt_outputs.jsonl", "output_id")             # 산출물
MEMORY_REFS = ("agrt_memory_refs.jsonl", "memref_id")    # 메모리 참조(READ ONLY)
LOGS = ("agrt_logs.jsonl", "log_id")                    # 활동 로그
REPORTS = ("agrt_reports.jsonl", "report_id")          # 리포트
ARTIFACTS = ("agrt_artifacts.jsonl", "artifact_id")   # 계보

ALL_LEDGERS = (AGENTS, ASSIGNMENTS, OUTPUTS, MEMORY_REFS, LOGS, REPORTS, ARTIFACTS)

# ── 참조 대상(READ ONLY 소스) — import 결합 없음, 파일만 읽는다. ──
SOURCE_LAYERS = {
    "workflow_automation": ("wf_workflows.jsonl", "workflow_event_id"),  # P44
    "model_management": ("mdl_models.jsonl", "model_event_id"),          # P43
    "experiment_tracking": ("expt_experiments.jsonl", "experiment_id"),  # P42
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


append_agent_event, read_agent_events, agents_head, agent_event_exists = _readers(AGENTS)
append_assignment, read_assignments, assignments_head, assignment_exists = _readers(ASSIGNMENTS)
append_output, read_outputs, outputs_head, output_exists = _readers(OUTPUTS)
append_memref, read_memory_refs, memory_refs_head, memref_exists = _readers(MEMORY_REFS)
append_log, read_logs, logs_head, log_exists = _readers(LOGS)
append_report, read_reports, reports_head, report_exists = _readers(REPORTS)
append_artifact, read_artifacts, artifacts_head, artifact_exists = _readers(ARTIFACTS)


def agent_events(agent) -> list[dict]:
    return [r for r in read_agent_events() if r.get("agent_id") == agent]


def agent_ids() -> list[str]:
    return sorted({r.get("agent_id") for r in read_agent_events() if r.get("agent_id")})


def assignments_for(agent) -> list[dict]:
    return [r for r in read_assignments() if r.get("agent_id") == agent]


def outputs_for(agent) -> list[dict]:
    return [r for r in read_outputs() if r.get("agent_id") == agent]


def memory_refs_for(agent) -> list[dict]:
    return [r for r in read_memory_refs() if r.get("agent_id") == agent]


def logs_for(agent) -> list[dict]:
    return [r for r in read_logs() if r.get("agent_id") == agent]
