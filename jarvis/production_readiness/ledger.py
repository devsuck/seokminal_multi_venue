"""Production Readiness 원장 (P21) — 8개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정/덮어쓰기 없음.**

물리 파일 pd_ 접두사(Production readiness / Deployment governance). 각 레코드: id · timestamp · previous_hash ·
record_hash. 준비성 검증·승인 기록·감사만 — 배포·실행 없음. 상위 계층(P9.8~P20)은 **READ ONLY** — 파일만 읽는다.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 계층 소유 원장 (pd_ 접두사)
CANDIDATES = ("pd_candidates.jsonl", "candidate_id")                # 배포 후보(불변 등록)
READINESS_CHECKS = ("pd_readiness_checks.jsonl", "check_id")        # 준비성 체크리스트
REQUIREMENTS = ("pd_requirements.jsonl", "requirement_id")          # 요구사항 평가
REVIEWS = ("pd_reviews.jsonl", "review_event_id")                   # 리뷰 생애주기(ES)
RISK_ASSESSMENTS = ("pd_risk_assessments.jsonl", "risk_id")         # 전환 리스크 평가
TRANSITIONS = ("pd_transitions.jsonl", "transition_id")             # 후보 상태 머신(ES)
REPORTS = ("pd_reports.jsonl", "report_id")                        # 준비성 리포트
ARTIFACTS = ("pd_artifacts.jsonl", "artifact_id")                  # 아티팩트 계보

ALL_LEDGERS = (CANDIDATES, READINESS_CHECKS, REQUIREMENTS, REVIEWS, RISK_ASSESSMENTS, TRANSITIONS,
               REPORTS, ARTIFACTS)

# ── 상위 소스(READ ONLY) — import 결합 없음, 파일만 읽는다. ──
SOURCE_LAYERS = {
    "data_governance": ("dg_datasets.jsonl", "dataset_hash"),           # P9.8
    "model_governance": ("mg_models.jsonl", "model_hash"),             # P9.9
    "simulation": ("sim_scenarios.jsonl", "event_id"),                # P10.8
    "decision_intelligence": ("di_candidates.jsonl", "event_id"),     # P10.7
    "research_operations": ("ro_workflows.jsonl", "workflow_event_id"),  # P18
    "continuous_learning": ("cl_memories.jsonl", "memory_event_id"),  # P20
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


# ── 상위 소스 READ ONLY ──
def source_count(layer) -> int:
    spec = SOURCE_LAYERS.get(layer)
    if not spec:
        return 0
    return len(read_jsonl(spec[0]))


def source_ref_exists(layer, ref) -> bool:
    spec = SOURCE_LAYERS.get(layer)
    if not spec:
        return False
    p = state_path(spec[0])
    if not os.path.exists(p):
        return False
    return any(r.get(spec[1]) == ref for r in read_jsonl(spec[0]))


# ── helper 팩토리 ──
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


append_candidate, read_candidates, candidates_head, candidate_exists = _readers(CANDIDATES)
append_check, read_checks, checks_head, check_exists = _readers(READINESS_CHECKS)
append_requirement, read_requirements, requirements_head, requirement_exists = _readers(REQUIREMENTS)
append_review_event, read_review_events, reviews_head, review_event_exists = _readers(REVIEWS)
append_risk, read_risks, risks_head, risk_exists = _readers(RISK_ASSESSMENTS)
append_transition, read_transitions, transitions_head, transition_exists = _readers(TRANSITIONS)
append_report, read_reports, reports_head, report_exists = _readers(REPORTS)
append_artifact, read_artifacts, artifacts_head, artifact_exists = _readers(ARTIFACTS)


# ── 그룹 조회 ──
def candidate_ids() -> list[str]:
    return sorted({r.get("candidate_id") for r in read_candidates() if r.get("candidate_id")})


def get_candidate(cand) -> dict | None:
    for r in read_candidates():
        if r.get("candidate_id") == cand:
            return r
    return None


def candidate_transitions(cand) -> list[dict]:
    return [r for r in read_transitions() if r.get("candidate_id") == cand]


def candidate_checks(cand) -> list[dict]:
    return [r for r in read_checks() if r.get("candidate_id") == cand]


def candidate_requirements(cand) -> list[dict]:
    return [r for r in read_requirements() if r.get("candidate_id") == cand]


def candidate_risks(cand) -> list[dict]:
    return [r for r in read_risks() if r.get("candidate_id") == cand]


def review_events(rev) -> list[dict]:
    return [r for r in read_review_events() if r.get("review_id") == rev]


def candidate_reviews(cand) -> list[str]:
    return sorted({r.get("review_id") for r in read_review_events()
                   if r.get("candidate_id") == cand and r.get("review_id")})
