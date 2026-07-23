"""Research Decision Intelligence 원장 (P10.7) — 7개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 di_ 접두사. 각 레코드: id · previous_hash · record_hash · timestamp. 판단 지원 기록만 —
전략선택/배포/자본배분/실행 없음. 상위 레이어(P10.2~P10.6) 원장은 **READ ONLY** 로만 읽는다.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (di_ 접두사)
CANDIDATES = ("di_candidates.jsonl", "event_id")            # 이벤트 소싱
DECISION_SESSIONS = ("di_decision_sessions.jsonl", "event_id")  # 이벤트 소싱
FRAMEWORKS = ("di_frameworks.jsonl", "framework_id")
SCORECARDS = ("di_scorecards.jsonl", "scorecard_id")
TRADEOFFS = ("di_tradeoffs.jsonl", "tradeoff_id")
REPORTS = ("di_reports.jsonl", "report_id")
ARTIFACTS = ("di_artifacts.jsonl", "artifact_id")

ALL_LEDGERS = (CANDIDATES, DECISION_SESSIONS, FRAMEWORKS, SCORECARDS, TRADEOFFS,
               REPORTS, ARTIFACTS)

# 상위 레이어 물리 원장(READ ONLY 데이터 소스) — import 결합 없음, 파일만 읽는다.
SOURCE_LEDGERS = {
    "STRATEGY": ("research_governance", "rg_strategies.jsonl", "strategy_id"),
    "SIGNAL": ("alpha_intelligence", "ai_signals.jsonl", "signal_id"),
    "PORTFOLIO": ("portfolio_research", "pr_portfolios.jsonl", "portfolio_id"),
    "GRAPH": ("research_kg", "kg_entities.jsonl", "entity_id"),
    "AGENT_RESEARCH": ("agent_governance", "arg_proposals.jsonl", "proposal_id"),
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


# ── 상위 레이어 READ ONLY 소스 ──
def read_source(filename: str) -> list[dict]:
    """상위 레이어 원장을 읽기 전용으로 로드. 절대 쓰지 않는다."""
    return read_jsonl(filename)


# ── Candidates (event-sourced) ──
def append_candidate_event(rec: dict) -> None:
    _append(CANDIDATES[0], rec)


def read_candidate_events() -> list[dict]:
    return read_jsonl(CANDIDATES[0])


def candidates_head() -> dict | None:
    return _head(CANDIDATES[0])


def candidate_event_exists(event_id: str) -> bool:
    return _exists(CANDIDATES[0], CANDIDATES[1], event_id)


def candidate_events_for(candidate_id: str) -> list[dict]:
    return [r for r in read_candidate_events() if r.get("candidate_id") == candidate_id]


def distinct_candidates() -> list[dict]:
    out: dict = {}
    for r in read_candidate_events():
        cid = r.get("candidate_id")
        if cid not in out:
            out[cid] = r
    return list(out.values())


# ── Decision sessions (event-sourced) ──
def append_session_event(rec: dict) -> None:
    _append(DECISION_SESSIONS[0], rec)


def read_session_events() -> list[dict]:
    return read_jsonl(DECISION_SESSIONS[0])


def sessions_head() -> dict | None:
    return _head(DECISION_SESSIONS[0])


def session_event_exists(event_id: str) -> bool:
    return _exists(DECISION_SESSIONS[0], DECISION_SESSIONS[1], event_id)


def session_events_for(session_id: str) -> list[dict]:
    return [r for r in read_session_events() if r.get("session_id") == session_id]


def distinct_sessions() -> list[dict]:
    out: dict = {}
    for r in read_session_events():
        sid = r.get("session_id")
        if sid not in out:
            out[sid] = r
    return list(out.values())


# ── Frameworks ──
def append_framework(rec: dict) -> None:
    _append(FRAMEWORKS[0], rec)


def read_frameworks() -> list[dict]:
    return read_jsonl(FRAMEWORKS[0])


def frameworks_head() -> dict | None:
    return _head(FRAMEWORKS[0])


def framework_exists(framework_id: str) -> bool:
    return _exists(FRAMEWORKS[0], FRAMEWORKS[1], framework_id)


def get_framework(framework_id: str) -> dict | None:
    for r in read_frameworks():
        if r.get("framework_id") == framework_id:
            return r
    return None


# ── Scorecards ──
def append_scorecard(rec: dict) -> None:
    _append(SCORECARDS[0], rec)


def read_scorecards() -> list[dict]:
    return read_jsonl(SCORECARDS[0])


def scorecards_head() -> dict | None:
    return _head(SCORECARDS[0])


def scorecard_exists(scorecard_id: str) -> bool:
    return _exists(SCORECARDS[0], SCORECARDS[1], scorecard_id)


def scorecards_for_session(session_id: str) -> list[dict]:
    return [r for r in read_scorecards() if r.get("session_id") == session_id]


# ── Tradeoffs ──
def append_tradeoff(rec: dict) -> None:
    _append(TRADEOFFS[0], rec)


def read_tradeoffs() -> list[dict]:
    return read_jsonl(TRADEOFFS[0])


def tradeoffs_head() -> dict | None:
    return _head(TRADEOFFS[0])


def tradeoff_exists(tradeoff_id: str) -> bool:
    return _exists(TRADEOFFS[0], TRADEOFFS[1], tradeoff_id)


def tradeoffs_for_session(session_id: str) -> list[dict]:
    return [r for r in read_tradeoffs() if r.get("session_id") == session_id]


# ── Reports ──
def append_report(rec: dict) -> None:
    _append(REPORTS[0], rec)


def read_reports() -> list[dict]:
    return read_jsonl(REPORTS[0])


def reports_head() -> dict | None:
    return _head(REPORTS[0])


def report_exists(report_id: str) -> bool:
    return _exists(REPORTS[0], REPORTS[1], report_id)


# ── Artifacts ──
def append_artifact(rec: dict) -> None:
    _append(ARTIFACTS[0], rec)


def read_artifacts() -> list[dict]:
    return read_jsonl(ARTIFACTS[0])


def artifacts_head() -> dict | None:
    return _head(ARTIFACTS[0])


def artifact_exists(artifact_id: str) -> bool:
    return _exists(ARTIFACTS[0], ARTIFACTS[1], artifact_id)
