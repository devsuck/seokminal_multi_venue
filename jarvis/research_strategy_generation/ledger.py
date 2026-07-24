"""Research Strategy Generation 원장 (P29) — 7개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 rsg_ 접두사(Research Strategy Generation). 각 레코드: id · timestamp · previous_hash · record_hash.
후보 생성 기록만 — 선택·실행·거래·배포 없음. 상위 계층(P10~P28)은 **READ ONLY** — 파일만 읽는다(소유 결합 없음, 변경 없음).
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

SESSIONS = ("rsg_sessions.jsonl", "session_event_id")             # 생성 세션 생애주기(ES)
CANDIDATES = ("rsg_candidates.jsonl", "candidate_event_id")       # 전략 후보 생애주기(ES)
HYPOTHESES = ("rsg_hypotheses.jsonl", "hypothesis_id")            # 가설
NOVELTY = ("rsg_novelty.jsonl", "novelty_id")                    # 신규성 분석
EVIDENCE = ("rsg_evidence.jsonl", "evidence_id")                 # 증거
REPORTS = ("rsg_reports.jsonl", "report_id")                    # 생성 리포트
ARTIFACTS = ("rsg_artifacts.jsonl", "artifact_id")             # 계보

ALL_LEDGERS = (SESSIONS, CANDIDATES, HYPOTHESES, NOVELTY, EVIDENCE, REPORTS, ARTIFACTS)

# ── 역사적 지식(READ ONLY 소스) — import 결합 없음, 파일만 읽는다. ──
SOURCE_LAYERS = {
    "alpha_intelligence": ("ai_experiments.jsonl", "experiment_id"),      # P10.3
    "knowledge_graph": ("kg_entities.jsonl", "entity_id"),                # P10.5
    "simulation": ("sim_scenarios.jsonl", "event_id"),                   # P10.8
    "research_memory": ("rm_lessons.jsonl", "lesson_id"),                # P20
    "autonomous_research": ("ar_cycles.jsonl", "cycle_event_id"),        # P25
    "memory_intelligence": ("rmi_memories.jsonl", "memory_event_id"),    # P27
    "insight_intelligence": ("rii_insights.jsonl", "insight_event_id"),  # P28
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


append_session_event, read_session_events, sessions_head, session_event_exists = _readers(SESSIONS)
append_candidate_event, read_candidate_events, candidates_head, candidate_event_exists = _readers(CANDIDATES)
append_hypothesis, read_hypotheses, hypotheses_head, hypothesis_exists = _readers(HYPOTHESES)
append_novelty, read_novelty, novelty_head, novelty_exists = _readers(NOVELTY)
append_evidence, read_evidence, evidence_head, evidence_exists = _readers(EVIDENCE)
append_report, read_reports, reports_head, report_exists = _readers(REPORTS)
append_artifact, read_artifacts, artifacts_head, artifact_exists = _readers(ARTIFACTS)


def session_events(sess) -> list[dict]:
    return [r for r in read_session_events() if r.get("session_id") == sess]


def session_ids() -> list[str]:
    return sorted({r.get("session_id") for r in read_session_events() if r.get("session_id")})


def candidate_events(cand) -> list[dict]:
    return [r for r in read_candidate_events() if r.get("candidate_id") == cand]


def candidate_ids() -> list[str]:
    return sorted({r.get("candidate_id") for r in read_candidate_events() if r.get("candidate_id")})


def candidates_in_session(sess) -> list[str]:
    return sorted({r.get("candidate_id") for r in read_candidate_events()
                   if r.get("session_id") == sess})


def novelty_for(cand) -> list[dict]:
    return [r for r in read_novelty() if r.get("candidate_id") == cand]


def evidence_for(cand) -> list[dict]:
    return [r for r in read_evidence() if r.get("candidate_id") == cand]
