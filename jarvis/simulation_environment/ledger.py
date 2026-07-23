"""Research Simulation Environment 원장 (P10.8) — 7개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 sim_ 접두사(execution paper-sim 의 simulation_ 과 구별). 각 레코드: id · previous_hash ·
record_hash · timestamp. 비실행 시뮬레이션 연구 기록만. 상위 레이어(P10.2~P10.7)는 **READ ONLY**.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (sim_ 접두사)
SCENARIOS = ("sim_scenarios.jsonl", "event_id")         # 이벤트 소싱
RUNS = ("sim_runs.jsonl", "event_id")                   # 이벤트 소싱
PARAMETERS = ("sim_parameters.jsonl", "parameter_id")
REGIMES = ("sim_regimes.jsonl", "regime_id")
RESULTS = ("sim_results.jsonl", "result_id")
COMPARISONS = ("sim_comparisons.jsonl", "comparison_id")
ARTIFACTS = ("sim_artifacts.jsonl", "artifact_id")

ALL_LEDGERS = (SCENARIOS, RUNS, PARAMETERS, REGIMES, RESULTS, COMPARISONS, ARTIFACTS)

# 상위 레이어 물리 원장(READ ONLY 데이터 소스) — import 결합 없음, 파일만 읽는다.
SOURCE_LEDGERS = {
    "STRATEGY": ("research_governance", "rg_strategies.jsonl", "strategy_id"),
    "SIGNAL": ("alpha_intelligence", "ai_signals.jsonl", "signal_id"),
    "PORTFOLIO": ("portfolio_research", "pr_portfolios.jsonl", "portfolio_id"),
    "GRAPH": ("research_kg", "kg_entities.jsonl", "entity_id"),
    "DECISION": ("decision_intelligence", "di_candidates.jsonl", "candidate_id"),
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


# ── Scenarios (event-sourced) ──
def append_scenario_event(rec: dict) -> None:
    _append(SCENARIOS[0], rec)


def read_scenario_events() -> list[dict]:
    return read_jsonl(SCENARIOS[0])


def scenarios_head() -> dict | None:
    return _head(SCENARIOS[0])


def scenario_event_exists(event_id: str) -> bool:
    return _exists(SCENARIOS[0], SCENARIOS[1], event_id)


def scenario_events_for(scenario_id: str) -> list[dict]:
    return [r for r in read_scenario_events() if r.get("scenario_id") == scenario_id]


def distinct_scenarios() -> list[dict]:
    out: dict = {}
    for r in read_scenario_events():
        sid = r.get("scenario_id")
        if sid not in out:
            out[sid] = r
    return list(out.values())


# ── Runs (event-sourced) ──
def append_run_event(rec: dict) -> None:
    _append(RUNS[0], rec)


def read_run_events() -> list[dict]:
    return read_jsonl(RUNS[0])


def runs_head() -> dict | None:
    return _head(RUNS[0])


def run_event_exists(event_id: str) -> bool:
    return _exists(RUNS[0], RUNS[1], event_id)


def run_events_for(run_id: str) -> list[dict]:
    return [r for r in read_run_events() if r.get("run_id") == run_id]


def distinct_runs() -> list[dict]:
    out: dict = {}
    for r in read_run_events():
        rid = r.get("run_id")
        if rid not in out:
            out[rid] = r
    return list(out.values())


# ── Parameters ──
def append_parameter(rec: dict) -> None:
    _append(PARAMETERS[0], rec)


def read_parameters() -> list[dict]:
    return read_jsonl(PARAMETERS[0])


def parameters_head() -> dict | None:
    return _head(PARAMETERS[0])


def parameter_exists(parameter_id: str) -> bool:
    return _exists(PARAMETERS[0], PARAMETERS[1], parameter_id)


# ── Regimes ──
def append_regime(rec: dict) -> None:
    _append(REGIMES[0], rec)


def read_regimes() -> list[dict]:
    return read_jsonl(REGIMES[0])


def regimes_head() -> dict | None:
    return _head(REGIMES[0])


def regime_exists(regime_id: str) -> bool:
    return _exists(REGIMES[0], REGIMES[1], regime_id)


# ── Results ──
def append_result(rec: dict) -> None:
    _append(RESULTS[0], rec)


def read_results() -> list[dict]:
    return read_jsonl(RESULTS[0])


def results_head() -> dict | None:
    return _head(RESULTS[0])


def result_exists(result_id: str) -> bool:
    return _exists(RESULTS[0], RESULTS[1], result_id)


def result_for_run(run_id: str) -> dict | None:
    for r in read_results():
        if r.get("run_id") == run_id:
            return r
    return None


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
