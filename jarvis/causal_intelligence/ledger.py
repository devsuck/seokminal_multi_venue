"""Research Causal Intelligence 원장 (P10.11) — 8개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 ci_ 접두사. 각 레코드: id · timestamp · previous_hash · record_hash. 인과 연구 기록만 —
실행/거래/배포 없음. 상위 레이어(P10.2~P10.8) 원장은 **READ ONLY** 로만 읽는다.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (ci_ 접두사)
VARIABLES = ("ci_variables.jsonl", "variable_id")
HYPOTHESES = ("ci_hypotheses.jsonl", "event_id")        # 이벤트 소싱
RELATIONSHIPS = ("ci_relationships.jsonl", "study_id")
EXPERIMENTS = ("ci_experiments.jsonl", "event_id")      # 이벤트 소싱
EVIDENCES = ("ci_evidences.jsonl", "evidence_id")
GRAPHS = ("ci_graphs.jsonl", "event_id")                # 이벤트 소싱
REPORTS = ("ci_reports.jsonl", "report_id")
ARTIFACTS = ("ci_artifacts.jsonl", "artifact_id")

ALL_LEDGERS = (VARIABLES, HYPOTHESES, RELATIONSHIPS, EXPERIMENTS, EVIDENCES, GRAPHS, REPORTS,
               ARTIFACTS)

# 상위 레이어 물리 원장(READ ONLY 데이터 소스) — import 결합 없음, 파일만 읽는다.
SOURCE_LEDGERS = {
    "research_governance": ("rg_strategies.jsonl", "strategy_id"),
    "alpha_intelligence": ("ai_signals.jsonl", "signal_id"),
    "portfolio_research": ("pr_portfolios.jsonl", "portfolio_id"),
    "research_kg": ("kg_entities.jsonl", "entity_id"),
    "decision_intelligence": ("di_candidates.jsonl", "candidate_id"),
    "simulation_environment": ("sim_scenarios.jsonl", "scenario_id"),
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


# ── Variables ──
def append_variable(rec: dict) -> None:
    _append(VARIABLES[0], rec)


def read_variables() -> list[dict]:
    return read_jsonl(VARIABLES[0])


def variables_head() -> dict | None:
    return _head(VARIABLES[0])


def variable_exists(variable_id: str) -> bool:
    return _exists(VARIABLES[0], VARIABLES[1], variable_id)


# ── Hypotheses (event-sourced) ──
def append_hypothesis_event(rec: dict) -> None:
    _append(HYPOTHESES[0], rec)


def read_hypothesis_events() -> list[dict]:
    return read_jsonl(HYPOTHESES[0])


def hypotheses_head() -> dict | None:
    return _head(HYPOTHESES[0])


def hypothesis_event_exists(event_id: str) -> bool:
    return _exists(HYPOTHESES[0], HYPOTHESES[1], event_id)


def hypothesis_events_for(hypothesis_id: str) -> list[dict]:
    return [r for r in read_hypothesis_events() if r.get("hypothesis_id") == hypothesis_id]


def distinct_hypotheses() -> list[dict]:
    out: dict = {}
    for r in read_hypothesis_events():
        hid = r.get("hypothesis_id")
        if hid not in out:
            out[hid] = r
    return list(out.values())


# ── Relationships ──
def append_relationship(rec: dict) -> None:
    _append(RELATIONSHIPS[0], rec)


def read_relationships() -> list[dict]:
    return read_jsonl(RELATIONSHIPS[0])


def relationships_head() -> dict | None:
    return _head(RELATIONSHIPS[0])


def relationship_exists(study_id: str) -> bool:
    return _exists(RELATIONSHIPS[0], RELATIONSHIPS[1], study_id)


# ── Experiments (event-sourced) ──
def append_experiment_event(rec: dict) -> None:
    _append(EXPERIMENTS[0], rec)


def read_experiment_events() -> list[dict]:
    return read_jsonl(EXPERIMENTS[0])


def experiments_head() -> dict | None:
    return _head(EXPERIMENTS[0])


def experiment_event_exists(event_id: str) -> bool:
    return _exists(EXPERIMENTS[0], EXPERIMENTS[1], event_id)


def experiment_events_for(experiment_id: str) -> list[dict]:
    return [r for r in read_experiment_events() if r.get("experiment_id") == experiment_id]


def distinct_experiments() -> list[dict]:
    out: dict = {}
    for r in read_experiment_events():
        xid = r.get("experiment_id")
        if xid not in out:
            out[xid] = r
    return list(out.values())


# ── Evidences ──
def append_evidence(rec: dict) -> None:
    _append(EVIDENCES[0], rec)


def read_evidences() -> list[dict]:
    return read_jsonl(EVIDENCES[0])


def evidences_head() -> dict | None:
    return _head(EVIDENCES[0])


def evidence_exists(evidence_id: str) -> bool:
    return _exists(EVIDENCES[0], EVIDENCES[1], evidence_id)


def evidences_for_experiment(experiment_id: str) -> list[dict]:
    return [r for r in read_evidences() if r.get("experiment_id") == experiment_id]


# ── Graphs (event-sourced) ──
def append_graph_event(rec: dict) -> None:
    _append(GRAPHS[0], rec)


def read_graph_events() -> list[dict]:
    return read_jsonl(GRAPHS[0])


def graphs_head() -> dict | None:
    return _head(GRAPHS[0])


def graph_event_exists(event_id: str) -> bool:
    return _exists(GRAPHS[0], GRAPHS[1], event_id)


def graph_events_for(graph_id: str) -> list[dict]:
    return [r for r in read_graph_events() if r.get("graph_id") == graph_id]


def distinct_graphs() -> list[dict]:
    out: dict = {}
    for r in read_graph_events():
        gid = r.get("graph_id")
        if gid not in out:
            out[gid] = r
    return list(out.values())


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
