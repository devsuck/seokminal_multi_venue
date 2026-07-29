"""Research Assistant 원장 (P44) — 2개 append-only SHA256 해시체인 + READ ONLY 소스 리더. **삭제/수정 없음.**

물리 파일 ras_ 접두사(Research ASsistant). 어시스턴트가 생성한 리포트 스냅샷·자문 노트만 기록한다(자체 원장).
기존 원장(expt_/rmi_/rel_/mdl_ 등)은 **파일만 읽는다(READ ONLY, import 결합 없음, 변경 없음).**
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path
from jarvis.research_assistant.models import SOURCES

REPORTS = ("ras_reports.jsonl", "report_id")     # 어시스턴트 리포트 스냅샷
NOTES = ("ras_notes.jsonl", "note_id")           # 자문 노트(비구속)

ALL_LEDGERS = (REPORTS, NOTES)


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


# ── READ ONLY 소스 리더(기존 원장 파일만 읽음) ──
def read_source(name: str) -> list[dict]:
    fname = SOURCES.get(name)
    if not fname:
        return []
    return read_jsonl(fname)


def source_count(name: str) -> int:
    return len(read_source(name))


def all_source_counts() -> dict:
    return {k: source_count(k) for k in sorted(SOURCES)}


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


append_report, read_reports, reports_head, report_exists = _readers(REPORTS)
append_note, read_notes, notes_head, note_exists = _readers(NOTES)
