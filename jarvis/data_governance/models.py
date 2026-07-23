"""Data Governance & Lineage 자료형 (P9.8) — 데이터 거버넌스·계보 전용.

**실행/거래/브로커/리스크/포트폴리오/권한 변경 없음.** 데이터셋/스키마/버전/계보/품질/신선도/신뢰도만.
불변 버전·append-only 해시체인·결정적. record_hash = 정렬 canonical json sha256(체인 필드 제외).
물리 원장은 dg_ 접두사(기존 P10.1 datasets/quality_reports 원장과 충돌 회피).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

GENESIS = "GENESIS"

# ── Quality 상태 ──
EXCELLENT = "EXCELLENT"
GOOD = "GOOD"
WARNING = "WARNING"
FAILED = "FAILED"

# ── Schema Drift 결과 ──
NO_DRIFT = "NO_DRIFT"
WARNING_DRIFT = "WARNING_DRIFT"
CRITICAL_DRIFT = "CRITICAL_DRIFT"

# ── Reliability 등급 ──
RELIABLE = "RELIABLE"
DEGRADED = "DEGRADED"
UNRELIABLE = "UNRELIABLE"


class ImmutableDatasetError(Exception):
    """불변 데이터셋 위반."""


class ImmutableSchemaError(Exception):
    """불변 스키마 버전 위반(동일 dataset+version 컬럼 상이)."""


class LineageError(Exception):
    """계보 무결성 위반(자기참조·사이클)."""


# ── 해시 ──
def _digest(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def input_digest(*parts) -> str:
    return _digest(list(parts))


def content_hash(record: dict) -> str:
    core = {k: v for k, v in record.items()
            if k not in ("previous_hash", "record_hash", "report_hash")}
    return _digest(core)


def dataset_hash(dataset_id: str, name: str, source: str, asset_class: str,
                 description: str) -> str:
    return _digest({"dataset_id": dataset_id, "name": name, "source": source,
                    "asset_class": asset_class, "description": description})


def version_hash(dataset_id: str, version: str, row_count: int, data_checksum: str,
                 schema_id: str) -> str:
    return _digest({"dataset_id": dataset_id, "version": version, "row_count": row_count,
                    "data_checksum": data_checksum, "schema_id": schema_id})


def schema_hash(dataset_id: str, version: str, columns: dict) -> str:
    return _digest({"dataset_id": dataset_id, "version": version,
                    "columns": sorted(columns.items())})


def lineage_event_id(dataset_id: str, parent_dataset: str, operation: str, version: str) -> str:
    return "DGL:" + hashlib.sha1(
        input_digest(dataset_id, parent_dataset, operation, version).encode()).hexdigest()[:12]


def quality_report_id(dataset_id: str, metrics_hash: str) -> str:
    return "DGQ:" + hashlib.sha1(
        input_digest(dataset_id, metrics_hash).encode()).hexdigest()[:12]


def reliability_score_id(dataset_id: str, input_hash_: str) -> str:
    return "DGR:" + hashlib.sha1(
        input_digest(dataset_id, input_hash_).encode()).hexdigest()[:12]


# ── 품질 점수(8개 체크 결정적 집계) ──
def quality_score(checks: dict) -> int:
    penalty = (float(checks.get("missing_ratio", 0.0)) * 40.0
               + float(checks.get("duplicate_ratio", 0.0)) * 20.0
               + float(checks.get("null_ratio", 0.0)) * 15.0)
    if checks.get("schema_mismatch"):
        penalty += 25.0
    if checks.get("stale_timestamp"):
        penalty += 15.0
    if checks.get("unexpected_columns"):
        penalty += 10.0
    if checks.get("row_count_anomaly"):
        penalty += 15.0
    if not checks.get("source_consistent", True):
        penalty += 10.0
    return max(0, min(100, int(round(100.0 - penalty))))


def quality_status(score: int, schema_mismatch: bool) -> str:
    if schema_mismatch or score < 50:
        return FAILED
    if score < 75:
        return WARNING
    if score < 90:
        return GOOD
    return EXCELLENT


def reliability_level(score: int) -> str:
    if score >= 80:
        return RELIABLE
    if score >= 55:
        return DEGRADED
    return UNRELIABLE


def compare_schemas(old_columns: dict, new_columns: dict) -> tuple[str, list]:
    """스키마 비교 → (drift_level, 변경목록). 타입 변경/컬럼 제거 → CRITICAL, 추가 → WARNING."""
    changes: list = []
    old_columns = old_columns or {}
    new_columns = new_columns or {}
    removed = sorted(set(old_columns) - set(new_columns))
    added = sorted(set(new_columns) - set(old_columns))
    typed = sorted(c for c in set(old_columns) & set(new_columns)
                   if old_columns[c] != new_columns[c])
    for c in removed:
        changes.append(f"removed:{c}:{old_columns[c]}")
    for c in typed:
        changes.append(f"type_changed:{c}:{old_columns[c]}->{new_columns[c]}")
    for c in added:
        changes.append(f"added:{c}:{new_columns[c]}")
    if removed or typed:
        return CRITICAL_DRIFT, changes
    if added:
        return WARNING_DRIFT, changes
    return NO_DRIFT, changes


def detect_lineage_cycle(edges: list, new_child: str = "", new_parent: str = "") -> list:
    graph: dict = {}
    for e in edges:
        graph.setdefault(e[0], set()).add(e[1])
    if new_child:
        if new_child == new_parent:
            return [new_child, new_parent]
        graph.setdefault(new_child, set()).add(new_parent)
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict = {}
    path: list = []

    def dfs(node) -> list:
        color[node] = GRAY
        path.append(node)
        for nxt in sorted(graph.get(node, ())):
            c = color.get(nxt, WHITE)
            if c == GRAY:
                return path[path.index(nxt):] + [nxt]
            if c == WHITE:
                r = dfs(nxt)
                if r:
                    return r
        path.pop()
        color[node] = BLACK
        return []

    for node in sorted(graph):
        if color.get(node, WHITE) == WHITE:
            r = dfs(node)
            if r:
                return r
    return []


def compute_checks(records: list, expected_columns: dict, now: str = "", *,
                   expected_row_count: int | None = None, source_field: str = "source",
                   expected_source: str = "", timestamp_field: str = "timestamp",
                   stale_seconds: float = 86400.0) -> dict:
    """데이터 레코드 → 8개 품질 체크(결정적)."""
    import datetime as _dt

    def _parse(ts):
        try:
            return _dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    records = records or []
    n = len(records)
    cols = list((expected_columns or {}).keys())
    if n == 0:
        return {"missing_ratio": 0.0, "duplicate_ratio": 0.0, "null_ratio": 0.0,
                "schema_mismatch": False, "stale_timestamp": False,
                "unexpected_columns": [], "row_count_anomaly": False,
                "source_consistent": True, "row_count": 0}
    # missing / null
    missing = null = 0
    total_expected = n * max(1, len(cols))
    total_cells = 0
    present_cols: set = set()
    for r in records:
        present_cols |= set(r.keys())
        for c in cols:
            if c not in r:
                missing += 1
            elif r.get(c) in (None, ""):
                missing += 1
        for _k, v in r.items():
            total_cells += 1
            if v in (None, ""):
                null += 1
    missing_ratio = round(missing / total_expected, 8) if cols else 0.0
    null_ratio = round(null / total_cells, 8) if total_cells else 0.0
    # duplicate
    seen = set()
    dups = 0
    for r in records:
        key = json.dumps(r, sort_keys=True, ensure_ascii=False, default=str)
        if key in seen:
            dups += 1
        seen.add(key)
    duplicate_ratio = round(dups / n, 8)
    # unexpected columns / schema mismatch
    unexpected = sorted(present_cols - set(cols)) if cols else []
    missing_cols = sorted(set(cols) - present_cols)
    schema_mismatch = bool(missing_cols) or (missing_ratio > 0)
    # stale timestamp
    stale = False
    ts_vals = [r.get(timestamp_field) for r in records if r.get(timestamp_field)]
    if ts_vals and now:
        latest = max(_parse(t) for t in ts_vals if _parse(t)) if any(_parse(t) for t in ts_vals) else None
        n_dt = _parse(now)
        if latest and n_dt:
            stale = (n_dt - latest).total_seconds() > stale_seconds
    # row count anomaly
    row_anomaly = False
    if expected_row_count is not None and expected_row_count > 0:
        row_anomaly = abs(n - expected_row_count) / expected_row_count > 0.5
    # source consistency
    src_consistent = True
    if expected_source:
        src_consistent = all(str(r.get(source_field, "")) == expected_source for r in records)
    return {"missing_ratio": missing_ratio, "duplicate_ratio": duplicate_ratio,
            "null_ratio": null_ratio, "schema_mismatch": schema_mismatch,
            "stale_timestamp": stale, "unexpected_columns": unexpected,
            "row_count_anomaly": row_anomaly, "source_consistent": src_consistent,
            "row_count": n}


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class DatasetMetadata:
    dataset_id: str
    name: str
    description: str
    source: str
    asset_class: str
    owner: str
    created_at: str
    dataset_hash: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DatasetVersion:
    version_hash: str
    dataset_id: str
    version: str
    row_count: int
    data_checksum: str
    schema_id: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SchemaDefinition:
    schema_hash: str
    dataset_id: str
    version: str
    columns: dict
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LineageEvent:
    lineage_id: str
    dataset_id: str
    parent_dataset: str
    operation: str
    transformation: str
    version: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DataQualityReport:
    report_id: str
    dataset_id: str
    checks: dict
    quality_score: int
    status: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DataReliabilityScore:
    dataset_id: str
    quality_score: int
    freshness_score: int
    lineage_completeness: int
    reliability_score: int
    level: str
    created_at: str
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DataGovernanceSummary:
    timestamp: str
    dataset_count: int
    schema_count: int
    version_count: int
    lineage_count: int
    quality_report_count: int
    average_quality_score: float
    failed_datasets: int

    def to_dict(self) -> dict:
        return asdict(self)
