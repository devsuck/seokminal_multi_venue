"""Research Reviewer 원장 (P11.5) — 4개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 rvw_ 접두사(ReVieWer). 각 레코드: id · timestamp · previous_hash · record_hash. 연구 품질 AI 리뷰어 —
평가·비평·증거·리포트만, 자동 결정/승인/삭제 없음. 연구 거부는 전략 삭제가 아니다.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (rvw_ 접두사)
REVIEWS = ("rvw_reviews.jsonl", "review_id")
CRITIQUES = ("rvw_critiques.jsonl", "critique_id")
EVIDENCE = ("rvw_evidence.jsonl", "evidence_id")
REPORTS = ("rvw_reports.jsonl", "report_id")

ALL_LEDGERS = (REVIEWS, CRITIQUES, EVIDENCE, REPORTS)


def _append(filename: str, record: dict) -> None:
    p = state_path(filename)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def read_jsonl(filename: str) -> list[dict]:
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


def _head(filename: str) -> dict | None:
    recs = read_jsonl(filename)
    return recs[-1] if recs else None


def _exists(filename: str, id_field: str, rid: str) -> bool:
    return any(r.get(id_field) == rid for r in read_jsonl(filename))


def _get(filename: str, id_field: str, rid: str) -> dict | None:
    for r in read_jsonl(filename):
        if r.get(id_field) == rid:
            return r
    return None


# ── Reviews ──
def append_review(rec: dict) -> None:
    _append(REVIEWS[0], rec)


def read_reviews() -> list[dict]:
    return read_jsonl(REVIEWS[0])


def reviews_head() -> dict | None:
    return _head(REVIEWS[0])


def review_exists(review_id: str) -> bool:
    return _exists(REVIEWS[0], REVIEWS[1], review_id)


def get_review(review_id: str) -> dict | None:
    return _get(REVIEWS[0], REVIEWS[1], review_id)


# ── Critiques ──
def append_critique(rec: dict) -> None:
    _append(CRITIQUES[0], rec)


def read_critiques() -> list[dict]:
    return read_jsonl(CRITIQUES[0])


def critiques_head() -> dict | None:
    return _head(CRITIQUES[0])


def critique_exists(critique_id: str) -> bool:
    return _exists(CRITIQUES[0], CRITIQUES[1], critique_id)


def get_critique(critique_id: str) -> dict | None:
    return _get(CRITIQUES[0], CRITIQUES[1], critique_id)


def review_critiques(review_id: str) -> list[dict]:
    return [r for r in read_critiques() if r.get("review_id") == review_id]


# ── Evidence ──
def append_evidence(rec: dict) -> None:
    _append(EVIDENCE[0], rec)


def read_evidence() -> list[dict]:
    return read_jsonl(EVIDENCE[0])


def evidence_head() -> dict | None:
    return _head(EVIDENCE[0])


def evidence_exists(evidence_id: str) -> bool:
    return _exists(EVIDENCE[0], EVIDENCE[1], evidence_id)


def get_evidence(evidence_id: str) -> dict | None:
    return _get(EVIDENCE[0], EVIDENCE[1], evidence_id)


def critique_evidence(critique_id: str) -> list[dict]:
    return [r for r in read_evidence() if r.get("critique_id") == critique_id]


# ── Reports ──
def append_report(rec: dict) -> None:
    _append(REPORTS[0], rec)


def read_reports() -> list[dict]:
    return read_jsonl(REPORTS[0])


def reports_head() -> dict | None:
    return _head(REPORTS[0])


def report_exists(report_id: str) -> bool:
    return _exists(REPORTS[0], REPORTS[1], report_id)


def get_report(report_id: str) -> dict | None:
    return _get(REPORTS[0], REPORTS[1], report_id)


def review_reports(review_id: str) -> list[dict]:
    return [r for r in read_reports() if r.get("review_id") == review_id]
