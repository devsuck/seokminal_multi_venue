"""Research Assistant 원장 (P44) — 2개 append-only SHA256 해시체인 + READ ONLY 소스 리더. **삭제/수정 없음.**

물리 파일 ras_ 접두사(Research ASsistant). 어시스턴트가 생성한 리포트 스냅샷·자문 노트만 기록한다(자체 원장).
기존 원장(expt_/rmi_/rel_/mdl_ 등)은 **파일만 읽는다(READ ONLY, import 결합 없음, 변경 없음).**
"""
from __future__ import annotations


from jarvis.config import state_path
from jarvis.ledger_io import append as _append, read_jsonl, head as _head, exists as _exists
from jarvis.research_assistant.models import SOURCES

REPORTS = ("ras_reports.jsonl", "report_id")     # 어시스턴트 리포트 스냅샷
NOTES = ("ras_notes.jsonl", "note_id")           # 자문 노트(비구속)

ALL_LEDGERS = (REPORTS, NOTES)

# ── READ ONLY 소스 리더(기존 원장 파일만 읽음) ──


def read_source(name: str) -> list[dict]:
    fname = SOURCES.get(name)
    if not fname:
        return []
    return read_jsonl(fname, resolver=state_path)


def source_count(name: str) -> int:
    return len(read_source(name))


def all_source_counts() -> dict:
    return {k: source_count(k) for k in sorted(SOURCES)}


def _readers(spec):
    fname, idf = spec

    def append(rec):
        _append(fname, rec, resolver=state_path)

    def read():
        return read_jsonl(fname, resolver=state_path)

    def head():
        return _head(fname, resolver=state_path)

    def exists(rid):
        return _exists(fname, idf, rid, resolver=state_path)

    return append, read, head, exists


append_report, read_reports, reports_head, report_exists = _readers(REPORTS)
append_note, read_notes, notes_head, note_exists = _readers(NOTES)
