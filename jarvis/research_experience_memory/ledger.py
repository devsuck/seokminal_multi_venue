"""Research Memory & Experience 원장 (P12.7) — 8개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 rxm_ 접두사(Research eXperience Memory) — 기존 rm_/rmem_ 계층과 구별. 각 레코드: id · timestamp ·
previous_hash · record_hash. 기억·기록·검색만 — 실행 능력 없음. 상위 계층(P10.2~P10.8, P12.1~P12.6)은 **READ ONLY**.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (rxm_ 접두사)
MEMORIES = ("rxm_memories.jsonl", "memory_event_id")         # Memory Registry(event-sourced)
EXPERIENCES = ("rxm_experiences.jsonl", "experience_id")     # Experience Records
FAILURES = ("rxm_failures.jsonl", "failure_id")             # Failure Memory
PATTERNS = ("rxm_patterns.jsonl", "pattern_id")             # Success Patterns
EPISODES = ("rxm_episodes.jsonl", "episode_id")             # Research Episodes
RETRIEVALS = ("rxm_retrievals.jsonl", "retrieval_id")       # Retrieval Index
SUMMARIES = ("rxm_summaries.jsonl", "summary_id")           # Memory Summary
ARTIFACTS = ("rxm_artifacts.jsonl", "artifact_id")          # Artifact Lineage

ALL_LEDGERS = (MEMORIES, EXPERIENCES, FAILURES, PATTERNS, EPISODES, RETRIEVALS, SUMMARIES,
               ARTIFACTS)

# ── 상위 소스 원장(READ ONLY) — 소스 참조 검증용. import 결합 없음, 파일만 읽는다. ──
SOURCE_LEDGERS = {
    "research_governance": ("rg_strategy_versions.jsonl", "version_id"),      # P10.2
    "alpha_intelligence": ("ai_signals.jsonl", "signal_hash"),               # P10.3
    "portfolio_research": ("pr_portfolio_versions.jsonl", "version_id"),      # P10.4
    "research_kg": ("kg_entities.jsonl", "entity_id"),                       # P10.5
    "agent_governance": ("arg_agents.jsonl", "event_id"),                    # P10.6
    "decision_intelligence": ("di_frameworks.jsonl", "framework_id"),        # P10.7
    "simulation_environment": ("sim_runs.jsonl", "event_id"),                # P10.8
    "autonomous_research_pipeline": ("arp_cycles.jsonl", "cycle_id"),        # P12.1
    "autonomous_experiment_scheduler": ("aes_schedules.jsonl", "schedule_event_id"),  # P12.2
    "research_agent_coordinator": ("rac_ownership.jsonl", "ownership_event_id"),  # P12.3
    "adaptive_research_loop": ("arl_proposals.jsonl", "proposal_event_id"),  # P12.4
    "autonomous_research_evaluation": ("are_registry.jsonl", "evaluation_event_id"),  # P12.5
    "research_optimization_engine": ("roe_studies.jsonl", "study_event_id"),  # P12.6
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


# ── Memories (event-sourced) ──
def append_memory_event(rec: dict) -> None:
    _append(MEMORIES[0], rec)


def read_memory_events() -> list[dict]:
    return read_jsonl(MEMORIES[0])


def memories_head() -> dict | None:
    return _head(MEMORIES[0])


def memory_event_exists(memory_event_id: str) -> bool:
    return _exists(MEMORIES[0], MEMORIES[1], memory_event_id)


def memory_events(memory_id: str) -> list[dict]:
    return [r for r in read_memory_events() if r.get("memory_id") == memory_id]


def memory_ids() -> list[str]:
    return sorted({r.get("memory_id") for r in read_memory_events() if r.get("memory_id")})


def type_memories(memory_type: str) -> list[str]:
    return sorted({r.get("memory_id") for r in read_memory_events()
                   if r.get("memory_type") == memory_type and r.get("memory_id")})


# ── Experiences ──
def append_experience(rec: dict) -> None:
    _append(EXPERIENCES[0], rec)


def read_experiences() -> list[dict]:
    return read_jsonl(EXPERIENCES[0])


def experiences_head() -> dict | None:
    return _head(EXPERIENCES[0])


def experience_exists(experience_id: str) -> bool:
    return _exists(EXPERIENCES[0], EXPERIENCES[1], experience_id)


def get_experience(experience_id: str) -> dict | None:
    return _get(EXPERIENCES[0], EXPERIENCES[1], experience_id)


def memory_experiences(memory_id: str) -> list[dict]:
    return [r for r in read_experiences() if r.get("memory_id") == memory_id]


# ── Failures ──
def append_failure(rec: dict) -> None:
    _append(FAILURES[0], rec)


def read_failures() -> list[dict]:
    return read_jsonl(FAILURES[0])


def failures_head() -> dict | None:
    return _head(FAILURES[0])


def failure_exists(failure_id: str) -> bool:
    return _exists(FAILURES[0], FAILURES[1], failure_id)


def get_failure(failure_id: str) -> dict | None:
    return _get(FAILURES[0], FAILURES[1], failure_id)


# ── Patterns ──
def append_pattern(rec: dict) -> None:
    _append(PATTERNS[0], rec)


def read_patterns() -> list[dict]:
    return read_jsonl(PATTERNS[0])


def patterns_head() -> dict | None:
    return _head(PATTERNS[0])


def pattern_exists(pattern_id: str) -> bool:
    return _exists(PATTERNS[0], PATTERNS[1], pattern_id)


def get_pattern(pattern_id: str) -> dict | None:
    return _get(PATTERNS[0], PATTERNS[1], pattern_id)


# ── Episodes ──
def append_episode(rec: dict) -> None:
    _append(EPISODES[0], rec)


def read_episodes() -> list[dict]:
    return read_jsonl(EPISODES[0])


def episodes_head() -> dict | None:
    return _head(EPISODES[0])


def episode_exists(episode_id: str) -> bool:
    return _exists(EPISODES[0], EPISODES[1], episode_id)


def get_episode(episode_id: str) -> dict | None:
    return _get(EPISODES[0], EPISODES[1], episode_id)


# ── Retrievals ──
def append_retrieval(rec: dict) -> None:
    _append(RETRIEVALS[0], rec)


def read_retrievals() -> list[dict]:
    return read_jsonl(RETRIEVALS[0])


def retrievals_head() -> dict | None:
    return _head(RETRIEVALS[0])


def retrieval_exists(retrieval_id: str) -> bool:
    return _exists(RETRIEVALS[0], RETRIEVALS[1], retrieval_id)


# ── Summaries ──
def append_summary(rec: dict) -> None:
    _append(SUMMARIES[0], rec)


def read_summaries() -> list[dict]:
    return read_jsonl(SUMMARIES[0])


def summaries_head() -> dict | None:
    return _head(SUMMARIES[0])


def summary_exists(summary_id: str) -> bool:
    return _exists(SUMMARIES[0], SUMMARIES[1], summary_id)


# ── Artifacts ──
def append_artifact(rec: dict) -> None:
    _append(ARTIFACTS[0], rec)


def read_artifacts() -> list[dict]:
    return read_jsonl(ARTIFACTS[0])


def artifacts_head() -> dict | None:
    return _head(ARTIFACTS[0])


def artifact_exists(artifact_id: str) -> bool:
    return _exists(ARTIFACTS[0], ARTIFACTS[1], artifact_id)
