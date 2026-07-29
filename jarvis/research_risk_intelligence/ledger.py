"""Research Risk Intelligence 원장 (P10.25) — 5개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 rr_ 접두사(Research Risk). 각 레코드: id · timestamp · previous_hash · record_hash. 연구 과정
리스크 분석·기록만 — 리스크 한도 변경·자본 결정·전략 거부·배포 결정 없음. 상위 소스는 **READ ONLY**.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (rr_ 접두사)
RISKS = ("rr_risks.jsonl", "event_id")                    # 이벤트 소싱
ASSESSMENTS = ("rr_assessments.jsonl", "assessment_id")
FACTORS = ("rr_factors.jsonl", "factor_id")
REPORTS = ("rr_reports.jsonl", "report_id")
ARTIFACTS = ("rr_artifacts.jsonl", "artifact_id")

ALL_LEDGERS = (RISKS, ASSESSMENTS, FACTORS, REPORTS, ARTIFACTS)

# 상위 소스 원장(READ ONLY) — P10.2/P10.3/P10.4/P10.7/P10.8. import 결합 없음, 파일만 읽는다.
SOURCE_LEDGERS = {
    "strategy_governance": ("rg_strategies.jsonl", "strategy_id"),
    "alpha_intelligence": ("ai_signals.jsonl", "signal_id"),
    "portfolio_research": ("pr_portfolios.jsonl", "portfolio_id"),
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


# ── 상위 소스 READ ONLY ──
def read_source(filename: str) -> list[dict]:
    """상위 소스 원장을 읽기 전용으로 로드. 절대 쓰지 않는다."""
    return read_jsonl(filename)


def source_count(layer: str) -> int:
    spec = SOURCE_LEDGERS.get(layer)
    if not spec:
        return 0
    return len(read_source(spec[0]))


# ── Risks (event-sourced) ──
def append_risk_event(rec: dict) -> None:
    _append(RISKS[0], rec)


def read_risk_events() -> list[dict]:
    return read_jsonl(RISKS[0])


def risks_head() -> dict | None:
    return _head(RISKS[0])


def risk_event_exists(event_id: str) -> bool:
    return _exists(RISKS[0], RISKS[1], event_id)


def risk_events_for(risk_id: str) -> list[dict]:
    return [r for r in read_risk_events() if r.get("risk_id") == risk_id]


def distinct_risks() -> list[dict]:
    out: dict = {}
    for r in read_risk_events():
        rid = r.get("risk_id")
        if rid not in out:
            out[rid] = r
    return list(out.values())


def risk_exists(risk_id: str) -> bool:
    return any(r.get("risk_id") == risk_id for r in read_risk_events())


# ── Assessments (불변) ──
def append_assessment(rec: dict) -> None:
    _append(ASSESSMENTS[0], rec)


def read_assessments() -> list[dict]:
    return read_jsonl(ASSESSMENTS[0])


def assessments_head() -> dict | None:
    return _head(ASSESSMENTS[0])


def assessment_exists(assessment_id: str) -> bool:
    return _exists(ASSESSMENTS[0], ASSESSMENTS[1], assessment_id)


def get_assessment(assessment_id: str) -> dict | None:
    for r in read_assessments():
        if r.get("assessment_id") == assessment_id:
            return r
    return None


# ── Factors (불변) ──
def append_factor(rec: dict) -> None:
    _append(FACTORS[0], rec)


def read_factors() -> list[dict]:
    return read_jsonl(FACTORS[0])


def factors_head() -> dict | None:
    return _head(FACTORS[0])


def factor_exists(factor_id: str) -> bool:
    return _exists(FACTORS[0], FACTORS[1], factor_id)


def get_factor(factor_id: str) -> dict | None:
    for r in read_factors():
        if r.get("factor_id") == factor_id:
            return r
    return None


def factors_for(risk_ref: str) -> list[dict]:
    return [r for r in read_factors() if r.get("risk_ref") == risk_ref]


# ── Reports ──
def append_report(rec: dict) -> None:
    _append(REPORTS[0], rec)


def read_reports() -> list[dict]:
    return read_jsonl(REPORTS[0])


def reports_head() -> dict | None:
    return _head(REPORTS[0])


def report_exists(report_id: str) -> bool:
    return _exists(REPORTS[0], REPORTS[1], report_id)


# ── Artifacts (계보) ──
def append_artifact(rec: dict) -> None:
    _append(ARTIFACTS[0], rec)


def read_artifacts() -> list[dict]:
    return read_jsonl(ARTIFACTS[0])


def artifacts_head() -> dict | None:
    return _head(ARTIFACTS[0])


def artifact_exists(artifact_id: str) -> bool:
    return _exists(ARTIFACTS[0], ARTIFACTS[1], artifact_id)
