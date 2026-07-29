"""Data Governance Engine (P9.8) — 데이터셋/스키마/버전/계보/품질/신선도/신뢰도. **거버넌스 전용.**

데이터셋·스키마를 불변 버전으로 등록하고 계보(사이클 차단)·품질(8체크)·스키마 drift·신선도·신뢰도
점수를 관리한다. **실행/거래/브로커/리스크/포트폴리오/권한 변경 없음.** execution/control 계층
import·coupling 없음. 외부 데이터는 injected/file reader 로만 소비. 결정적·append-only.
"""
from __future__ import annotations

import datetime as _dt

from jarvis.data_governance import ledger
from jarvis.data_governance.models import (
    GENESIS,
    NO_DRIFT,
    DataGovernanceSummary,
    DataQualityReport,
    DataReliabilityScore,
    DatasetMetadata,
    DatasetVersion,
    ImmutableDatasetError,
    ImmutableSchemaError,
    LineageError,
    LineageEvent,
    SchemaDefinition,
    compare_schemas,
    compute_checks,
    content_hash,
    dataset_hash as _dataset_hash,
    detect_lineage_cycle,
    input_digest,
    lineage_event_id,
    quality_report_id,
    quality_score,
    quality_status,
    reliability_level,
    reliability_score_id,
    schema_hash as _schema_hash,
    version_hash as _version_hash,
)


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


def _parse(ts: str):
    try:
        return _dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


class DataGovernanceEngine:
    """데이터 거버넌스 엔진. 불변 버전·append-only·결정적. 실행/집행 없음."""

    # ── register_dataset ──
    def register_dataset(self, dataset_id: str, name: str, description: str, source: str,
                         asset_class: str, owner: str, now: str = "",
                         *, commit: bool = False) -> DatasetMetadata:
        dh = _dataset_hash(dataset_id, name, source, asset_class, description)
        for d in ledger.read_datasets():
            if d.get("dataset_id") == dataset_id:
                if d.get("dataset_hash") != dh:
                    raise ImmutableDatasetError(f"{dataset_id} 는 불변 — 메타 변경 불가")
                return DatasetMetadata(**{k: v for k, v in d.items()
                                          if k in DatasetMetadata.__dataclass_fields__})
        rec = DatasetMetadata(
            dataset_id=dataset_id, name=name, description=description, source=source,
            asset_class=asset_class, owner=owner, created_at=now, dataset_hash=dh,
            input_hash=dh, previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.dataset_hash_exists(dh):
            head = ledger.datasets_head()
            ledger.append_dataset(_seal(rec, head["record_hash"] if head else GENESIS))
        return DatasetMetadata(**rec)

    # ── register_schema ──
    def register_schema(self, dataset_id: str, version: str, columns: dict, now: str = "",
                        *, commit: bool = False) -> SchemaDefinition:
        sh = _schema_hash(dataset_id, version, columns)
        for s in ledger.read_schemas():
            if s.get("dataset_id") == dataset_id and s.get("version") == version:
                if s.get("schema_hash") != sh:
                    raise ImmutableSchemaError(
                        f"{dataset_id} schema v{version} 는 불변 — 컬럼 변경 불가")
                return SchemaDefinition(**{k: v for k, v in s.items()
                                           if k in SchemaDefinition.__dataclass_fields__})
        rec = SchemaDefinition(
            schema_hash=sh, dataset_id=dataset_id, version=version, columns=dict(columns),
            created_at=now, input_hash=sh, previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.schema_hash_exists(sh):
            head = ledger.schemas_head()
            ledger.append_schema(_seal(rec, head["record_hash"] if head else GENESIS))
        return SchemaDefinition(**rec)

    # ── register_version ──
    def register_version(self, dataset_id: str, version: str, row_count: int,
                         data_checksum: str, schema_id: str, now: str = "",
                         *, commit: bool = False) -> DatasetVersion:
        vh = _version_hash(dataset_id, version, row_count, data_checksum, schema_id)
        rec = DatasetVersion(
            version_hash=vh, dataset_id=dataset_id, version=version, row_count=row_count,
            data_checksum=data_checksum, schema_id=schema_id, created_at=now, input_hash=vh,
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.version_hash_exists(vh):
            head = ledger.versions_head()
            ledger.append_version(_seal(rec, head["record_hash"] if head else GENESIS))
        return DatasetVersion(**rec)

    # ── record_lineage ──
    def record_lineage(self, dataset_id: str, parent_dataset: str, operation: str,
                       transformation: str, version: str, now: str = "",
                       *, require_parent: bool = True, commit: bool = False) -> LineageEvent:
        if dataset_id == parent_dataset:
            raise LineageError("자기 참조 계보 금지")
        known = {d.get("dataset_id") for d in ledger.read_datasets()}
        if require_parent and parent_dataset and parent_dataset not in known:
            raise LineageError(f"미존재 부모 데이터셋 {parent_dataset}")
        edges = [(r.get("dataset_id"), r.get("parent_dataset"))
                 for r in ledger.read_lineage() if r.get("parent_dataset")]
        cycle = detect_lineage_cycle(edges, dataset_id, parent_dataset)
        if cycle:
            raise LineageError(f"계보 사이클: {'->'.join(cycle)}")
        lid = lineage_event_id(dataset_id, parent_dataset, operation, version)
        rec = LineageEvent(
            lineage_id=lid, dataset_id=dataset_id, parent_dataset=parent_dataset,
            operation=operation, transformation=transformation, version=version,
            created_at=now, input_hash=input_digest(dataset_id, parent_dataset, operation, version),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.lineage_exists(lid):
            head = ledger.lineage_head()
            ledger.append_lineage(_seal(rec, head["record_hash"] if head else GENESIS))
        return LineageEvent(**rec)

    def lineage_chain(self, dataset_id: str) -> list[str]:
        parent_of: dict = {}
        for r in ledger.read_lineage():
            if r.get("parent_dataset"):
                parent_of.setdefault(r["dataset_id"], r["parent_dataset"])
        chain = [dataset_id]
        cur, seen = dataset_id, {dataset_id}
        while cur in parent_of:
            p = parent_of[cur]
            if p in seen:
                break
            chain.append(p)
            seen.add(p)
            cur = p
        return list(reversed(chain))

    # ── validate_quality (8 checks) ──
    def validate_quality(self, dataset_id: str, now: str = "", *, records=None,
                         expected_columns=None, checks: dict | None = None,
                         expected_row_count=None, expected_source: str = "",
                         commit: bool = False) -> DataQualityReport:
        if checks is None:
            checks = compute_checks(records or [], expected_columns or {}, now,
                                    expected_row_count=expected_row_count,
                                    expected_source=expected_source)
        score = quality_score(checks)
        status = quality_status(score, bool(checks.get("schema_mismatch")))
        ih = input_digest(dataset_id, sorted((k, str(v)) for k, v in checks.items()))
        rid = quality_report_id(dataset_id, ih)
        rec = DataQualityReport(
            report_id=rid, dataset_id=dataset_id, checks=dict(checks), quality_score=score,
            status=status, created_at=now, input_hash=ih, previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.quality_report_exists(rid):
            head = ledger.quality_reports_head()
            ledger.append_quality_report(_seal(rec, head["record_hash"] if head else GENESIS))
        return DataQualityReport(**rec)

    # ── detect_schema_drift ──
    def detect_schema_drift(self, dataset_id: str, new_columns: dict, *,
                            old_columns: dict | None = None) -> dict:
        if old_columns is None:
            prev = [s for s in ledger.read_schemas() if s.get("dataset_id") == dataset_id]
            old_columns = prev[-1].get("columns", {}) if prev else {}
        level, changes = compare_schemas(old_columns, new_columns)
        return {"dataset_id": dataset_id, "drift_level": level, "changes": changes,
                "old_columns": old_columns, "new_columns": new_columns}

    # ── detect_stale_data ──
    def detect_stale_data(self, dataset_id: str, last_timestamp: str, now: str, *,
                          stale_seconds: float = 86400.0) -> dict:
        lt, nt = _parse(last_timestamp), _parse(now)
        age = (nt - lt).total_seconds() if (lt and nt) else None
        stale = age is not None and age > stale_seconds
        return {"dataset_id": dataset_id, "stale": bool(stale),
                "age_seconds": round(age, 3) if age is not None else None,
                "threshold_seconds": stale_seconds, "last_timestamp": last_timestamp}

    def check_source_freshness(self, source_ledger_filename: str, now: str, *,
                               stale_seconds: float = 86400.0) -> dict:
        """기존 P9.x 원장 파일의 신선도 관측(데이터로만 읽기 — 변경 없음)."""
        rows = ledger.read_jsonl(source_ledger_filename)
        last_ts = ""
        for r in reversed(rows):
            if r.get("timestamp"):
                last_ts = r["timestamp"]
                break
        res = self.detect_stale_data(source_ledger_filename, last_ts, now,
                                     stale_seconds=stale_seconds)
        res["n_records"] = len(rows)
        return res

    # ── calculate_reliability_score ──
    def calculate_reliability_score(self, dataset_id: str, now: str = "", *,
                                    stale_seconds: float = 86400.0) -> DataReliabilityScore:
        qrs = [q for q in ledger.read_quality_reports() if q.get("dataset_id") == dataset_id]
        q_score = int(qrs[-1].get("quality_score", 0)) if qrs else 0
        # freshness: 최신 품질 체크의 stale 플래그 기반
        fresh = 100
        if qrs and qrs[-1].get("checks", {}).get("stale_timestamp"):
            fresh = 40
        elif not qrs:
            fresh = 50
        # lineage completeness: 부모 계보 존재 여부
        has_lineage = any(r.get("dataset_id") == dataset_id and r.get("parent_dataset")
                          for r in ledger.read_lineage())
        lineage_completeness = 100 if has_lineage else 50
        reliability = int(round(0.5 * q_score + 0.3 * fresh + 0.2 * lineage_completeness))
        reliability = max(0, min(100, reliability))
        return DataReliabilityScore(
            dataset_id=dataset_id, quality_score=q_score, freshness_score=fresh,
            lineage_completeness=lineage_completeness, reliability_score=reliability,
            level=reliability_level(reliability), created_at=now,
            detail={"has_quality": bool(qrs), "has_lineage": has_lineage})

    # ── summary ──
    def summary(self, now: str = "") -> DataGovernanceSummary:
        datasets = {d.get("dataset_id") for d in ledger.read_datasets()}
        qrs = ledger.read_quality_reports()
        scores = [int(q.get("quality_score", 0)) for q in qrs]
        avg = round(sum(scores) / len(scores), 2) if scores else 0.0
        failed = sum(1 for q in qrs if q.get("status") == "FAILED")
        return DataGovernanceSummary(
            timestamp=now, dataset_count=len(datasets),
            schema_count=len(ledger.read_schemas()), version_count=len(ledger.read_versions()),
            lineage_count=len(ledger.read_lineage()), quality_report_count=len(qrs),
            average_quality_score=avg, failed_datasets=failed)
