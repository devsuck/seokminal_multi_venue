"""Research Council 원장 (P11.6) — 11개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 cnl_ 접두사(couNciL). 각 레코드: id · timestamp · previous_hash · record_hash. 다중 에이전트 연구
협의체 — 토론 조율·기록만, 실행/승인/배포/상위 수정 없음. 상위 계층은 참조하지 않는다(자족적 협의).
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (cnl_ 접두사)
COUNCILS = ("cnl_councils.jsonl", "council_id")            # Council Registry
SESSIONS = ("cnl_sessions.jsonl", "session_event_id")      # Council Sessions (event-sourced)
PARTICIPANTS = ("cnl_participants.jsonl", "participant_id")  # Participants
DISCUSSIONS = ("cnl_discussions.jsonl", "discussion_id")   # Discussion Records
ARGUMENTS = ("cnl_arguments.jsonl", "argument_id")         # Research Arguments
VOTES = ("cnl_votes.jsonl", "vote_id")                     # Voting Records
CONSENSUS = ("cnl_consensus.jsonl", "consensus_id")        # Consensus Records
MINORITY = ("cnl_minority.jsonl", "minority_id")           # Minority Opinions
SUMMARIES = ("cnl_summaries.jsonl", "summary_id")          # Decision Summaries
REPORTS = ("cnl_reports.jsonl", "report_id")               # Council Reports
ARTIFACTS = ("cnl_artifacts.jsonl", "artifact_id")         # Artifact Lineage

ALL_LEDGERS = (COUNCILS, SESSIONS, PARTICIPANTS, DISCUSSIONS, ARGUMENTS, VOTES, CONSENSUS,
               MINORITY, SUMMARIES, REPORTS, ARTIFACTS)


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


def _append_sealed(which, rec: dict) -> None:
    _append(which[0], rec)


# ── Councils ──
def append_council(rec: dict) -> None:
    _append(COUNCILS[0], rec)


def read_councils() -> list[dict]:
    return read_jsonl(COUNCILS[0])


def councils_head() -> dict | None:
    return _head(COUNCILS[0])


def council_exists(council_id: str) -> bool:
    return _exists(COUNCILS[0], COUNCILS[1], council_id)


def get_council(council_id: str) -> dict | None:
    return _get(COUNCILS[0], COUNCILS[1], council_id)


# ── Sessions (event-sourced) ──
def append_session_event(rec: dict) -> None:
    _append(SESSIONS[0], rec)


def read_session_events() -> list[dict]:
    return read_jsonl(SESSIONS[0])


def sessions_head() -> dict | None:
    return _head(SESSIONS[0])


def session_event_exists(session_event_id: str) -> bool:
    return _exists(SESSIONS[0], SESSIONS[1], session_event_id)


def session_events(session_id: str) -> list[dict]:
    return [r for r in read_session_events() if r.get("session_id") == session_id]


def session_ids() -> list[str]:
    return sorted({r.get("session_id") for r in read_session_events() if r.get("session_id")})


# ── Participants ──
def append_participant(rec: dict) -> None:
    _append(PARTICIPANTS[0], rec)


def read_participants() -> list[dict]:
    return read_jsonl(PARTICIPANTS[0])


def participants_head() -> dict | None:
    return _head(PARTICIPANTS[0])


def participant_exists(participant_id: str) -> bool:
    return _exists(PARTICIPANTS[0], PARTICIPANTS[1], participant_id)


def get_participant(participant_id: str) -> dict | None:
    return _get(PARTICIPANTS[0], PARTICIPANTS[1], participant_id)


def session_participants(session_id: str) -> list[dict]:
    return [r for r in read_participants() if r.get("session_id") == session_id]


# ── Discussions ──
def append_discussion(rec: dict) -> None:
    _append(DISCUSSIONS[0], rec)


def read_discussions() -> list[dict]:
    return read_jsonl(DISCUSSIONS[0])


def discussions_head() -> dict | None:
    return _head(DISCUSSIONS[0])


def discussion_exists(discussion_id: str) -> bool:
    return _exists(DISCUSSIONS[0], DISCUSSIONS[1], discussion_id)


def session_discussions(session_id: str) -> list[dict]:
    return [r for r in read_discussions() if r.get("session_id") == session_id]


# ── Arguments ──
def append_argument(rec: dict) -> None:
    _append(ARGUMENTS[0], rec)


def read_arguments() -> list[dict]:
    return read_jsonl(ARGUMENTS[0])


def arguments_head() -> dict | None:
    return _head(ARGUMENTS[0])


def argument_exists(argument_id: str) -> bool:
    return _exists(ARGUMENTS[0], ARGUMENTS[1], argument_id)


def get_argument(argument_id: str) -> dict | None:
    return _get(ARGUMENTS[0], ARGUMENTS[1], argument_id)


def session_arguments(session_id: str) -> list[dict]:
    return [r for r in read_arguments() if r.get("session_id") == session_id]


# ── Votes ──
def append_vote(rec: dict) -> None:
    _append(VOTES[0], rec)


def read_votes() -> list[dict]:
    return read_jsonl(VOTES[0])


def votes_head() -> dict | None:
    return _head(VOTES[0])


def vote_exists(vote_id: str) -> bool:
    return _exists(VOTES[0], VOTES[1], vote_id)


def get_vote(vote_id: str) -> dict | None:
    return _get(VOTES[0], VOTES[1], vote_id)


def topic_votes(session_id: str, topic: str) -> list[dict]:
    return [r for r in read_votes()
            if r.get("session_id") == session_id and r.get("topic") == topic]


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


# ── Minority ──
def append_minority(rec: dict) -> None:
    _append(MINORITY[0], rec)


def read_minority() -> list[dict]:
    return read_jsonl(MINORITY[0])


def minority_head() -> dict | None:
    return _head(MINORITY[0])


def minority_exists(minority_id: str) -> bool:
    return _exists(MINORITY[0], MINORITY[1], minority_id)


def consensus_minority(consensus_id: str) -> list[dict]:
    return [r for r in read_minority() if r.get("consensus_id") == consensus_id]


# ── Summaries ──
def append_summary(rec: dict) -> None:
    _append(SUMMARIES[0], rec)


def read_summaries() -> list[dict]:
    return read_jsonl(SUMMARIES[0])


def summaries_head() -> dict | None:
    return _head(SUMMARIES[0])


def summary_exists(summary_id: str) -> bool:
    return _exists(SUMMARIES[0], SUMMARIES[1], summary_id)


def get_summary(summary_id: str) -> dict | None:
    return _get(SUMMARIES[0], SUMMARIES[1], summary_id)


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
