"""Research Conflict Resolution 원장 (P11.9) — 11개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 crf_ 접두사(ConfliCt Resolution). 각 레코드: id · timestamp · previous_hash · record_hash. 연구 충돌
분석·해소 — 기록·분석만, 실행/승인/연구결과수정 없음. 원본 주장·증거·신원·추론·소수의견 보존. 상위 계층
(P11.1/P11.5/P11.6/P11.7/P11.8)은 **READ ONLY** — 증거 참조는 파일만 읽고 절대 쓰지 않는다.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (crf_ 접두사)
REGISTRY = ("crf_registry.jsonl", "registry_id")        # Conflict Registry
CASES = ("crf_cases.jsonl", "event_id")                 # Conflict Cases (event-sourced)
CLAIMS = ("crf_claims.jsonl", "claim_id")               # Conflicting Claims
EVIDENCE = ("crf_evidence.jsonl", "evidence_id")        # Evidence References
POSITIONS = ("crf_positions.jsonl", "position_id")      # Agent Positions
SESSIONS = ("crf_sessions.jsonl", "session_id")         # Resolution Sessions
OUTCOMES = ("crf_outcomes.jsonl", "resolution_id")      # Resolution Outcomes
MINORITY = ("crf_minority.jsonl", "minority_id")        # Minority Opinions
CONSENSUS = ("crf_consensus.jsonl", "consensus_id")     # Consensus Records
REPORTS = ("crf_reports.jsonl", "report_id")            # Conflict Reports
ARTIFACTS = ("crf_artifacts.jsonl", "artifact_id")      # Artifact Lineage

ALL_LEDGERS = (REGISTRY, CASES, CLAIMS, EVIDENCE, POSITIONS, SESSIONS, OUTCOMES, MINORITY,
               CONSENSUS, REPORTS, ARTIFACTS)

# ── 상위 소스 원장(READ ONLY) — 증거 참조 검증용. import 결합 없음, 파일만 읽는다. ──
SOURCE_LEDGERS = {
    "research_agents": ("ragt_reports.jsonl", "report_id"),
    "research_reviewer": ("rvw_reviews.jsonl", "review_id"),
    "research_council": ("cnl_consensus.jsonl", "consensus_id"),
    "research_coordinator": ("rco_reports.jsonl", "report_id"),
    "knowledge_sharing": ("ksh_entries.jsonl", "entry_id"),
}


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


# ── 상위 소스 READ ONLY ──
def source_ref_exists(layer: str, ref: str) -> bool:
    spec = SOURCE_LEDGERS.get(layer)
    if not spec:
        return False
    p = state_path(spec[0])
    if not os.path.exists(p):
        return False
    return any(r.get(spec[1]) == ref for r in read_jsonl(spec[0]))


# ── Registry ──
def append_registry(rec: dict) -> None:
    _append(REGISTRY[0], rec)


def read_registry() -> list[dict]:
    return read_jsonl(REGISTRY[0])


def registry_head() -> dict | None:
    return _head(REGISTRY[0])


def registry_exists(registry_id: str) -> bool:
    return _exists(REGISTRY[0], REGISTRY[1], registry_id)


def get_registry(registry_id: str) -> dict | None:
    return _get(REGISTRY[0], REGISTRY[1], registry_id)


# ── Cases (event-sourced) ──
def append_case_event(rec: dict) -> None:
    _append(CASES[0], rec)


def read_case_events() -> list[dict]:
    return read_jsonl(CASES[0])


def cases_head() -> dict | None:
    return _head(CASES[0])


def case_event_exists(event_id: str) -> bool:
    return _exists(CASES[0], CASES[1], event_id)


def conflict_events(conflict_id: str) -> list[dict]:
    return [r for r in read_case_events() if r.get("conflict_id") == conflict_id]


def conflict_ids() -> list[str]:
    return sorted({r.get("conflict_id") for r in read_case_events() if r.get("conflict_id")})


# ── Claims ──
def append_claim(rec: dict) -> None:
    _append(CLAIMS[0], rec)


def read_claims() -> list[dict]:
    return read_jsonl(CLAIMS[0])


def claims_head() -> dict | None:
    return _head(CLAIMS[0])


def claim_exists(claim_id: str) -> bool:
    return _exists(CLAIMS[0], CLAIMS[1], claim_id)


def get_claim(claim_id: str) -> dict | None:
    return _get(CLAIMS[0], CLAIMS[1], claim_id)


def conflict_claims(conflict_id: str) -> list[dict]:
    return [r for r in read_claims() if r.get("conflict_id") == conflict_id]


# ── Evidence ──
def append_evidence(rec: dict) -> None:
    _append(EVIDENCE[0], rec)


def read_evidence() -> list[dict]:
    return read_jsonl(EVIDENCE[0])


def evidence_head() -> dict | None:
    return _head(EVIDENCE[0])


def evidence_exists(evidence_id: str) -> bool:
    return _exists(EVIDENCE[0], EVIDENCE[1], evidence_id)


def claim_evidence(claim_id: str) -> list[dict]:
    return [r for r in read_evidence() if r.get("claim_id") == claim_id]


def conflict_evidence(conflict_id: str) -> list[dict]:
    return [r for r in read_evidence() if r.get("conflict_id") == conflict_id]


# ── Positions ──
def append_position(rec: dict) -> None:
    _append(POSITIONS[0], rec)


def read_positions() -> list[dict]:
    return read_jsonl(POSITIONS[0])


def positions_head() -> dict | None:
    return _head(POSITIONS[0])


def position_exists(position_id: str) -> bool:
    return _exists(POSITIONS[0], POSITIONS[1], position_id)


def get_position(position_id: str) -> dict | None:
    return _get(POSITIONS[0], POSITIONS[1], position_id)


def conflict_positions(conflict_id: str) -> list[dict]:
    return [r for r in read_positions() if r.get("conflict_id") == conflict_id]


# ── Sessions ──
def append_session(rec: dict) -> None:
    _append(SESSIONS[0], rec)


def read_sessions() -> list[dict]:
    return read_jsonl(SESSIONS[0])


def sessions_head() -> dict | None:
    return _head(SESSIONS[0])


def session_exists(session_id: str) -> bool:
    return _exists(SESSIONS[0], SESSIONS[1], session_id)


def conflict_sessions(conflict_id: str) -> list[dict]:
    return [r for r in read_sessions() if r.get("conflict_id") == conflict_id]


# ── Outcomes ──
def append_outcome(rec: dict) -> None:
    _append(OUTCOMES[0], rec)


def read_outcomes() -> list[dict]:
    return read_jsonl(OUTCOMES[0])


def outcomes_head() -> dict | None:
    return _head(OUTCOMES[0])


def outcome_exists(resolution_id: str) -> bool:
    return _exists(OUTCOMES[0], OUTCOMES[1], resolution_id)


def get_outcome(resolution_id: str) -> dict | None:
    return _get(OUTCOMES[0], OUTCOMES[1], resolution_id)


def conflict_outcomes(conflict_id: str) -> list[dict]:
    return [r for r in read_outcomes() if r.get("conflict_id") == conflict_id]


# ── Minority ──
def append_minority(rec: dict) -> None:
    _append(MINORITY[0], rec)


def read_minority() -> list[dict]:
    return read_jsonl(MINORITY[0])


def minority_head() -> dict | None:
    return _head(MINORITY[0])


def minority_exists(minority_id: str) -> bool:
    return _exists(MINORITY[0], MINORITY[1], minority_id)


def conflict_minority(conflict_id: str) -> list[dict]:
    return [r for r in read_minority() if r.get("conflict_id") == conflict_id]


# ── Consensus ──
def append_consensus(rec: dict) -> None:
    _append(CONSENSUS[0], rec)


def read_consensus() -> list[dict]:
    return read_jsonl(CONSENSUS[0])


def consensus_head() -> dict | None:
    return _head(CONSENSUS[0])


def consensus_exists(consensus_id: str) -> bool:
    return _exists(CONSENSUS[0], CONSENSUS[1], consensus_id)


def get_consensus(consensus_id: str) -> dict | None:
    return _get(CONSENSUS[0], CONSENSUS[1], consensus_id)


# ── Reports ──
def append_report(rec: dict) -> None:
    _append(REPORTS[0], rec)


def read_reports() -> list[dict]:
    return read_jsonl(REPORTS[0])


def reports_head() -> dict | None:
    return _head(REPORTS[0])


def report_exists(report_id: str) -> bool:
    return _exists(REPORTS[0], REPORTS[1], report_id)


# ── Artifacts (lineage) ──
def append_artifact(rec: dict) -> None:
    _append(ARTIFACTS[0], rec)


def read_artifacts() -> list[dict]:
    return read_jsonl(ARTIFACTS[0])


def artifacts_head() -> dict | None:
    return _head(ARTIFACTS[0])


def artifact_exists(artifact_id: str) -> bool:
    return _exists(ARTIFACTS[0], ARTIFACTS[1], artifact_id)
