"""Portfolio Research 원장 (P10.4) — 8개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일은 pr_ 접두사. 각 레코드: id · timestamp · previous_hash · record_hash(sha256 canonical).
포트폴리오 연구 기록만 — 실제 자본배분·주문·portfolio mutation 없음. portfolio 는 연구 객체.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드)
PORTFOLIOS = ("pr_portfolios.jsonl", "portfolio_hash")
PORTFOLIO_VERSIONS = ("pr_portfolio_versions.jsonl", "version_id")   # 이벤트 소싱
HYPOTHESES = ("pr_hypotheses.jsonl", "hypothesis_id")
CONSTRUCTION_STUDIES = ("pr_construction_studies.jsonl", "study_id")
BACKTESTS = ("pr_backtests.jsonl", "backtest_id")
RISK_ANALYSES = ("pr_risk_analyses.jsonl", "analysis_id")
COMPARISONS = ("pr_comparisons.jsonl", "comparison_id")
ARTIFACTS = ("pr_artifacts.jsonl", "artifact_id")

ALL_LEDGERS = (PORTFOLIOS, PORTFOLIO_VERSIONS, HYPOTHESES, CONSTRUCTION_STUDIES, BACKTESTS,
               RISK_ANALYSES, COMPARISONS, ARTIFACTS)


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


# ── Portfolios ──
def append_portfolio(rec: dict) -> None:
    _append(PORTFOLIOS[0], rec)


def read_portfolios() -> list[dict]:
    return read_jsonl(PORTFOLIOS[0])


def portfolios_head() -> dict | None:
    return _head(PORTFOLIOS[0])


def portfolio_hash_exists(h: str) -> bool:
    return _exists(PORTFOLIOS[0], PORTFOLIOS[1], h)


# ── Portfolio versions (event-sourced) ──
def append_version(rec: dict) -> None:
    _append(PORTFOLIO_VERSIONS[0], rec)


def read_versions() -> list[dict]:
    return read_jsonl(PORTFOLIO_VERSIONS[0])


def versions_head() -> dict | None:
    return _head(PORTFOLIO_VERSIONS[0])


def version_event_exists(version_id: str) -> bool:
    return _exists(PORTFOLIO_VERSIONS[0], PORTFOLIO_VERSIONS[1], version_id)


def version_events_for(vkey: str) -> list[dict]:
    return [r for r in read_versions() if r.get("version_key") == vkey]


# ── Hypotheses ──
def append_hypothesis(rec: dict) -> None:
    _append(HYPOTHESES[0], rec)


def read_hypotheses() -> list[dict]:
    return read_jsonl(HYPOTHESES[0])


def hypotheses_head() -> dict | None:
    return _head(HYPOTHESES[0])


def hypothesis_exists(hypothesis_id: str) -> bool:
    return _exists(HYPOTHESES[0], HYPOTHESES[1], hypothesis_id)


# ── Construction studies ──
def append_study(rec: dict) -> None:
    _append(CONSTRUCTION_STUDIES[0], rec)


def read_studies() -> list[dict]:
    return read_jsonl(CONSTRUCTION_STUDIES[0])


def studies_head() -> dict | None:
    return _head(CONSTRUCTION_STUDIES[0])


def study_exists(study_id: str) -> bool:
    return _exists(CONSTRUCTION_STUDIES[0], CONSTRUCTION_STUDIES[1], study_id)


def get_study(study_id: str) -> dict | None:
    for r in read_studies():
        if r.get("study_id") == study_id:
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


def backtests_for_portfolio(portfolio_id: str) -> list[dict]:
    return [r for r in read_backtests() if r.get("portfolio_id") == portfolio_id]


# ── Risk analyses ──
def append_risk(rec: dict) -> None:
    _append(RISK_ANALYSES[0], rec)


def read_risk() -> list[dict]:
    return read_jsonl(RISK_ANALYSES[0])


def risk_head() -> dict | None:
    return _head(RISK_ANALYSES[0])


def risk_exists(analysis_id: str) -> bool:
    return _exists(RISK_ANALYSES[0], RISK_ANALYSES[1], analysis_id)


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
