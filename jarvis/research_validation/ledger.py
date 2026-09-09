"""Research Validation 원장 (P10.9) — 8개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 rv_ 접두사. 각 레코드: id · previous_hash · record_hash · timestamp. 연구 품질 평가 기록만 —
실행/거래/배포 없음. 상위 레이어(P10.2~P10.8) 원장은 **READ ONLY** 로만 읽는다.
"""
from __future__ import annotations


from jarvis.config import state_path
from jarvis.ledger_io import append as _append, read_jsonl, head as _head, exists as _exists

# (파일명, id 필드) — 본 레이어 소유 원장 (rv_ 접두사)
VALIDATIONS = ("rv_validations.jsonl", "event_id")      # 이벤트 소싱
SESSIONS = ("rv_sessions.jsonl", "session_id")
CHECKLISTS = ("rv_checklists.jsonl", "checklist_id")
EVIDENCE = ("rv_evidence.jsonl", "evidence_id")
REPLAY_REPORTS = ("rv_replay_reports.jsonl", "replay_id")
LINEAGE_REPORTS = ("rv_lineage_reports.jsonl", "lineage_report_id")
SCORES = ("rv_scores.jsonl", "score_id")
ARTIFACTS = ("rv_artifacts.jsonl", "artifact_id")

ALL_LEDGERS = (VALIDATIONS, SESSIONS, CHECKLISTS, EVIDENCE, REPLAY_REPORTS, LINEAGE_REPORTS,
               SCORES, ARTIFACTS)

# 상위 레이어 물리 원장(READ ONLY 데이터 소스) — import 결합 없음, 파일만 읽는다.
SOURCE_LEDGERS = {
    "research_governance": ("rg_strategies.jsonl", "rg_artifacts.jsonl"),
    "alpha_intelligence": ("ai_signals.jsonl", "ai_artifacts.jsonl"),
    "portfolio_research": ("pr_portfolios.jsonl", "pr_artifacts.jsonl"),
    "research_kg": ("kg_entities.jsonl", "kg_lineage_edges.jsonl"),
    "agent_governance": ("arg_agents.jsonl", "arg_artifacts.jsonl"),
    "decision_intelligence": ("di_candidates.jsonl", "di_artifacts.jsonl"),
    "simulation_environment": ("sim_scenarios.jsonl", "sim_artifacts.jsonl"),
}

# ── 상위 레이어 READ ONLY 소스 ──


def read_source(filename: str) -> list[dict]:
    """상위 레이어 원장을 읽기 전용으로 로드. 절대 쓰지 않는다."""
    return read_jsonl(filename, resolver=state_path)


# ── Validations (event-sourced) ──


def append_validation_event(rec: dict) -> None:
    _append(VALIDATIONS[0], rec, resolver=state_path)


def read_validation_events() -> list[dict]:
    return read_jsonl(VALIDATIONS[0], resolver=state_path)


def validations_head() -> dict | None:
    return _head(VALIDATIONS[0], resolver=state_path)


def validation_event_exists(event_id: str) -> bool:
    return _exists(VALIDATIONS[0], VALIDATIONS[1], event_id, resolver=state_path)


def validation_events_for(validation_id: str) -> list[dict]:
    return [r for r in read_validation_events() if r.get("validation_id") == validation_id]


def distinct_validations() -> list[dict]:
    out: dict = {}
    for r in read_validation_events():
        vid = r.get("validation_id")
        if vid not in out:
            out[vid] = r
    return list(out.values())


# ── Sessions ──


def append_session(rec: dict) -> None:
    _append(SESSIONS[0], rec, resolver=state_path)


def read_sessions() -> list[dict]:
    return read_jsonl(SESSIONS[0], resolver=state_path)


def sessions_head() -> dict | None:
    return _head(SESSIONS[0], resolver=state_path)


def session_exists(session_id: str) -> bool:
    return _exists(SESSIONS[0], SESSIONS[1], session_id, resolver=state_path)


# ── Checklists ──


def append_checklist(rec: dict) -> None:
    _append(CHECKLISTS[0], rec, resolver=state_path)


def read_checklists() -> list[dict]:
    return read_jsonl(CHECKLISTS[0], resolver=state_path)


def checklists_head() -> dict | None:
    return _head(CHECKLISTS[0], resolver=state_path)


def checklist_exists(checklist_id: str) -> bool:
    return _exists(CHECKLISTS[0], CHECKLISTS[1], checklist_id, resolver=state_path)


# ── Evidence ──


def append_evidence(rec: dict) -> None:
    _append(EVIDENCE[0], rec, resolver=state_path)


def read_evidence() -> list[dict]:
    return read_jsonl(EVIDENCE[0], resolver=state_path)


def evidence_head() -> dict | None:
    return _head(EVIDENCE[0], resolver=state_path)


def evidence_exists(evidence_id: str) -> bool:
    return _exists(EVIDENCE[0], EVIDENCE[1], evidence_id, resolver=state_path)


# ── Replay reports ──


def append_replay(rec: dict) -> None:
    _append(REPLAY_REPORTS[0], rec, resolver=state_path)


def read_replay_reports() -> list[dict]:
    return read_jsonl(REPLAY_REPORTS[0], resolver=state_path)


def replay_head() -> dict | None:
    return _head(REPLAY_REPORTS[0], resolver=state_path)


def replay_exists(replay_id: str) -> bool:
    return _exists(REPLAY_REPORTS[0], REPLAY_REPORTS[1], replay_id, resolver=state_path)


# ── Lineage reports ──


def append_lineage_report(rec: dict) -> None:
    _append(LINEAGE_REPORTS[0], rec, resolver=state_path)


def read_lineage_reports() -> list[dict]:
    return read_jsonl(LINEAGE_REPORTS[0], resolver=state_path)


def lineage_head() -> dict | None:
    return _head(LINEAGE_REPORTS[0], resolver=state_path)


def lineage_report_exists(lineage_report_id: str) -> bool:
    return _exists(LINEAGE_REPORTS[0], LINEAGE_REPORTS[1], lineage_report_id, resolver=state_path)


# ── Scores ──


def append_score(rec: dict) -> None:
    _append(SCORES[0], rec, resolver=state_path)


def read_scores() -> list[dict]:
    return read_jsonl(SCORES[0], resolver=state_path)


def scores_head() -> dict | None:
    return _head(SCORES[0], resolver=state_path)


def score_exists(score_id: str) -> bool:
    return _exists(SCORES[0], SCORES[1], score_id, resolver=state_path)


# ── Artifacts ──


def append_artifact(rec: dict) -> None:
    _append(ARTIFACTS[0], rec, resolver=state_path)


def read_artifacts() -> list[dict]:
    return read_jsonl(ARTIFACTS[0], resolver=state_path)


def artifacts_head() -> dict | None:
    return _head(ARTIFACTS[0], resolver=state_path)


def artifact_exists(artifact_id: str) -> bool:
    return _exists(ARTIFACTS[0], ARTIFACTS[1], artifact_id, resolver=state_path)
