"""Research Loop 원장 (C5) — 3개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 rloop_ 접두사. 연구 루프 단계 이벤트·사람 검토·리포트만 기록. 자동 실행·집행 없음.
기존 원장(experiments/reports 등)은 READ ONLY 참조.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

LOOPS = ("rloop_loops.jsonl", "loop_event_id")     # 단계 이벤트(ES)
REVIEWS = ("rloop_reviews.jsonl", "review_id")     # 사람 검토 결정
REPORTS = ("rloop_reports.jsonl", "report_id")     # 리포트

ALL_LEDGERS = (LOOPS, REVIEWS, REPORTS)

# 참조 대상(READ ONLY 소스)
SOURCE_LAYERS = {
    "experiment_tracking": ("expt_experiments.jsonl", "experiment_id"),
    "research_assistant": ("ras_reports.jsonl", "report_id"),
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
    return len(read_jsonl(spec[0])) if spec else 0


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


append_loop_event, read_loop_events, loops_head, loop_event_exists = _readers(LOOPS)
append_review, read_reviews, reviews_head, review_exists = _readers(REVIEWS)
append_report, read_reports, reports_head, report_exists = _readers(REPORTS)


def loop_events(loop) -> list[dict]:
    return [r for r in read_loop_events() if r.get("loop_id") == loop]


def loop_ids() -> list[str]:
    return sorted({r.get("loop_id") for r in read_loop_events() if r.get("loop_id")})


def reviews_for(loop) -> list[dict]:
    return [r for r in read_reviews() if r.get("loop_id") == loop]
