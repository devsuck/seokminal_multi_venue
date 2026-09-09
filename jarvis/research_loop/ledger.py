"""Research Loop 원장 (C5) — 3개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 rloop_ 접두사. 연구 루프 단계 이벤트·사람 검토·리포트만 기록. 자동 실행·집행 없음.
기존 원장(experiments/reports 등)은 READ ONLY 참조.
"""
from __future__ import annotations


from jarvis.ledger_io import append as _append, read_jsonl, head as _head, exists as _exists

LOOPS = ("rloop_loops.jsonl", "loop_event_id")     # 단계 이벤트(ES)
REVIEWS = ("rloop_reviews.jsonl", "review_id")     # 사람 검토 결정
REPORTS = ("rloop_reports.jsonl", "report_id")     # 리포트

ALL_LEDGERS = (LOOPS, REVIEWS, REPORTS)

# 참조 대상(READ ONLY 소스)
SOURCE_LAYERS = {
    "experiment_tracking": ("expt_experiments.jsonl", "experiment_id"),
    "research_assistant": ("ras_reports.jsonl", "report_id"),
}


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
