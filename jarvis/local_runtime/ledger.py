"""Local Runtime 원장 (P42) — 2개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 lrt_ 접두사(Local RunTime). 런타임 생애 이벤트(startup/restart/stop/health)·로그만 기록한다.
**기존 원장은 건드리지 않는다(자체 lrt_ 원장만 append).** 상태 변경·거래·집행 없음.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

EVENTS = ("lrt_events.jsonl", "event_id")     # 런타임 생애 이벤트
LOGS = ("lrt_logs.jsonl", "log_id")          # 런타임 로그

ALL_LEDGERS = (EVENTS, LOGS)


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


append_event, read_events, events_head, event_exists = _readers(EVENTS)
append_log, read_logs, logs_head, log_exists = _readers(LOGS)
