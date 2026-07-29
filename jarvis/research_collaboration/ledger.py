"""Research Collaboration 원장 (P19) — 10개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 rcol_ 접두사(Research COLlaboration). 각 레코드: id · timestamp · previous_hash · record_hash · metadata.
협업·조정·기록만 — 실행·자동승인 없음. P10.6 agent_governance 포함 상위/통합 계층은 **READ ONLY** — 파일만 읽는다.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 계층 소유 원장 (rcol_ 접두사)
COLLABORATIONS = ("rcol_collaborations.jsonl", "collab_event_id")           # 협업 생애주기(ES)
PARTICIPANTS = ("rcol_participants.jsonl", "participation_event_id")        # 참여 생애주기(ES)
MESSAGES = ("rcol_messages.jsonl", "message_id")                           # 메시지(불변)
PROPOSALS = ("rcol_proposals.jsonl", "proposal_event_id")                  # 제안 생애주기(ES)
REVIEWS = ("rcol_reviews.jsonl", "review_id")                             # 동료 검토(불변)
CONSENSUS = ("rcol_consensus.jsonl", "consensus_event_id")                # 합의 생애주기(ES)
CONFLICTS = ("rcol_conflicts.jsonl", "conflict_event_id")                 # 갈등 생애주기(ES)
HUMAN_REVIEWS = ("rcol_human_reviews.jsonl", "human_review_event_id")     # 사람 검토 생애주기(ES)
REPORTS = ("rcol_reports.jsonl", "report_id")                            # 협업 리포트
ARTIFACTS = ("rcol_artifacts.jsonl", "artifact_id")                      # 아티팩트 계보

ALL_LEDGERS = (COLLABORATIONS, PARTICIPANTS, MESSAGES, PROPOSALS, REVIEWS, CONSENSUS, CONFLICTS,
               HUMAN_REVIEWS, REPORTS, ARTIFACTS)

# ── 통합 소스(READ ONLY) — import 결합 없음, 파일만 읽는다. ──
SOURCE_LAYERS = {
    "knowledge_graph": ("kg_entities.jsonl", "event_id"),           # P10.5
    "agent_governance": ("arg_agents.jsonl", "event_id"),           # P10.6 (READ ONLY)
    "decision_intelligence": ("di_candidates.jsonl", "event_id"),   # P10.7
    "simulation": ("sim_scenarios.jsonl", "event_id"),              # P10.8
    "observability": ("obs_pipeline_health.jsonl", "health_event_id"),  # P17
    "research_operations": ("ro_workflows.jsonl", "workflow_event_id"),  # P18
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


# ── 통합 소스 READ ONLY ──
def source_count(layer: str) -> int:
    spec = SOURCE_LAYERS.get(layer)
    if not spec:
        return 0
    return len(read_jsonl(spec[0]))


def source_ref_exists(layer: str, ref: str) -> bool:
    spec = SOURCE_LAYERS.get(layer)
    if not spec:
        return False
    p = state_path(spec[0])
    if not os.path.exists(p):
        return False
    return any(r.get(spec[1]) == ref for r in read_jsonl(spec[0]))


# ── 일반 helper 팩토리 ──
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


append_collab_event, read_collab_events, collab_head, collab_event_exists = _readers(COLLABORATIONS)
append_participation, read_participations, participation_head, participation_exists = _readers(PARTICIPANTS)
append_message, read_messages, messages_head, message_exists = _readers(MESSAGES)
append_proposal_event, read_proposal_events, proposals_head, proposal_event_exists = _readers(PROPOSALS)
append_review, read_reviews, reviews_head, review_exists = _readers(REVIEWS)
append_consensus_event, read_consensus_events, consensus_head, consensus_event_exists = _readers(CONSENSUS)
append_conflict_event, read_conflict_events, conflicts_head, conflict_event_exists = _readers(CONFLICTS)
append_human_review_event, read_human_review_events, human_reviews_head, human_review_event_exists = _readers(HUMAN_REVIEWS)
append_report, read_reports, reports_head, report_exists = _readers(REPORTS)
append_artifact, read_artifacts, artifacts_head, artifact_exists = _readers(ARTIFACTS)


# ── 그룹 조회 ──
def collab_events(cid: str) -> list[dict]:
    return [r for r in read_collab_events() if r.get("collaboration_id") == cid]


def collaboration_ids() -> list[str]:
    return sorted({r.get("collaboration_id") for r in read_collab_events()
                   if r.get("collaboration_id")})


def participation_events(pid: str) -> list[dict]:
    return [r for r in read_participations() if r.get("participant_id") == pid]


def collab_participants(cid: str) -> list[str]:
    return sorted({r.get("participant_id") for r in read_participations()
                   if r.get("collaboration_id") == cid and r.get("participant_id")})


def collab_messages(cid: str) -> list[dict]:
    return [r for r in read_messages() if r.get("collaboration_id") == cid]


def proposal_events(pid: str) -> list[dict]:
    return [r for r in read_proposal_events() if r.get("proposal_id") == pid]


def collab_proposals(cid: str) -> list[str]:
    return sorted({r.get("proposal_id") for r in read_proposal_events()
                   if r.get("collaboration_id") == cid and r.get("proposal_id")})


def collab_reviews(cid: str) -> list[dict]:
    return [r for r in read_reviews() if r.get("collaboration_id") == cid]


def consensus_events(cons: str) -> list[dict]:
    return [r for r in read_consensus_events() if r.get("consensus_id") == cons]


def collab_consensus(cid: str) -> list[str]:
    return sorted({r.get("consensus_id") for r in read_consensus_events()
                   if r.get("collaboration_id") == cid and r.get("consensus_id")})


def conflict_events(conf: str) -> list[dict]:
    return [r for r in read_conflict_events() if r.get("conflict_id") == conf]


def collab_conflicts(cid: str) -> list[str]:
    return sorted({r.get("conflict_id") for r in read_conflict_events()
                   if r.get("collaboration_id") == cid and r.get("conflict_id")})


def human_review_events(hr: str) -> list[dict]:
    return [r for r in read_human_review_events() if r.get("human_review_id") == hr]


def collab_human_reviews(cid: str) -> list[str]:
    return sorted({r.get("human_review_id") for r in read_human_review_events()
                   if r.get("collaboration_id") == cid and r.get("human_review_id")})
