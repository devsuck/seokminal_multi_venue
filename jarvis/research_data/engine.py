"""Research Data Engine (P10.1) — 데이터셋 레지스트리·스키마·품질·lineage·스냅샷. **연구 관리 전용.**

데이터셋/피처를 불변 버전으로 등록하고, 스키마 검증·데이터 품질 평가·lineage(사이클 차단)·재현
스냅샷을 관리한다. **전략 실행·주문·포트폴리오·브로커·live capital 없음.** execution/control 계층
import·coupling 없음. 외부 데이터는 injected/file reader 로만 소비. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.research_data import ledger
from jarvis.research_data.models import (
    GENESIS,
    DataLineageRecord,
    DataQualityReport,
    DatasetMetadata,
    FeatureMetadata,
    ImmutableDatasetError,
    ImmutableFeatureError,
    LineageError,
    ResearchDataSummary,
    ResearchSnapshot,
    compute_metrics,
    content_hash,
    dataset_hash as _dataset_hash,
    detect_lineage_cycle,
    feature_hash as _feature_hash,
    input_digest,
    lineage_id as _lineage_id,
    quality_report_id,
    quality_score,
    quality_status,
    snapshot_hash as _snapshot_hash,
    snapshot_id as _snapshot_id,
)

_DATASET_REQUIRED = ("dataset_id", "name", "asset_class", "source", "frequency",
                     "schema_version")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


def _ver_key(v: str):
    try:
        return (0, int(v))
    except (ValueError, TypeError):
        return (1, str(v))


class ResearchDataEngine:
    """연구 데이터 거버넌스 엔진. 불변 버전·append-only·결정적. 실행/집행 없음."""

    # ── 1. Dataset / Feature Registry(불변) ──
    def register_dataset(self, dataset_id: str, name: str, description: str, asset_class: str,
                         source: str, frequency: str, coverage_start: str, coverage_end: str,
                         schema_version: str, owner: str, now: str = "",
                         *, commit: bool = False) -> DatasetMetadata:
        dh = _dataset_hash(dataset_id, name, description, asset_class, source, frequency,
                           coverage_start, coverage_end, schema_version)
        for d in ledger.read_datasets():
            if d.get("dataset_id") == dataset_id and d.get("schema_version") == schema_version:
                if d.get("dataset_hash") != dh:
                    raise ImmutableDatasetError(
                        f"{dataset_id} schema v{schema_version} 는 불변 — 내용 변경 불가")
                return DatasetMetadata(**{k: v for k, v in d.items()
                                          if k in DatasetMetadata.__dataclass_fields__})
        rec = DatasetMetadata(
            dataset_id=dataset_id, name=name, description=description, asset_class=asset_class,
            source=source, frequency=frequency, coverage_start=coverage_start,
            coverage_end=coverage_end, schema_version=schema_version, owner=owner,
            created_at=now, dataset_hash=dh, input_hash=dh, previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.dataset_hash_exists(dh):
            head = ledger.datasets_head()
            ledger.append_dataset(_seal(rec, head["record_hash"] if head else GENESIS))
        return DatasetMetadata(**rec)

    def register_feature(self, feature_id: str, name: str, description: str, category: str,
                         source_dataset: str, calculation_version: str, now: str = "",
                         *, commit: bool = False) -> FeatureMetadata:
        fh = _feature_hash(feature_id, name, description, category, source_dataset,
                           calculation_version)
        for f in ledger.read_features():
            if (f.get("feature_id") == feature_id
                    and f.get("calculation_version") == calculation_version):
                if f.get("feature_hash") != fh:
                    raise ImmutableFeatureError(
                        f"{feature_id} calc v{calculation_version} 는 불변")
                return FeatureMetadata(**{k: v for k, v in f.items()
                                          if k in FeatureMetadata.__dataclass_fields__})
        rec = FeatureMetadata(
            feature_id=feature_id, name=name, description=description, category=category,
            source_dataset=source_dataset, calculation_version=calculation_version,
            created_at=now, feature_hash=fh, input_hash=fh, previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.feature_hash_exists(fh):
            head = ledger.features_head()
            ledger.append_feature(_seal(rec, head["record_hash"] if head else GENESIS))
        return FeatureMetadata(**rec)

    def _active_datasets(self) -> list[dict]:
        latest: dict = {}
        for d in ledger.read_datasets():
            did = d.get("dataset_id")
            cur = latest.get(did)
            if cur is None or _ver_key(d.get("schema_version")) >= _ver_key(cur.get("schema_version")):
                latest[did] = d
        return [latest[k] for k in sorted(latest)]

    def _active_features(self) -> list[dict]:
        latest: dict = {}
        for f in ledger.read_features():
            fid = f.get("feature_id")
            cur = latest.get(fid)
            if cur is None or _ver_key(f.get("calculation_version")) >= _ver_key(cur.get("calculation_version")):
                latest[fid] = f
        return [latest[k] for k in sorted(latest)]

    # ── 2. Schema Validation ──
    @staticmethod
    def validate_schema(records: list, required_fields=None,
                        timestamp_field: str = "timestamp") -> dict:
        req = list(required_fields or _DATASET_REQUIRED)
        m = compute_metrics(records, req, timestamp_field)
        missing_fields = sorted({f for r in (records or []) for f in req
                                 if f not in r or r.get(f) in (None, "")})
        return {"schema_valid": m["schema_valid"], "missing_fields": missing_fields,
                "timestamp_continuity": m["timestamp_continuity"],
                "duplicate_ratio": m["duplicate_ratio"], "n_records": len(records or [])}

    # ── 3. Data Quality Assessment ──
    def assess_quality(self, dataset_id: str, now: str = "", *, records=None,
                       required_fields=None, metrics: dict | None = None,
                       commit: bool = False) -> DataQualityReport:
        if metrics is None:
            metrics = compute_metrics(records or [], required_fields or [], "timestamp")
        mr = float(metrics.get("missing_ratio", 0.0))
        dr = float(metrics.get("duplicate_ratio", 0.0))
        oc = int(metrics.get("outlier_count", 0))
        sv = bool(metrics.get("schema_valid", True))
        tc = bool(metrics.get("timestamp_continuity", True))
        score = quality_score(mr, dr, oc, sv, tc)
        status = quality_status(score, sv)
        ih = input_digest(dataset_id, mr, dr, oc, sv, tc)
        rid = quality_report_id(dataset_id, ih)
        rec = DataQualityReport(
            report_id=rid, dataset_id=dataset_id, missing_ratio=mr, duplicate_ratio=dr,
            outlier_count=oc, schema_valid=sv, timestamp_continuity=tc, quality_score=score,
            status=status, created_at=now, input_hash=ih, previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.quality_report_exists(rid):
            head = ledger.quality_reports_head()
            ledger.append_quality_report(_seal(rec, head["record_hash"] if head else GENESIS))
        return DataQualityReport(**rec)

    # ── 4. Dataset Lineage ──
    def register_lineage(self, dataset_id: str, parent_dataset: str, transformation: str,
                         version: str, now: str = "", *, require_parent: bool = True,
                         commit: bool = False) -> DataLineageRecord:
        if dataset_id == parent_dataset:
            raise LineageError("자기 참조 lineage 금지")
        known = {d.get("dataset_id") for d in ledger.read_datasets()}
        if require_parent and parent_dataset and parent_dataset not in known:
            raise LineageError(f"미존재 부모 데이터셋 {parent_dataset}")
        edges = [(r.get("dataset_id"), r.get("parent_dataset"))
                 for r in ledger.read_lineage() if r.get("parent_dataset")]
        cycle = detect_lineage_cycle(edges, dataset_id, parent_dataset)
        if cycle:
            raise LineageError(f"lineage 사이클: {'->'.join(cycle)}")
        lid = _lineage_id(dataset_id, parent_dataset, version)
        rec = DataLineageRecord(
            lineage_id=lid, dataset_id=dataset_id, parent_dataset=parent_dataset,
            transformation=transformation, version=version, created_at=now,
            input_hash=input_digest(dataset_id, parent_dataset, version),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.lineage_exists(lid):
            head = ledger.lineage_head()
            ledger.append_lineage(_seal(rec, head["record_hash"] if head else GENESIS))
        return DataLineageRecord(**rec)

    def lineage_chain(self, dataset_id: str) -> list[str]:
        """dataset_id 의 조상 체인(raw→...→dataset). 결정적."""
        parent_of: dict = {}
        for r in ledger.read_lineage():
            if r.get("parent_dataset"):
                parent_of.setdefault(r["dataset_id"], r["parent_dataset"])
        chain = [dataset_id]
        cur = dataset_id
        seen = {dataset_id}
        while cur in parent_of:
            p = parent_of[cur]
            if p in seen:
                break
            chain.append(p)
            seen.add(p)
            cur = p
        return list(reversed(chain))

    # ── 5. Research Snapshot(재현성) ──
    def snapshot(self, now: str = "", *, commit: bool = False) -> ResearchSnapshot:
        datasets = self._active_datasets()
        features = self._active_features()
        dvers = {d["dataset_id"]: d.get("schema_version") for d in datasets}
        fvers = {f["feature_id"]: f.get("calculation_version") for f in features}
        sh = _snapshot_hash(dvers, fvers)
        sid = _snapshot_id(sh)
        rec = ResearchSnapshot(
            snapshot_id=sid, dataset_versions=dvers, feature_versions=fvers, snapshot_hash=sh,
            created_at=now, dataset_count=len(datasets), feature_count=len(features),
            input_hash=sh, previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.snapshot_exists(sid):
            head = ledger.snapshots_head()
            ledger.append_snapshot(_seal(rec, head["record_hash"] if head else GENESIS))
        return ResearchSnapshot(**rec)

    # ── 6. Summary ──
    def summary(self, now: str = "") -> ResearchDataSummary:
        datasets = self._active_datasets()
        features = self._active_features()
        qrs = ledger.read_quality_reports()
        scores = [int(q.get("quality_score", 0)) for q in qrs]
        avg = round(sum(scores) / len(scores), 2) if scores else 0.0
        failed = sum(1 for q in qrs if q.get("status") == "FAILED")
        return ResearchDataSummary(
            timestamp=now, dataset_count=len(datasets), feature_count=len(features),
            quality_report_count=len(qrs), average_quality_score=avg, failed_datasets=failed,
            lineage_count=len(ledger.read_lineage()), snapshot_count=len(ledger.read_snapshots()))
