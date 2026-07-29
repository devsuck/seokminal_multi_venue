"""Knowledge Graph 모델·저장 스키마 (P4).

엔티티/관계 정의 + SQLite 그래프 테이블(nodes/edges/graph_meta). 외부 그래프DB 없음.
graph.db는 P3 projection 위에 세우는 disposable 프로젝션 — 삭제 후 rebuild하면 동일.
"""
from __future__ import annotations

import os

from jarvis.config import state_path

GRAPH_DB = "knowledge.db"

# 엔티티 타입(10)
NODE_TYPES = ["Strategy", "Experiment", "Hypothesis", "Signal", "Allocation",
              "PortfolioDecision", "Regime", "FailureReason", "Dataset", "Metric"]

# 관계 타입(8)
RELATIONS = ["derived_from", "tested", "failed_because", "generated",
             "contributed_to", "produced", "affected_by", "used"]

# 실패로 간주하는 experiment status
FAILED_STATUSES = {"rejected", "weak", "underpowered", "blocked_by_data",
                   "no_effect", "inconclusive", "research_negative_drift"}

# 전략 실패 상태
STRATEGY_FAILED = {"rejected", "blocked_by_data", "paper_failed", "paper_retired", "retired"}

GRAPH_SCHEMA = """
CREATE TABLE nodes (
    id         TEXT PRIMARY KEY,
    type       TEXT,
    name       TEXT,
    metadata   TEXT,
    created_at TEXT
);
CREATE TABLE edges (
    source_id  TEXT,
    relation   TEXT,
    target_id  TEXT,
    metadata   TEXT,
    PRIMARY KEY (source_id, relation, target_id)
);
CREATE TABLE graph_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE INDEX idx_nodes_type ON nodes(type);
CREATE INDEX idx_edges_source ON edges(source_id);
CREATE INDEX idx_edges_target ON edges(target_id);
CREATE INDEX idx_edges_relation ON edges(relation);
"""


def graph_db_path() -> str:
    return state_path(GRAPH_DB)


def node_id(node_type: str, key: str) -> str:
    return f"{node_type}:{key}"


def graph_exists(path: str | None = None) -> bool:
    return os.path.exists(path or graph_db_path())


# ── 실패사유 정규화(진단 문자열 → 카테고리) ──
_FAIL_MAP = [
    ("signal dead", "SIGNAL_DEAD"),
    ("cost", "COST_EXECUTION"),
    ("survivor", "SURVIVORSHIP"),
    ("look-ahead", "LOOKAHEAD"), ("lookahead", "LOOKAHEAD"),
    ("confound", "CONFOUND"),
    ("bh-fdr", "FAILED_MULTIPLE_TESTING"), ("multiple", "FAILED_MULTIPLE_TESTING"),
    ("random", "INDISTINGUISHABLE_FROM_RANDOM"),
    ("underpower", "UNDERPOWERED"),
    ("blocked", "BLOCKED_BY_DATA"),
    ("negative", "NEGATIVE_DRIFT"),
    ("no_effect", "NO_EFFECT"), ("no effect", "NO_EFFECT"),
]


def failure_category(result: str | None, reason: str | None, status: str | None) -> str:
    blob = " ".join(x for x in (result, reason, status) if x).lower()
    for kw, cat in _FAIL_MAP:
        if kw in blob:
            return cat
    return "OTHER"


def datasets_from_meta(meta: dict) -> list[str]:
    out = set()
    for key in ("data_source", "universe"):
        v = meta.get(key)
        if v:
            out.add(str(v))
    return sorted(out)
