"""Research Improvement 원장 (P11.10) — 11개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 rimp_ 접두사(Research IMProvement). 각 레코드: id · timestamp · previous_hash · record_hash. 연구
자기개선 루프 — 분석·기록만, 연구/전략/모델 수정·배포 승인·자동 실행·설정 변경 없음. 상위 계층
(P10.2~P10.8, P11.1~P11.9)은 **READ ONLY** — 소스 참조는 파일만 읽고 절대 쓰지 않는다.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (rimp_ 접두사)
REGISTRY = ("rimp_registry.jsonl", "registry_id")            # Improvement Registry
CYCLES = ("rimp_cycles.jsonl", "cycle_id")                   # Research Cycle Records
OBSERVATIONS = ("rimp_observations.jsonl", "observation_id")  # Performance Observations
METRICS = ("rimp_metrics.jsonl", "metric_id")                # Process Metrics
FAILURES = ("rimp_failures.jsonl", "failure_id")             # Failure Patterns
PROPOSALS = ("rimp_proposals.jsonl", "improvement_event_id")  # Improvement Proposals (event-sourced)
LEARNING = ("rimp_learning.jsonl", "learning_id")            # Learning Records
ITERATIONS = ("rimp_iterations.jsonl", "iteration_id")       # Iteration History
REVIEWS = ("rimp_reviews.jsonl", "review_id")                # Improvement Reviews
REPORTS = ("rimp_reports.jsonl", "report_id")                # Improvement Reports
ARTIFACTS = ("rimp_artifacts.jsonl", "artifact_id")          # Artifact Lineage

ALL_LEDGERS = (REGISTRY, CYCLES, OBSERVATIONS, METRICS, FAILURES, PROPOSALS, LEARNING, ITERATIONS,
               REVIEWS, REPORTS, ARTIFACTS)

# ── 상위 소스 원장(READ ONLY) — 소스 참조 검증용. import 결합 없음, 파일만 읽는다. ──
SOURCE_LEDGERS = {
    "research_governance": ("rg_strategy_versions.jsonl", "version_id"),      # P10.2
    "alpha_intelligence": ("ai_signals.jsonl", "signal_hash"),               # P10.3
    "portfolio_research": ("pr_portfolio_versions.jsonl", "version_id"),      # P10.4
    "research_kg": ("kg_entities.jsonl", "entity_id"),                       # P10.5
    "agent_governance": ("arg_agents.jsonl", "event_id"),                    # P10.6
    "decision_intelligence": ("di_frameworks.jsonl", "framework_id"),        # P10.7
    "simulation_environment": ("sim_runs.jsonl", "event_id"),                # P10.8
    "research_agents": ("ragt_reports.jsonl", "report_id"),                  # P11.1
    "research_reviewer": ("rvw_reviews.jsonl", "review_id"),                 # P11.5
    "research_council": ("cnl_consensus.jsonl", "consensus_id"),             # P11.6
    "research_coordinator": ("rco_reports.jsonl", "report_id"),              # P11.7
    "knowledge_sharing": ("ksh_entries.jsonl", "entry_id"),                  # P11.8
    "research_conflict_resolution": ("crf_outcomes.jsonl", "resolution_id"),  # P11.9
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


# ── Cycles ──
def append_cycle(rec: dict) -> None:
    _append(CYCLES[0], rec)


def read_cycles() -> list[dict]:
    return read_jsonl(CYCLES[0])


def cycles_head() -> dict | None:
    return _head(CYCLES[0])


def cycle_exists(cycle_id: str) -> bool:
    return _exists(CYCLES[0], CYCLES[1], cycle_id)


def get_cycle(cycle_id: str) -> dict | None:
    return _get(CYCLES[0], CYCLES[1], cycle_id)


# ── Observations ──
def append_observation(rec: dict) -> None:
    _append(OBSERVATIONS[0], rec)


def read_observations() -> list[dict]:
    return read_jsonl(OBSERVATIONS[0])


def observations_head() -> dict | None:
    return _head(OBSERVATIONS[0])


def observation_exists(observation_id: str) -> bool:
    return _exists(OBSERVATIONS[0], OBSERVATIONS[1], observation_id)


def get_observation(observation_id: str) -> dict | None:
    return _get(OBSERVATIONS[0], OBSERVATIONS[1], observation_id)


def cycle_observations(cycle_id: str) -> list[dict]:
    return [r for r in read_observations() if r.get("cycle_id") == cycle_id]


# ── Metrics ──
def append_metric(rec: dict) -> None:
    _append(METRICS[0], rec)


def read_metrics() -> list[dict]:
    return read_jsonl(METRICS[0])


def metrics_head() -> dict | None:
    return _head(METRICS[0])


def metric_exists(metric_id: str) -> bool:
    return _exists(METRICS[0], METRICS[1], metric_id)


def get_metric(metric_id: str) -> dict | None:
    return _get(METRICS[0], METRICS[1], metric_id)


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


def cycle_failures(cycle_id: str) -> list[dict]:
    return [r for r in read_failures() if r.get("cycle_id") == cycle_id]


# ── Proposals (event-sourced improvements) ──
def append_improvement_event(rec: dict) -> None:
    _append(PROPOSALS[0], rec)


def read_improvement_events() -> list[dict]:
    return read_jsonl(PROPOSALS[0])


def proposals_head() -> dict | None:
    return _head(PROPOSALS[0])


def improvement_event_exists(improvement_event_id: str) -> bool:
    return _exists(PROPOSALS[0], PROPOSALS[1], improvement_event_id)


def improvement_events(improvement_id: str) -> list[dict]:
    return [r for r in read_improvement_events() if r.get("improvement_id") == improvement_id]


def improvement_ids() -> list[str]:
    return sorted({r.get("improvement_id") for r in read_improvement_events()
                   if r.get("improvement_id")})


def cycle_improvements(cycle_id: str) -> list[str]:
    return sorted({r.get("improvement_id") for r in read_improvement_events()
                   if r.get("cycle_id") == cycle_id and r.get("improvement_id")})


# ── Learning ──
def append_learning(rec: dict) -> None:
    _append(LEARNING[0], rec)


def read_learning() -> list[dict]:
    return read_jsonl(LEARNING[0])


def learning_head() -> dict | None:
    return _head(LEARNING[0])


def learning_exists(learning_id: str) -> bool:
    return _exists(LEARNING[0], LEARNING[1], learning_id)


def get_learning(learning_id: str) -> dict | None:
    return _get(LEARNING[0], LEARNING[1], learning_id)


def cycle_learning(cycle_id: str) -> list[dict]:
    return [r for r in read_learning() if r.get("cycle_id") == cycle_id]


# ── Iterations ──
def append_iteration(rec: dict) -> None:
    _append(ITERATIONS[0], rec)


def read_iterations() -> list[dict]:
    return read_jsonl(ITERATIONS[0])


def iterations_head() -> dict | None:
    return _head(ITERATIONS[0])


def iteration_exists(iteration_id: str) -> bool:
    return _exists(ITERATIONS[0], ITERATIONS[1], iteration_id)


def get_iteration(iteration_id: str) -> dict | None:
    return _get(ITERATIONS[0], ITERATIONS[1], iteration_id)


# ── Reviews ──
def append_review(rec: dict) -> None:
    _append(REVIEWS[0], rec)


def read_reviews() -> list[dict]:
    return read_jsonl(REVIEWS[0])


def reviews_head() -> dict | None:
    return _head(REVIEWS[0])


def review_exists(review_id: str) -> bool:
    return _exists(REVIEWS[0], REVIEWS[1], review_id)


def improvement_reviews(improvement_id: str) -> list[dict]:
    return [r for r in read_reviews() if r.get("improvement_id") == improvement_id]


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
