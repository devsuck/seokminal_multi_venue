"""Research Governance 원장 (P10.2) — 7개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일은 rg_ 접두사(기존 registry.jsonl 과 개념·물리 분리). 각 레코드: previous_hash ·
record_hash(sha256 canonical) · timestamp · 불변 id. 연구 거버넌스 기록만 — 주문/실행/자본배분 없음.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — rg_ 네임스페이스
STRATEGIES = ("rg_strategies.jsonl", "strategy_hash")
STRATEGY_VERSIONS = ("rg_strategy_versions.jsonl", "version_id")   # 이벤트 소싱
EXPERIMENTS = ("rg_experiments.jsonl", "experiment_id")
BACKTESTS = ("rg_backtests.jsonl", "backtest_id")
VALIDATION_REPORTS = ("rg_validation_reports.jsonl", "report_id")
COMPARISONS = ("rg_comparisons.jsonl", "comparison_id")
ARTIFACTS = ("rg_artifacts.jsonl", "artifact_id")

ALL_LEDGERS = (STRATEGIES, STRATEGY_VERSIONS, EXPERIMENTS, BACKTESTS, VALIDATION_REPORTS,
               COMPARISONS, ARTIFACTS)


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


# ── Strategies ──
def append_strategy(rec: dict) -> None:
    _append(STRATEGIES[0], rec)


def read_strategies() -> list[dict]:
    return read_jsonl(STRATEGIES[0])


def strategies_head() -> dict | None:
    return _head(STRATEGIES[0])


def strategy_hash_exists(h: str) -> bool:
    return _exists(STRATEGIES[0], STRATEGIES[1], h)


# ── Strategy versions (event-sourced) ──
def append_version(rec: dict) -> None:
    _append(STRATEGY_VERSIONS[0], rec)


def read_versions() -> list[dict]:
    return read_jsonl(STRATEGY_VERSIONS[0])


def versions_head() -> dict | None:
    return _head(STRATEGY_VERSIONS[0])


def version_event_exists(version_id: str) -> bool:
    return _exists(STRATEGY_VERSIONS[0], STRATEGY_VERSIONS[1], version_id)


def version_events_for(vkey: str) -> list[dict]:
    return [r for r in read_versions() if r.get("version_key") == vkey]


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


# ── Backtests ──
def append_backtest(rec: dict) -> None:
    _append(BACKTESTS[0], rec)


def read_backtests() -> list[dict]:
    return read_jsonl(BACKTESTS[0])


def backtests_head() -> dict | None:
    return _head(BACKTESTS[0])


def backtest_exists(backtest_id: str) -> bool:
    return _exists(BACKTESTS[0], BACKTESTS[1], backtest_id)


def backtests_for(experiment_id: str) -> list[dict]:
    return [r for r in read_backtests() if r.get("experiment_id") == experiment_id]


# ── Validation reports ──
def append_validation(rec: dict) -> None:
    _append(VALIDATION_REPORTS[0], rec)


def read_validations() -> list[dict]:
    return read_jsonl(VALIDATION_REPORTS[0])


def validations_head() -> dict | None:
    return _head(VALIDATION_REPORTS[0])


def validation_exists(report_id: str) -> bool:
    return _exists(VALIDATION_REPORTS[0], VALIDATION_REPORTS[1], report_id)


# ── Comparisons ──
def append_comparison(rec: dict) -> None:
    _append(COMPARISONS[0], rec)


def read_comparisons() -> list[dict]:
    return read_jsonl(COMPARISONS[0])


def comparisons_head() -> dict | None:
    return _head(COMPARISONS[0])


def comparison_exists(comparison_id: str) -> bool:
    return _exists(COMPARISONS[0], COMPARISONS[1], comparison_id)


# ── Artifacts ──
def append_artifact(rec: dict) -> None:
    _append(ARTIFACTS[0], rec)


def read_artifacts() -> list[dict]:
    return read_jsonl(ARTIFACTS[0])


def artifacts_head() -> dict | None:
    return _head(ARTIFACTS[0])


def artifact_exists(artifact_id: str) -> bool:
    return _exists(ARTIFACTS[0], ARTIFACTS[1], artifact_id)
