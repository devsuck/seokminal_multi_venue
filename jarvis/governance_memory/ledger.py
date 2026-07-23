"""Governance Memory 원장 (P10.21) — 8개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 gm_ 접두사. 각 레코드: id · timestamp · previous_hash · record_hash. 재사용 지식 저장·조회만 —
정책/config 변경·승인·배포·실행 없음. 상위 레이어(P9.8~P10.20)는 **READ ONLY**. (gm_ ≠ mg_ Model Governance.)
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (gm_ 접두사)
ENTRIES = ("gm_entries.jsonl", "entry_id")
EXPERIENCES = ("gm_experiences.jsonl", "experience_id")
LESSONS = ("gm_lessons.jsonl", "lesson_id")
RESOLUTION_HISTORY = ("gm_resolution_history.jsonl", "resolution_id")
LINKS = ("gm_links.jsonl", "link_id")
SNAPSHOTS = ("gm_snapshots.jsonl", "snapshot_id")
REPORTS = ("gm_reports.jsonl", "report_id")
ARTIFACTS = ("gm_artifacts.jsonl", "artifact_id")

ALL_LEDGERS = (ENTRIES, EXPERIENCES, LESSONS, RESOLUTION_HISTORY, LINKS, SNAPSHOTS, REPORTS,
               ARTIFACTS)

# 상위 레이어 물리 원장(READ ONLY 데이터 소스) — import 결합 없음, 파일만 읽는다.
# 논리 레이어명 -> (대표 원장 파일명, id 필드)
SOURCE_LEDGERS = {
    "data_governance": ("dg_datasets.jsonl", "dataset_id"),
    "model_governance": ("mg_models.jsonl", "model_id"),
    "access_governance": ("ag_operators.jsonl", "identity_hash"),
    "research_data": ("datasets.jsonl", "dataset_id"),
    "research_governance": ("rg_strategies.jsonl", "strategy_id"),
    "alpha_intelligence": ("ai_signals.jsonl", "signal_id"),
    "portfolio_research": ("pr_portfolios.jsonl", "portfolio_id"),
    "research_kg": ("kg_entities.jsonl", "entity_id"),
    "agent_governance": ("arg_agents.jsonl", "agent_id"),
    "decision_intelligence": ("di_candidates.jsonl", "candidate_id"),
    "simulation_environment": ("sim_scenarios.jsonl", "scenario_id"),
    "research_validation": ("rv_validations.jsonl", "event_id"),
    "research_observatory": ("ob_snapshots.jsonl", "event_id"),
    "causal_intelligence": ("ci_hypotheses.jsonl", "event_id"),
    "meta_intelligence": ("mi_patterns.jsonl", "event_id"),
    "self_improvement_intelligence": ("si_opportunities.jsonl", "event_id"),
    "research_memory": ("rm_memories.jsonl", "event_id"),
    "research_planning": ("rp_opportunities.jsonl", "event_id"),
    "research_evolution": ("ev_research_objects.jsonl", "object_id"),
    "research_os": ("ros_layers.jsonl", "event_id"),
    "research_orchestration": ("or_workflows.jsonl", "event_id"),
    "research_observability": ("mh_health_records.jsonl", "health_id"),
    "research_compliance": ("rc_rules.jsonl", "rule_id"),
    "governance_feedback": ("gf_feedback.jsonl", "feedback_id"),
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


def source_count(layer: str) -> int:
    spec = SOURCE_LEDGERS.get(layer)
    if not spec:
        return 0
    return len(read_source(spec[0]))


# ── Entries (불변) ──
def append_entry(rec: dict) -> None:
    _append(ENTRIES[0], rec)


def read_entries() -> list[dict]:
    return read_jsonl(ENTRIES[0])


def entries_head() -> dict | None:
    return _head(ENTRIES[0])


def entry_exists(entry_id: str) -> bool:
    return _exists(ENTRIES[0], ENTRIES[1], entry_id)


def get_entry(entry_id: str) -> dict | None:
    for r in read_entries():
        if r.get("entry_id") == entry_id:
            return r
    return None


def entries_by_category(category: str) -> list[dict]:
    return [r for r in read_entries() if r.get("category") == category]


# ── Experiences (불변) ──
def append_experience(rec: dict) -> None:
    _append(EXPERIENCES[0], rec)


def read_experiences() -> list[dict]:
    return read_jsonl(EXPERIENCES[0])


def experiences_head() -> dict | None:
    return _head(EXPERIENCES[0])


def experience_exists(experience_id: str) -> bool:
    return _exists(EXPERIENCES[0], EXPERIENCES[1], experience_id)


def get_experience(experience_id: str) -> dict | None:
    for r in read_experiences():
        if r.get("experience_id") == experience_id:
            return r
    return None


# ── Lessons (불변) ──
def append_lesson(rec: dict) -> None:
    _append(LESSONS[0], rec)


def read_lessons() -> list[dict]:
    return read_jsonl(LESSONS[0])


def lessons_head() -> dict | None:
    return _head(LESSONS[0])


def lesson_exists(lesson_id: str) -> bool:
    return _exists(LESSONS[0], LESSONS[1], lesson_id)


def get_lesson(lesson_id: str) -> dict | None:
    for r in read_lessons():
        if r.get("lesson_id") == lesson_id:
            return r
    return None


# ── Resolution History (불변) ──
def append_resolution(rec: dict) -> None:
    _append(RESOLUTION_HISTORY[0], rec)


def read_resolutions() -> list[dict]:
    return read_jsonl(RESOLUTION_HISTORY[0])


def resolutions_head() -> dict | None:
    return _head(RESOLUTION_HISTORY[0])


def resolution_exists(resolution_id: str) -> bool:
    return _exists(RESOLUTION_HISTORY[0], RESOLUTION_HISTORY[1], resolution_id)


# ── Links ──
def append_link(rec: dict) -> None:
    _append(LINKS[0], rec)


def read_links() -> list[dict]:
    return read_jsonl(LINKS[0])


def links_head() -> dict | None:
    return _head(LINKS[0])


def link_exists(link_id: str) -> bool:
    return _exists(LINKS[0], LINKS[1], link_id)


# ── Snapshots (불변) ──
def append_snapshot(rec: dict) -> None:
    _append(SNAPSHOTS[0], rec)


def read_snapshots() -> list[dict]:
    return read_jsonl(SNAPSHOTS[0])


def snapshots_head() -> dict | None:
    return _head(SNAPSHOTS[0])


def snapshot_exists(snapshot_id: str) -> bool:
    return _exists(SNAPSHOTS[0], SNAPSHOTS[1], snapshot_id)


def get_snapshot(snapshot_id: str) -> dict | None:
    for r in read_snapshots():
        if r.get("snapshot_id") == snapshot_id:
            return r
    return None


# ── Reports ──
def append_report(rec: dict) -> None:
    _append(REPORTS[0], rec)


def read_reports() -> list[dict]:
    return read_jsonl(REPORTS[0])


def reports_head() -> dict | None:
    return _head(REPORTS[0])


def report_exists(report_id: str) -> bool:
    return _exists(REPORTS[0], REPORTS[1], report_id)


# ── Artifacts (계보) ──
def append_artifact(rec: dict) -> None:
    _append(ARTIFACTS[0], rec)


def read_artifacts() -> list[dict]:
    return read_jsonl(ARTIFACTS[0])


def artifacts_head() -> dict | None:
    return _head(ARTIFACTS[0])


def artifact_exists(artifact_id: str) -> bool:
    return _exists(ARTIFACTS[0], ARTIFACTS[1], artifact_id)
