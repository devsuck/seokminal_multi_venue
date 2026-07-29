"""Research Knowledge Graph 원장 (P10.5) — 6개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일은 kg_ 접두사. 각 레코드: id · previous_hash · record_hash(sha256 canonical). 그래프 기록만.
상위 레이어(P9.8~P10.4) 원장은 **READ ONLY** 로만 읽는다 — 그 파일에는 절대 append/수정하지 않는다.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장
ENTITIES = ("kg_entities.jsonl", "event_id")            # 이벤트 소싱(entity_key 로 그룹)
RELATIONSHIPS = ("kg_relationships.jsonl", "relationship_id")
LINEAGE_EDGES = ("kg_lineage_edges.jsonl", "lineage_id")
GRAPH_SNAPSHOTS = ("kg_graph_snapshots.jsonl", "snapshot_id")
SIMILARITY_REPORTS = ("kg_similarity_reports.jsonl", "report_id")
ARTIFACTS = ("kg_artifacts.jsonl", "artifact_id")

ALL_LEDGERS = (ENTITIES, RELATIONSHIPS, LINEAGE_EDGES, GRAPH_SNAPSHOTS,
               SIMILARITY_REPORTS, ARTIFACTS)

# 상위 레이어 물리 원장(READ ONLY 데이터 소스) — import 결합 없음, 파일만 읽는다.
SOURCE_LEDGERS = {
    "data_governance": {
        "DATASET": ("dg_datasets.jsonl", "dataset_id"),
    },
    "research_data": {
        "DATASET": ("datasets.jsonl", "dataset_id"),
        "FEATURE": ("features.jsonl", "feature_id"),
    },
    "alpha_intelligence": {
        "SIGNAL": ("ai_signals.jsonl", "signal_id"),
        "FEATURE": ("ai_features.jsonl", "feature_id"),
        "EXPERIMENT": ("ai_experiments.jsonl", "experiment_id"),
    },
    "model_governance": {
        "MODEL": ("mg_models.jsonl", "model_id"),
    },
    "research_governance": {
        "STRATEGY": ("rg_strategies.jsonl", "strategy_id"),
        "EXPERIMENT": ("rg_experiments.jsonl", "experiment_id"),
        "BACKTEST": ("rg_backtests.jsonl", "backtest_id"),
        "VALIDATION": ("rg_validation_reports.jsonl", "report_id"),
    },
    "portfolio_research": {
        "PORTFOLIO": ("pr_portfolios.jsonl", "portfolio_id"),
        "BACKTEST": ("pr_backtests.jsonl", "backtest_id"),
        "RISK_ANALYSIS": ("pr_risk_analyses.jsonl", "analysis_id"),
    },
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


# ── Entities (event-sourced) ──
def append_entity_event(rec: dict) -> None:
    _append(ENTITIES[0], rec)


def read_entity_events() -> list[dict]:
    return read_jsonl(ENTITIES[0])


def entities_head() -> dict | None:
    return _head(ENTITIES[0])


def entity_event_exists(event_id: str) -> bool:
    return _exists(ENTITIES[0], ENTITIES[1], event_id)


def entity_events_for(entity_key: str) -> list[dict]:
    return [r for r in read_entity_events() if r.get("entity_key") == entity_key]


def entity_exists(entity_id: str) -> bool:
    return any(r.get("entity_id") == entity_id for r in read_entity_events())


def distinct_entities() -> list[dict]:
    """entity_id 별 최초 등록 이벤트(메타데이터 원본)."""
    out: dict = {}
    for r in read_entity_events():
        eid = r.get("entity_id")
        if eid not in out:
            out[eid] = r
    return list(out.values())


# ── Relationships ──
def append_relationship(rec: dict) -> None:
    _append(RELATIONSHIPS[0], rec)


def read_relationships() -> list[dict]:
    return read_jsonl(RELATIONSHIPS[0])


def relationships_head() -> dict | None:
    return _head(RELATIONSHIPS[0])


def relationship_exists(relationship_id: str) -> bool:
    return _exists(RELATIONSHIPS[0], RELATIONSHIPS[1], relationship_id)


# ── Lineage edges ──
def append_lineage_edge(rec: dict) -> None:
    _append(LINEAGE_EDGES[0], rec)


def read_lineage_edges() -> list[dict]:
    return read_jsonl(LINEAGE_EDGES[0])


def lineage_head() -> dict | None:
    return _head(LINEAGE_EDGES[0])


def lineage_exists(lineage_id: str) -> bool:
    return _exists(LINEAGE_EDGES[0], LINEAGE_EDGES[1], lineage_id)


# ── Graph snapshots ──
def append_snapshot(rec: dict) -> None:
    _append(GRAPH_SNAPSHOTS[0], rec)


def read_snapshots() -> list[dict]:
    return read_jsonl(GRAPH_SNAPSHOTS[0])


def snapshots_head() -> dict | None:
    return _head(GRAPH_SNAPSHOTS[0])


def snapshot_exists(snapshot_id: str) -> bool:
    return _exists(GRAPH_SNAPSHOTS[0], GRAPH_SNAPSHOTS[1], snapshot_id)


# ── Similarity reports ──
def append_similarity(rec: dict) -> None:
    _append(SIMILARITY_REPORTS[0], rec)


def read_similarity() -> list[dict]:
    return read_jsonl(SIMILARITY_REPORTS[0])


def similarity_head() -> dict | None:
    return _head(SIMILARITY_REPORTS[0])


def similarity_exists(report_id: str) -> bool:
    return _exists(SIMILARITY_REPORTS[0], SIMILARITY_REPORTS[1], report_id)


# ── Artifacts ──
def append_artifact(rec: dict) -> None:
    _append(ARTIFACTS[0], rec)


def read_artifacts() -> list[dict]:
    return read_jsonl(ARTIFACTS[0])


def artifacts_head() -> dict | None:
    return _head(ARTIFACTS[0])


def artifact_exists(artifact_id: str) -> bool:
    return _exists(ARTIFACTS[0], ARTIFACTS[1], artifact_id)
