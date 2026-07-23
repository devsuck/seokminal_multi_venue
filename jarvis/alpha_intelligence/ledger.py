"""Alpha Intelligence 원장 (P10.3) — 8개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

각 레코드: id · timestamp · previous_hash · record_hash(sha256 canonical). alpha 연구 기록만 —
trading signal 실행·주문·portfolio·자본배분 없음. signal 은 연구 객체.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드)
SIGNALS = ("ai_signals.jsonl", "signal_hash")
SIGNAL_VERSIONS = ("ai_signal_versions.jsonl", "version_id")   # 이벤트 소싱
FEATURES = ("ai_features.jsonl", "feature_hash")
HYPOTHESES = ("ai_hypotheses.jsonl", "hypothesis_id")
EXPERIMENTS = ("ai_experiments.jsonl", "experiment_id")
EVALUATIONS = ("ai_evaluations.jsonl", "evaluation_id")
RANKINGS = ("ai_rankings.jsonl", "ranking_id")
ARTIFACTS = ("ai_artifacts.jsonl", "artifact_id")

ALL_LEDGERS = (SIGNALS, SIGNAL_VERSIONS, FEATURES, HYPOTHESES, EXPERIMENTS, EVALUATIONS,
               RANKINGS, ARTIFACTS)


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


# ── Signals ──
def append_signal(rec: dict) -> None:
    _append(SIGNALS[0], rec)


def read_signals() -> list[dict]:
    return read_jsonl(SIGNALS[0])


def signals_head() -> dict | None:
    return _head(SIGNALS[0])


def signal_hash_exists(h: str) -> bool:
    return _exists(SIGNALS[0], SIGNALS[1], h)


# ── Signal versions (event-sourced) ──
def append_version(rec: dict) -> None:
    _append(SIGNAL_VERSIONS[0], rec)


def read_versions() -> list[dict]:
    return read_jsonl(SIGNAL_VERSIONS[0])


def versions_head() -> dict | None:
    return _head(SIGNAL_VERSIONS[0])


def version_event_exists(version_id: str) -> bool:
    return _exists(SIGNAL_VERSIONS[0], SIGNAL_VERSIONS[1], version_id)


def version_events_for(vkey: str) -> list[dict]:
    return [r for r in read_versions() if r.get("version_key") == vkey]


# ── Features ──
def append_feature(rec: dict) -> None:
    _append(FEATURES[0], rec)


def read_features() -> list[dict]:
    return read_jsonl(FEATURES[0])


def features_head() -> dict | None:
    return _head(FEATURES[0])


def feature_hash_exists(h: str) -> bool:
    return _exists(FEATURES[0], FEATURES[1], h)


def feature_ids() -> set:
    return {f.get("feature_id") for f in read_features()}


# ── Hypotheses ──
def append_hypothesis(rec: dict) -> None:
    _append(HYPOTHESES[0], rec)


def read_hypotheses() -> list[dict]:
    return read_jsonl(HYPOTHESES[0])


def hypotheses_head() -> dict | None:
    return _head(HYPOTHESES[0])


def hypothesis_exists(hypothesis_id: str) -> bool:
    return _exists(HYPOTHESES[0], HYPOTHESES[1], hypothesis_id)


# ── Experiments ──
def append_experiment(rec: dict) -> None:
    _append(EXPERIMENTS[0], rec)


def read_experiments() -> list[dict]:
    return read_jsonl(EXPERIMENTS[0])


def experiments_head() -> dict | None:
    return _head(EXPERIMENTS[0])


def experiment_exists(experiment_id: str) -> bool:
    return _exists(EXPERIMENTS[0], EXPERIMENTS[1], experiment_id)


def get_experiment(experiment_id: str) -> dict | None:
    for r in read_experiments():
        if r.get("experiment_id") == experiment_id:
            return r
    return None


# ── Evaluations ──
def append_evaluation(rec: dict) -> None:
    _append(EVALUATIONS[0], rec)


def read_evaluations() -> list[dict]:
    return read_jsonl(EVALUATIONS[0])


def evaluations_head() -> dict | None:
    return _head(EVALUATIONS[0])


def evaluation_exists(evaluation_id: str) -> bool:
    return _exists(EVALUATIONS[0], EVALUATIONS[1], evaluation_id)


# ── Rankings ──
def append_ranking(rec: dict) -> None:
    _append(RANKINGS[0], rec)


def read_rankings() -> list[dict]:
    return read_jsonl(RANKINGS[0])


def rankings_head() -> dict | None:
    return _head(RANKINGS[0])


def ranking_exists(ranking_id: str) -> bool:
    return _exists(RANKINGS[0], RANKINGS[1], ranking_id)


# ── Artifacts ──
def append_artifact(rec: dict) -> None:
    _append(ARTIFACTS[0], rec)


def read_artifacts() -> list[dict]:
    return read_jsonl(ARTIFACTS[0])


def artifacts_head() -> dict | None:
    return _head(ARTIFACTS[0])


def artifact_exists(artifact_id: str) -> bool:
    return _exists(ARTIFACTS[0], ARTIFACTS[1], artifact_id)
