"""Real Data Infrastructure 원장 (P41) — 7개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 dinf_ 접두사(Data INFrastructure). 각 레코드: id · timestamp · previous_hash · record_hash. 데이터 메타·
검증·계보 기록만 — 거래·실행 없음. 상위 계층은 **READ ONLY** — 파일만 읽는다(소유 결합 없음, 변경 없음).
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

SOURCES = ("dinf_sources.jsonl", "source_id")                    # 데이터 소스 레지스트리
DATASETS = ("dinf_datasets.jsonl", "dataset_event_id")          # 데이터셋 생애주기(ES)
VERSIONS = ("dinf_versions.jsonl", "version_id")                # 데이터셋 버전
FEATURES = ("dinf_features.jsonl", "feature_set_id")           # 피처 메타
QUALITY = ("dinf_quality.jsonl", "quality_id")                # 품질 리포트
REPORTS = ("dinf_reports.jsonl", "report_id")                # 인프라 리포트
ARTIFACTS = ("dinf_artifacts.jsonl", "artifact_id")         # 계보(lineage)

ALL_LEDGERS = (SOURCES, DATASETS, VERSIONS, FEATURES, QUALITY, REPORTS, ARTIFACTS)

# ── 참조 대상(READ ONLY 소스) — import 결합 없음, 파일만 읽는다. ──
SOURCE_LAYERS = {
    "data_governance": ("dg_datasets.jsonl", "dataset_hash"),      # P9.8 (거버넌스 데이터셋)
    "alpha_intelligence": ("ai_experiments.jsonl", "experiment_id"),  # P10.3
    "simulation": ("sim_scenarios.jsonl", "event_id"),           # P10.8
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


append_source, read_sources, sources_head, source_exists = _readers(SOURCES)
append_dataset_event, read_dataset_events, datasets_head, dataset_event_exists = _readers(DATASETS)
append_version, read_versions, versions_head, version_exists = _readers(VERSIONS)
append_feature, read_features, features_head, feature_exists = _readers(FEATURES)
append_quality, read_quality, quality_head, quality_exists = _readers(QUALITY)
append_report, read_reports, reports_head, report_exists = _readers(REPORTS)
append_artifact, read_artifacts, artifacts_head, artifact_exists = _readers(ARTIFACTS)


def dataset_events(ds) -> list[dict]:
    return [r for r in read_dataset_events() if r.get("dataset_id") == ds]


def dataset_ids() -> list[str]:
    return sorted({r.get("dataset_id") for r in read_dataset_events() if r.get("dataset_id")})


def versions_for(ds) -> list[dict]:
    return [r for r in read_versions() if r.get("dataset_id") == ds]


def quality_for(ds) -> list[dict]:
    return [r for r in read_quality() if r.get("dataset_id") == ds]


def source_by_id(sid):
    return next((r for r in read_sources() if r.get("source_id") == sid), None)
