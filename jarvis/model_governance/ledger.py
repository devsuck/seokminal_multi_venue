"""Model Governance 원장 (P9.9) — 7개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일은 mg_ 접두사(기존 approvals/drift_reports 원장과 충돌 회피). 각 레코드: previous_hash ·
record_hash(sha256 canonical). 모델 거버넌스 기록만 — 모델/학습/배포 실행 없음.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — mg_ 네임스페이스
MODELS = ("mg_models.jsonl", "model_hash")
VERSIONS = ("mg_versions.jsonl", "version_id")            # 이벤트 소싱(생명주기 전이)
TRAINING_RUNS = ("mg_training_runs.jsonl", "run_id")
EVALUATIONS = ("mg_evaluations.jsonl", "report_id")
APPROVALS = ("mg_approvals.jsonl", "approval_id")
DEPLOYMENTS = ("mg_deployments.jsonl", "deployment_id")
DRIFT_REPORTS = ("mg_drift_reports.jsonl", "report_id")

ALL_LEDGERS = (MODELS, VERSIONS, TRAINING_RUNS, EVALUATIONS, APPROVALS, DEPLOYMENTS,
               DRIFT_REPORTS)


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


# ── Models ──
def append_model(rec: dict) -> None:
    _append(MODELS[0], rec)


def read_models() -> list[dict]:
    return read_jsonl(MODELS[0])


def models_head() -> dict | None:
    return _head(MODELS[0])


def model_hash_exists(h: str) -> bool:
    return _exists(MODELS[0], MODELS[1], h)


# ── Versions (event-sourced) ──
def append_version(rec: dict) -> None:
    _append(VERSIONS[0], rec)


def read_versions() -> list[dict]:
    return read_jsonl(VERSIONS[0])


def versions_head() -> dict | None:
    return _head(VERSIONS[0])


def version_event_exists(version_id: str) -> bool:
    return _exists(VERSIONS[0], VERSIONS[1], version_id)


def version_events_for(vkey: str) -> list[dict]:
    return [r for r in read_versions() if r.get("version_key") == vkey]


# ── Training runs ──
def append_training(rec: dict) -> None:
    _append(TRAINING_RUNS[0], rec)


def read_training() -> list[dict]:
    return read_jsonl(TRAINING_RUNS[0])


def training_head() -> dict | None:
    return _head(TRAINING_RUNS[0])


def training_exists(run_id: str) -> bool:
    return _exists(TRAINING_RUNS[0], TRAINING_RUNS[1], run_id)


# ── Evaluations ──
def append_evaluation(rec: dict) -> None:
    _append(EVALUATIONS[0], rec)


def read_evaluations() -> list[dict]:
    return read_jsonl(EVALUATIONS[0])


def evaluations_head() -> dict | None:
    return _head(EVALUATIONS[0])


def evaluation_exists(report_id: str) -> bool:
    return _exists(EVALUATIONS[0], EVALUATIONS[1], report_id)


# ── Approvals ──
def append_approval(rec: dict) -> None:
    _append(APPROVALS[0], rec)


def read_approvals() -> list[dict]:
    return read_jsonl(APPROVALS[0])


def approvals_head() -> dict | None:
    return _head(APPROVALS[0])


def approval_exists(approval_id: str) -> bool:
    return _exists(APPROVALS[0], APPROVALS[1], approval_id)


# ── Deployments ──
def append_deployment(rec: dict) -> None:
    _append(DEPLOYMENTS[0], rec)


def read_deployments() -> list[dict]:
    return read_jsonl(DEPLOYMENTS[0])


def deployments_head() -> dict | None:
    return _head(DEPLOYMENTS[0])


def deployment_exists(deployment_id: str) -> bool:
    return _exists(DEPLOYMENTS[0], DEPLOYMENTS[1], deployment_id)


# ── Drift reports ──
def append_drift(rec: dict) -> None:
    _append(DRIFT_REPORTS[0], rec)


def read_drift() -> list[dict]:
    return read_jsonl(DRIFT_REPORTS[0])


def drift_head() -> dict | None:
    return _head(DRIFT_REPORTS[0])


def drift_exists(report_id: str) -> bool:
    return _exists(DRIFT_REPORTS[0], DRIFT_REPORTS[1], report_id)
