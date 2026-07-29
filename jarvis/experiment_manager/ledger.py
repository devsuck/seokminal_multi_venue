"""Experiment Manager 원장 (P11.4) — 5개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 exm_ 접두사(EXperiment Manager). 각 레코드: id · timestamp · previous_hash · record_hash. AI 보조 실험
제안 — 제안·계획·연구요청·결과 수집만, 실행/배포/라이브 전략 없음. APPROVED_FOR_RESEARCH 는 거래 승인이 아니다.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (exm_ 접두사)
EXPERIMENTS = ("exm_experiments.jsonl", "event_id")   # 생애주기 이벤트
PLANS = ("exm_plans.jsonl", "plan_id")
REQUESTS = ("exm_requests.jsonl", "request_id")
RESULTS = ("exm_results.jsonl", "result_id")
REPORTS = ("exm_reports.jsonl", "report_id")

ALL_LEDGERS = (EXPERIMENTS, PLANS, REQUESTS, RESULTS, REPORTS)


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


# ── Experiments (lifecycle events) ──
def append_experiment_event(rec: dict) -> None:
    _append(EXPERIMENTS[0], rec)


def read_experiment_events() -> list[dict]:
    return read_jsonl(EXPERIMENTS[0])


def experiments_head() -> dict | None:
    return _head(EXPERIMENTS[0])


def event_exists(event_id: str) -> bool:
    return _exists(EXPERIMENTS[0], EXPERIMENTS[1], event_id)


def experiment_events(experiment_id: str) -> list[dict]:
    return [r for r in read_experiment_events() if r.get("experiment_id") == experiment_id]


def experiment_ids() -> list[str]:
    return sorted({r.get("experiment_id") for r in read_experiment_events()
                   if r.get("experiment_id")})


# ── Plans ──
def append_plan(rec: dict) -> None:
    _append(PLANS[0], rec)


def read_plans() -> list[dict]:
    return read_jsonl(PLANS[0])


def plans_head() -> dict | None:
    return _head(PLANS[0])


def plan_exists(plan_id: str) -> bool:
    return _exists(PLANS[0], PLANS[1], plan_id)


def get_plan(plan_id: str) -> dict | None:
    return _get(PLANS[0], PLANS[1], plan_id)


def experiment_plans(experiment_id: str) -> list[dict]:
    return [r for r in read_plans() if r.get("experiment_id") == experiment_id]


# ── Requests ──
def append_request(rec: dict) -> None:
    _append(REQUESTS[0], rec)


def read_requests() -> list[dict]:
    return read_jsonl(REQUESTS[0])


def requests_head() -> dict | None:
    return _head(REQUESTS[0])


def request_exists(request_id: str) -> bool:
    return _exists(REQUESTS[0], REQUESTS[1], request_id)


def get_request(request_id: str) -> dict | None:
    return _get(REQUESTS[0], REQUESTS[1], request_id)


def experiment_requests(experiment_id: str) -> list[dict]:
    return [r for r in read_requests() if r.get("experiment_id") == experiment_id]


# ── Results ──
def append_result(rec: dict) -> None:
    _append(RESULTS[0], rec)


def read_results() -> list[dict]:
    return read_jsonl(RESULTS[0])


def results_head() -> dict | None:
    return _head(RESULTS[0])


def result_exists(result_id: str) -> bool:
    return _exists(RESULTS[0], RESULTS[1], result_id)


def get_result(result_id: str) -> dict | None:
    return _get(RESULTS[0], RESULTS[1], result_id)


def experiment_results(experiment_id: str) -> list[dict]:
    return [r for r in read_results() if r.get("experiment_id") == experiment_id]


# ── Reports ──
def append_report(rec: dict) -> None:
    _append(REPORTS[0], rec)


def read_reports() -> list[dict]:
    return read_jsonl(REPORTS[0])


def reports_head() -> dict | None:
    return _head(REPORTS[0])


def report_exists(report_id: str) -> bool:
    return _exists(REPORTS[0], REPORTS[1], report_id)


def get_report(report_id: str) -> dict | None:
    return _get(REPORTS[0], REPORTS[1], report_id)
