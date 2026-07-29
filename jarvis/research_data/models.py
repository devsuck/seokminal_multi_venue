"""Research Data Platform & Data Governance 자료형 (P10.1) — 연구 데이터 관리 전용.

**전략 실행·주문·포트폴리오·브로커·live capital 없음.** 데이터셋 레지스트리·스키마 메타·데이터
품질·lineage·재현 스냅샷만. 불변 버전·append-only 해시체인·결정적. record_hash = 정렬 canonical
json 의 sha256(체인/파생 해시 필드 제외).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

GENESIS = "GENESIS"

# ── Data Quality 상태 ──
EXCELLENT = "EXCELLENT"
GOOD = "GOOD"
WARNING = "WARNING"
FAILED = "FAILED"


class ImmutableDatasetError(Exception):
    """불변 데이터셋 버전 위반(동일 id+schema_version 내용 상이)."""


class ImmutableFeatureError(Exception):
    """불변 피처 버전 위반(동일 id+calculation_version 내용 상이)."""


class LineageError(Exception):
    """lineage 무결성 위반(사이클·자기참조·미존재 부모)."""


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


def dataset_hash(dataset_id: str, name: str, description: str, asset_class: str,
                 source: str, frequency: str, coverage_start: str, coverage_end: str,
                 schema_version: str) -> str:
    """데이터셋 콘텐츠 해시(owner/created_at 제외 — 버전 불변 판정)."""
    return _digest({"dataset_id": dataset_id, "name": name, "description": description,
                    "asset_class": asset_class, "source": source, "frequency": frequency,
                    "coverage_start": coverage_start, "coverage_end": coverage_end,
                    "schema_version": schema_version})


def feature_hash(feature_id: str, name: str, description: str, category: str,
                 source_dataset: str, calculation_version: str) -> str:
    return _digest({"feature_id": feature_id, "name": name, "description": description,
                    "category": category, "source_dataset": source_dataset,
                    "calculation_version": calculation_version})


def quality_report_id(dataset_id: str, metrics_hash: str) -> str:
    return "DQR:" + hashlib.sha1(
        input_digest(dataset_id, metrics_hash).encode()).hexdigest()[:12]


def lineage_id(dataset_id: str, parent_dataset: str, version: str) -> str:
    return "LIN:" + hashlib.sha1(
        input_digest(dataset_id, parent_dataset, version).encode()).hexdigest()[:12]


def snapshot_id(snapshot_hash: str) -> str:
    return "RSN:" + hashlib.sha1(snapshot_hash.encode()).hexdigest()[:12]


def snapshot_hash(dataset_versions: dict, feature_versions: dict) -> str:
    return _digest({"datasets": sorted(dataset_versions.items()),
                    "features": sorted(feature_versions.items())})


def quality_score(missing_ratio: float, duplicate_ratio: float, outlier_count: int,
                  schema_valid: bool, timestamp_continuity: bool) -> int:
    """결정적 품질 점수(0~100)."""
    penalty = (missing_ratio * 40.0 + duplicate_ratio * 30.0
               + min(int(outlier_count), 500) * 0.1)
    if not schema_valid:
        penalty += 30.0
    if not timestamp_continuity:
        penalty += 10.0
    return max(0, min(100, int(round(100.0 - penalty))))


def quality_status(score: int, schema_valid: bool) -> str:
    if not schema_valid or score < 50:
        return FAILED
    if score < 75:
        return WARNING
    if score < 90:
        return GOOD
    return EXCELLENT


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class DatasetMetadata:
    dataset_id: str
    name: str
    description: str
    asset_class: str
    source: str
    frequency: str
    coverage_start: str
    coverage_end: str
    schema_version: str
    owner: str
    created_at: str
    dataset_hash: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FeatureMetadata:
    feature_id: str
    name: str
    description: str
    category: str
    source_dataset: str
    calculation_version: str
    created_at: str
    feature_hash: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DataQualityReport:
    report_id: str
    dataset_id: str
    missing_ratio: float
    duplicate_ratio: float
    outlier_count: int
    schema_valid: bool
    timestamp_continuity: bool
    quality_score: int
    status: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DataLineageRecord:
    lineage_id: str
    dataset_id: str
    parent_dataset: str
    transformation: str
    version: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ResearchSnapshot:
    snapshot_id: str
    dataset_versions: dict
    feature_versions: dict
    snapshot_hash: str
    created_at: str
    dataset_count: int = 0
    feature_count: int = 0
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ResearchDataSummary:
    timestamp: str
    dataset_count: int
    feature_count: int
    quality_report_count: int
    average_quality_score: float
    failed_datasets: int
    lineage_count: int
    snapshot_count: int

    def to_dict(self) -> dict:
        return asdict(self)


# ── 스키마/lineage 헬퍼 ──
def compute_metrics(records: list, required_fields: list,
                    timestamp_field: str = "timestamp") -> dict:
    """데이터 레코드 → 품질 메트릭(결정적). missing/duplicate/schema/timestamp continuity."""
    records = records or []
    n = len(records)
    req = list(required_fields or [])
    if n == 0:
        return {"missing_ratio": 0.0, "duplicate_ratio": 0.0, "outlier_count": 0,
                "schema_valid": True, "timestamp_continuity": True}
    # missing: 필수 필드 셀 결측 비율
    total_cells = n * max(1, len(req))
    missing = 0
    schema_valid = True
    for r in records:
        for f in req:
            if f not in r or r.get(f) in (None, ""):
                missing += 1
                schema_valid = False
    missing_ratio = round(missing / total_cells, 8) if req else 0.0
    # duplicate: 동일 레코드(정렬 json) 비율
    seen = set()
    dups = 0
    for r in records:
        key = json.dumps(r, sort_keys=True, ensure_ascii=False, default=str)
        if key in seen:
            dups += 1
        seen.add(key)
    duplicate_ratio = round(dups / n, 8)
    # timestamp 연속성: 단조 증가 + 중복 없음
    continuity = True
    ts = [r.get(timestamp_field) for r in records if r.get(timestamp_field) is not None]
    if len(ts) >= 2:
        continuity = all(ts[i] < ts[i + 1] for i in range(len(ts) - 1))
    return {"missing_ratio": missing_ratio, "duplicate_ratio": duplicate_ratio,
            "outlier_count": 0, "schema_valid": schema_valid,
            "timestamp_continuity": continuity}


def detect_lineage_cycle(edges: list, new_child: str = "", new_parent: str = "") -> list:
    """child→parent 간선 목록(+선택 신규 간선)에서 사이클 경로 반환(없으면 [])."""
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
