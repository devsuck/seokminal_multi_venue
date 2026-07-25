"""Research Workflow 원장 (P64-67) — 2개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 rwf_ 접두사. **워크플로 단계 이벤트·연구 세션 이벤트만** 기록(오케스트레이션 상태). 실험/실패/포트폴리오/
리스크 등 실제 지식은 기존 원장(expt_/rmi_/pr_/rr_)이 담당 — 이 원장은 조율 상태만. 자동 실행·집행 없음.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

RUNS = ("rwf_runs.jsonl", "event_id")          # 워크플로 단계 이벤트(event-sourced)
SESSIONS = ("rwf_sessions.jsonl", "event_id")  # 연구 세션 이벤트(event-sourced)
LOOPS = ("rwf_loops.jsonl", "event_id")        # 자율 연구 루프 이터레이션(event-sourced, P72)

ALL_LEDGERS = (RUNS, SESSIONS, LOOPS)


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


# ── runs ──
def append_run(rec) -> None:
    _append(RUNS[0], rec)


def read_runs() -> list[dict]:
    return read_jsonl(RUNS[0])


def runs_head():
    return _head(RUNS[0])


def run_events(run_id) -> list[dict]:
    return [r for r in read_runs() if r.get("run_id") == run_id]


# ── sessions ──
def append_session(rec) -> None:
    _append(SESSIONS[0], rec)


def read_sessions() -> list[dict]:
    return read_jsonl(SESSIONS[0])


def sessions_head():
    return _head(SESSIONS[0])


def session_events(session_id) -> list[dict]:
    return [r for r in read_sessions() if r.get("session_id") == session_id]


# ── loops (P72 자율 연구 루프) ──
def append_loop(rec) -> None:
    _append(LOOPS[0], rec)


def read_loops() -> list[dict]:
    return read_jsonl(LOOPS[0])


def loops_head():
    return _head(LOOPS[0])


def loop_events(loop_id) -> list[dict]:
    return [r for r in read_loops() if r.get("loop_id") == loop_id]
