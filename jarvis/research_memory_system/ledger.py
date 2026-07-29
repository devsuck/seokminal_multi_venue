"""Research Memory System 원장 (P11.12) — 12개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 rmem_ 접두사(Research MEMory system) — 기존 rm_ 계층과 구별. 각 레코드: id · timestamp ·
previous_hash · record_hash. 장기 연구 기억 — 저장·검색·분석만, 실행/수정/승인/배포/권한 변경 없음. 상위 계층
(P10.1~P10.8, P11.1~P11.11)은 **READ ONLY** — 소스 참조는 파일만 읽고 절대 쓰지 않는다.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (rmem_ 접두사)
REGISTRY = ("rmem_registry.jsonl", "registry_id")            # Memory Registry (immutable catalog)
MEMORIES = ("rmem_memories.jsonl", "memory_event_id")        # Research Memories (event-sourced)
KNOWLEDGE = ("rmem_knowledge.jsonl", "knowledge_id")         # Knowledge Entries
CONTEXTS = ("rmem_contexts.jsonl", "context_id")             # Research Context Records
EXPERIMENTS = ("rmem_experiments.jsonl", "experiment_memory_id")  # Experiment Memories
FAILURES = ("rmem_failures.jsonl", "failure_memory_id")      # Failure Memories
PATTERNS = ("rmem_patterns.jsonl", "success_pattern_id")     # Success Patterns
ASSOCIATIONS = ("rmem_associations.jsonl", "association_id")  # Memory Associations
SNAPSHOTS = ("rmem_snapshots.jsonl", "snapshot_id")          # Memory Snapshots
REPORTS = ("rmem_reports.jsonl", "report_id")                # Memory Reports
ARTIFACTS = ("rmem_artifacts.jsonl", "artifact_id")          # Artifact Lineage
SEARCHES = ("rmem_searches.jsonl", "search_id")              # 검색 기록(retrieval, 결정적·기록)

ALL_LEDGERS = (REGISTRY, MEMORIES, KNOWLEDGE, CONTEXTS, EXPERIMENTS, FAILURES, PATTERNS,
               ASSOCIATIONS, SNAPSHOTS, REPORTS, ARTIFACTS, SEARCHES)

# ── 상위 소스 원장(READ ONLY) — 소스 참조 검증용. import 결합 없음, 파일만 읽는다. ──
SOURCE_LEDGERS = {
    "research_data": ("datasets.jsonl", "dataset_hash"),                     # P10.1
    "research_governance": ("rg_strategy_versions.jsonl", "version_id"),      # P10.2
    "alpha_intelligence": ("ai_signals.jsonl", "signal_hash"),               # P10.3
    "portfolio_research": ("pr_portfolio_versions.jsonl", "version_id"),      # P10.4
    "research_kg": ("kg_entities.jsonl", "entity_id"),                       # P10.5
    "agent_governance": ("arg_agents.jsonl", "event_id"),                    # P10.6
    "decision_intelligence": ("di_frameworks.jsonl", "framework_id"),        # P10.7
    "simulation_environment": ("sim_runs.jsonl", "event_id"),                # P10.8
    "research_agents": ("ragt_reports.jsonl", "report_id"),                  # P11.1
    "research_task_planner": ("rtp_tasks.jsonl", "task_id"),                 # P11.2
    "research_literature": ("rli_papers.jsonl", "paper_id"),                 # P11.3
    "experiment_manager": ("exm_experiments.jsonl", "event_id"),             # P11.4
    "research_reviewer": ("rvw_reviews.jsonl", "review_id"),                 # P11.5
    "research_council": ("cnl_consensus.jsonl", "consensus_id"),             # P11.6
    "research_coordinator": ("rco_reports.jsonl", "report_id"),              # P11.7
    "knowledge_sharing": ("ksh_entries.jsonl", "entry_id"),                  # P11.8
    "research_conflict_resolution": ("crf_outcomes.jsonl", "resolution_id"),  # P11.9
    "research_improvement": ("rimp_registry.jsonl", "registry_id"),          # P11.10
    "research_event_bus": ("reb_events.jsonl", "event_lifecycle_id"),        # P11.11
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


# ── Registry (catalog) ──
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


def catalog_by_memory(memory_id: str) -> dict | None:
    for r in read_registry():
        if r.get("memory_id") == memory_id:
            return r
    return None


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


# ── Knowledge ──
def append_knowledge(rec: dict) -> None:
    _append(KNOWLEDGE[0], rec)


def read_knowledge() -> list[dict]:
    return read_jsonl(KNOWLEDGE[0])


def knowledge_head() -> dict | None:
    return _head(KNOWLEDGE[0])


def knowledge_exists(knowledge_id: str) -> bool:
    return _exists(KNOWLEDGE[0], KNOWLEDGE[1], knowledge_id)


def get_knowledge(knowledge_id: str) -> dict | None:
    return _get(KNOWLEDGE[0], KNOWLEDGE[1], knowledge_id)


# ── Contexts ──
def append_context(rec: dict) -> None:
    _append(CONTEXTS[0], rec)


def read_contexts() -> list[dict]:
    return read_jsonl(CONTEXTS[0])


def contexts_head() -> dict | None:
    return _head(CONTEXTS[0])


def context_exists(context_id: str) -> bool:
    return _exists(CONTEXTS[0], CONTEXTS[1], context_id)


def get_context(context_id: str) -> dict | None:
    return _get(CONTEXTS[0], CONTEXTS[1], context_id)


def memory_contexts(memory_id: str) -> list[dict]:
    return [r for r in read_contexts() if r.get("memory_id") == memory_id]


# ── Experiments ──
def append_experiment(rec: dict) -> None:
    _append(EXPERIMENTS[0], rec)


def read_experiments() -> list[dict]:
    return read_jsonl(EXPERIMENTS[0])


def experiments_head() -> dict | None:
    return _head(EXPERIMENTS[0])


def experiment_exists(experiment_memory_id: str) -> bool:
    return _exists(EXPERIMENTS[0], EXPERIMENTS[1], experiment_memory_id)


def get_experiment(experiment_memory_id: str) -> dict | None:
    return _get(EXPERIMENTS[0], EXPERIMENTS[1], experiment_memory_id)


# ── Failures ──
def append_failure(rec: dict) -> None:
    _append(FAILURES[0], rec)


def read_failures() -> list[dict]:
    return read_jsonl(FAILURES[0])


def failures_head() -> dict | None:
    return _head(FAILURES[0])


def failure_exists(failure_memory_id: str) -> bool:
    return _exists(FAILURES[0], FAILURES[1], failure_memory_id)


def get_failure(failure_memory_id: str) -> dict | None:
    return _get(FAILURES[0], FAILURES[1], failure_memory_id)


# ── Patterns ──
def append_pattern(rec: dict) -> None:
    _append(PATTERNS[0], rec)


def read_patterns() -> list[dict]:
    return read_jsonl(PATTERNS[0])


def patterns_head() -> dict | None:
    return _head(PATTERNS[0])


def pattern_exists(success_pattern_id: str) -> bool:
    return _exists(PATTERNS[0], PATTERNS[1], success_pattern_id)


def get_pattern(success_pattern_id: str) -> dict | None:
    return _get(PATTERNS[0], PATTERNS[1], success_pattern_id)


# ── Associations ──
def append_association(rec: dict) -> None:
    _append(ASSOCIATIONS[0], rec)


def read_associations() -> list[dict]:
    return read_jsonl(ASSOCIATIONS[0])


def associations_head() -> dict | None:
    return _head(ASSOCIATIONS[0])


def association_exists(association_id: str) -> bool:
    return _exists(ASSOCIATIONS[0], ASSOCIATIONS[1], association_id)


def memory_associations(memory_id: str) -> list[dict]:
    return [r for r in read_associations()
            if r.get("memory_a") == memory_id or r.get("memory_b") == memory_id]


# ── Snapshots ──
def append_snapshot(rec: dict) -> None:
    _append(SNAPSHOTS[0], rec)


def read_snapshots() -> list[dict]:
    return read_jsonl(SNAPSHOTS[0])


def snapshots_head() -> dict | None:
    return _head(SNAPSHOTS[0])


def snapshot_exists(snapshot_id: str) -> bool:
    return _exists(SNAPSHOTS[0], SNAPSHOTS[1], snapshot_id)


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


# ── Searches (recorded retrieval) ──
def append_search(rec: dict) -> None:
    _append(SEARCHES[0], rec)


def read_searches() -> list[dict]:
    return read_jsonl(SEARCHES[0])


def searches_head() -> dict | None:
    return _head(SEARCHES[0])


def search_exists(search_id: str) -> bool:
    return _exists(SEARCHES[0], SEARCHES[1], search_id)
