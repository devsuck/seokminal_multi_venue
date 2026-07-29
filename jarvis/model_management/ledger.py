"""Model Management 원장 (P43) — 7개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 mdl_ 접두사(MoDeL management). 각 레코드: id · timestamp · previous_hash · record_hash. 모델 생애주기·
검증·성능·메타 기록만 — 라이브 배포 없음. 상위 계층은 **READ ONLY** — 파일만 읽는다(소유 결합 없음, 변경 없음).
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

MODELS = ("mdl_models.jsonl", "model_event_id")                  # 모델 생애주기(ES)
VERSIONS = ("mdl_versions.jsonl", "version_id")                 # 모델 버전
VALIDATIONS = ("mdl_validations.jsonl", "validation_id")       # 검증 결과
PERFORMANCE = ("mdl_performance.jsonl", "performance_id")      # 성능 이력
METADATA = ("mdl_metadata.jsonl", "metadata_id")             # 모델 메타
REPORTS = ("mdl_reports.jsonl", "report_id")                # 리포트
ARTIFACTS = ("mdl_artifacts.jsonl", "artifact_id")         # 계보

ALL_LEDGERS = (MODELS, VERSIONS, VALIDATIONS, PERFORMANCE, METADATA, REPORTS, ARTIFACTS)

# ── 참조 대상(READ ONLY 소스) — import 결합 없음, 파일만 읽는다. ──
SOURCE_LAYERS = {
    "experiment_tracking": ("expt_experiments.jsonl", "experiment_id"),  # P42
    "data_infrastructure": ("dinf_datasets.jsonl", "dataset_event_id"),  # P41
    "model_governance": ("mg_models.jsonl", "model_hash"),             # P9.9 (거버넌스)
}


def _append(filename, record) -> None:
    p = state_path(filename)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def read_jsonl(filename) -> list[dict]:
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


def _head(filename):
    recs = read_jsonl(filename)
    return recs[-1] if recs else None


def _exists(filename, id_field, rid) -> bool:
    return any(r.get(id_field) == rid for r in read_jsonl(filename))


def source_count(layer) -> int:
    spec = SOURCE_LAYERS.get(layer)
    if not spec:
        return 0
    return len(read_jsonl(spec[0]))


def source_present(layer) -> bool:
    spec = SOURCE_LAYERS.get(layer)
    if not spec:
        return False
    return os.path.exists(state_path(spec[0]))


def all_source_counts() -> dict:
    return {k: source_count(k) for k in sorted(SOURCE_LAYERS)}


def _readers(spec):
    fname, idf = spec

    def append(rec):
        _append(fname, rec)

    def read():
        return read_jsonl(fname)

    def head():
        return _head(fname)

    def exists(rid):
        return _exists(fname, idf, rid)

    return append, read, head, exists


append_model_event, read_model_events, models_head, model_event_exists = _readers(MODELS)
append_version, read_versions, versions_head, version_exists = _readers(VERSIONS)
append_validation, read_validations, validations_head, validation_exists = _readers(VALIDATIONS)
append_performance, read_performance, performance_head, performance_exists = _readers(PERFORMANCE)
append_metadata, read_metadata, metadata_head, metadata_exists = _readers(METADATA)
append_report, read_reports, reports_head, report_exists = _readers(REPORTS)
append_artifact, read_artifacts, artifacts_head, artifact_exists = _readers(ARTIFACTS)


def model_events(mdl) -> list[dict]:
    return [r for r in read_model_events() if r.get("model_id") == mdl]


def model_ids() -> list[str]:
    return sorted({r.get("model_id") for r in read_model_events() if r.get("model_id")})


def versions_for(mdl) -> list[dict]:
    return [r for r in read_versions() if r.get("model_id") == mdl]


def validations_for(mdl) -> list[dict]:
    return [r for r in read_validations() if r.get("model_id") == mdl]


def performance_for(mdl) -> list[dict]:
    return [r for r in read_performance() if r.get("model_id") == mdl]
