"""Data Governance 원장 (P9.8) — 5개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일은 dg_ 접두사(기존 P10.1 datasets/quality_reports 원장과 충돌 회피). 각 레코드:
previous_hash · record_hash(sha256 canonical). 데이터 거버넌스 기록만 — 실행/거래/브로커 없음.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — dg_ 네임스페이스로 기존 원장과 물리 분리
DATASETS = ("dg_datasets.jsonl", "dataset_hash")
DATASET_VERSIONS = ("dg_dataset_versions.jsonl", "version_hash")
SCHEMA_VERSIONS = ("dg_schema_versions.jsonl", "schema_hash")
LINEAGE_EVENTS = ("dg_lineage_events.jsonl", "lineage_id")
QUALITY_REPORTS = ("dg_quality_reports.jsonl", "report_id")

ALL_LEDGERS = (DATASETS, DATASET_VERSIONS, SCHEMA_VERSIONS, LINEAGE_EVENTS, QUALITY_REPORTS)


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


# ── Datasets ──
def append_dataset(rec: dict) -> None:
    _append(DATASETS[0], rec)


def read_datasets() -> list[dict]:
    return read_jsonl(DATASETS[0])


def datasets_head() -> dict | None:
    return _head(DATASETS[0])


def dataset_hash_exists(h: str) -> bool:
    return _exists(DATASETS[0], DATASETS[1], h)


# ── Dataset versions ──
def append_version(rec: dict) -> None:
    _append(DATASET_VERSIONS[0], rec)


def read_versions() -> list[dict]:
    return read_jsonl(DATASET_VERSIONS[0])


def versions_head() -> dict | None:
    return _head(DATASET_VERSIONS[0])


def version_hash_exists(h: str) -> bool:
    return _exists(DATASET_VERSIONS[0], DATASET_VERSIONS[1], h)


# ── Schema versions ──
def append_schema(rec: dict) -> None:
    _append(SCHEMA_VERSIONS[0], rec)


def read_schemas() -> list[dict]:
    return read_jsonl(SCHEMA_VERSIONS[0])


def schemas_head() -> dict | None:
    return _head(SCHEMA_VERSIONS[0])


def schema_hash_exists(h: str) -> bool:
    return _exists(SCHEMA_VERSIONS[0], SCHEMA_VERSIONS[1], h)


# ── Lineage events ──
def append_lineage(rec: dict) -> None:
    _append(LINEAGE_EVENTS[0], rec)


def read_lineage() -> list[dict]:
    return read_jsonl(LINEAGE_EVENTS[0])


def lineage_head() -> dict | None:
    return _head(LINEAGE_EVENTS[0])


def lineage_exists(lineage_id: str) -> bool:
    return _exists(LINEAGE_EVENTS[0], LINEAGE_EVENTS[1], lineage_id)


# ── Quality reports ──
def append_quality_report(rec: dict) -> None:
    _append(QUALITY_REPORTS[0], rec)


def read_quality_reports() -> list[dict]:
    return read_jsonl(QUALITY_REPORTS[0])


def quality_reports_head() -> dict | None:
    return _head(QUALITY_REPORTS[0])


def quality_report_exists(report_id: str) -> bool:
    return _exists(QUALITY_REPORTS[0], QUALITY_REPORTS[1], report_id)
