"""Research Data 원장 (P10.1) — 5개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

datasets · features · quality_reports · lineage · snapshots. 각 레코드: previous_hash ·
record_hash(sha256 canonical). 연구 데이터 거버넌스 기록만 — 전략/주문/포트폴리오/브로커 없음.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드)
DATASETS = ("datasets.jsonl", "dataset_hash")
FEATURES = ("features.jsonl", "feature_hash")
QUALITY_REPORTS = ("quality_reports.jsonl", "report_id")
LINEAGE = ("lineage.jsonl", "lineage_id")
SNAPSHOTS = ("snapshots.jsonl", "snapshot_id")

ALL_LEDGERS = (DATASETS, FEATURES, QUALITY_REPORTS, LINEAGE, SNAPSHOTS)


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


def dataset_hash_exists(dataset_hash: str) -> bool:
    return _exists(DATASETS[0], DATASETS[1], dataset_hash)


# ── Features ──
def append_feature(rec: dict) -> None:
    _append(FEATURES[0], rec)


def read_features() -> list[dict]:
    return read_jsonl(FEATURES[0])


def features_head() -> dict | None:
    return _head(FEATURES[0])


def feature_hash_exists(feature_hash: str) -> bool:
    return _exists(FEATURES[0], FEATURES[1], feature_hash)


# ── Quality reports ──
def append_quality_report(rec: dict) -> None:
    _append(QUALITY_REPORTS[0], rec)


def read_quality_reports() -> list[dict]:
    return read_jsonl(QUALITY_REPORTS[0])


def quality_reports_head() -> dict | None:
    return _head(QUALITY_REPORTS[0])


def quality_report_exists(report_id: str) -> bool:
    return _exists(QUALITY_REPORTS[0], QUALITY_REPORTS[1], report_id)


# ── Lineage ──
def append_lineage(rec: dict) -> None:
    _append(LINEAGE[0], rec)


def read_lineage() -> list[dict]:
    return read_jsonl(LINEAGE[0])


def lineage_head() -> dict | None:
    return _head(LINEAGE[0])


def lineage_exists(lineage_id: str) -> bool:
    return _exists(LINEAGE[0], LINEAGE[1], lineage_id)


# ── Snapshots ──
def append_snapshot(rec: dict) -> None:
    _append(SNAPSHOTS[0], rec)


def read_snapshots() -> list[dict]:
    return read_jsonl(SNAPSHOTS[0])


def snapshots_head() -> dict | None:
    return _head(SNAPSHOTS[0])


def snapshot_exists(snapshot_id: str) -> bool:
    return _exists(SNAPSHOTS[0], SNAPSHOTS[1], snapshot_id)
