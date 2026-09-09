"""Local Runtime 원장 (P42) — 2개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 lrt_ 접두사(Local RunTime). 런타임 생애 이벤트(startup/restart/stop/health)·로그만 기록한다.
**기존 원장은 건드리지 않는다(자체 lrt_ 원장만 append).** 상태 변경·거래·집행 없음.
"""
from __future__ import annotations


from jarvis.ledger_io import append as _append, read_jsonl, head as _head, exists as _exists

EVENTS = ("lrt_events.jsonl", "event_id")     # 런타임 생애 이벤트
LOGS = ("lrt_logs.jsonl", "log_id")          # 런타임 로그

ALL_LEDGERS = (EVENTS, LOGS)


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
