"""Real Data Infrastructure Engine (P41) — 시장 연구 데이터 인프라. **거래 연결 없음, 동작 없음.**

데이터 수집·역사적 저장·검증·버전관리·피처 준비를 메타·해시로 기록한다. **거래·실행·배포·배분을 하지 않는다.**
execution/broker/live_trading/portfolio_execution import·호출 없음. DATA ≠ TRADING · METADATA ≠ EXECUTION.
결정적·불변·append-only·이벤트 소싱·재현. 상위 계층은 READ ONLY.
"""
from __future__ import annotations

from jarvis.data_infrastructure import ledger
from jarvis.data_infrastructure import models as M
from jarvis.data_infrastructure.models import (
    GENESIS,
    ArtifactRecord,
    DataInfraReportRecord,
    DataInfraSummary,
    DataSourceRecord,
    DatasetEventRecord,
    DatasetVersionRecord,
    FeatureSetRecord,
    IllegalDatasetTransition,
    QualityReportRecord,
    UnknownEntityError,
    content_hash,
    input_digest,
)

_DISCLAIMER = ("Real Data Infrastructure 데이터 — DATA ≠ TRADING · METADATA ≠ EXECUTION. 시장 연구 데이터 "
               "수집·저장·검증·버전관리·피처 준비 메타 전용 — 거래·실행·배포·자본 배분 없음. 데이터 계보·해시 검증·재현 보장.")


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class DataInfrastructureEngine:
    """데이터 인프라 엔진. 불변·append-only·이벤트 소싱·결정적. 거래/실행/배포/배분 권한 없음."""

    def _emit(self, exists_fn, head_fn, append_fn, rid, rec, *, commit) -> dict:
        rec = dict(rec)
        rec["record_hash"] = content_hash(rec)
        if commit and not exists_fn(rid):
            head = head_fn()
            append_fn(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def _artifact(self, atype, ref, parent, now, *, commit) -> ArtifactRecord:
        aid = M.artifact_id(atype, ref)
        rec = ArtifactRecord(artifact_id=aid, artifact_type=atype, ref_id=ref, parent_artifact=parent,
                             created_at=now, input_hash=input_digest(atype, ref),
                             previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.artifact_exists, ledger.artifacts_head, ledger.append_artifact,
                         aid, rec, commit=commit)
        return ArtifactRecord(**rec)

    # ══════════════ register_source ══════════════
    def register_source(self, source_type, name, uri_ref="", description="", now="",
                        *, commit=False) -> DataSourceRecord:
        """데이터 소스 등록(불변). **메타 기록만 — 실시간 연결 아님.**"""
        if source_type not in M.SOURCE_TYPES:
            raise ValueError(f"미지원 source_type {source_type}")
        sid = M.source_id(source_type, name)
        existing = ledger.source_by_id(sid)
        if existing:
            return DataSourceRecord(**{k: v for k, v in existing.items()
                                       if k in DataSourceRecord.__dataclass_fields__})
        rec = DataSourceRecord(source_id=sid, name=name, source_type=source_type, uri_ref=uri_ref,
                               description=description, created_at=now,
                               input_hash=input_digest(source_type, name),
                               previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.source_exists, ledger.sources_head, ledger.append_source, sid, rec,
                         commit=commit)
        self._artifact(M.ART_SOURCE, sid, "", now, commit=commit)
        return DataSourceRecord(**rec)

    # ══════════════ 데이터셋 생애주기(event-sourced) ══════════════
    def _dataset_event(self, ds, name, source, frm, to, note, now, *, commit):
        seq = len(ledger.dataset_events(ds))
        eid = M.dataset_event_id(ds, to, seq)
        rec = DatasetEventRecord(
            dataset_event_id=eid, dataset_id=ds, name=name, source_id=source, from_state=frm,
            to_state=to, note=note, occurred_at=now, input_hash=input_digest(ds, to, seq),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.dataset_event_exists, ledger.datasets_head,
                         ledger.append_dataset_event, eid, rec, commit=commit)
        return DatasetEventRecord(**rec)

    def dataset_state(self, ds) -> str | None:
        evs = ledger.dataset_events(ds)
        return evs[-1].get("to_state") if evs else None

    def _dataset_meta(self, ds) -> dict:
        evs = ledger.dataset_events(ds)
        if not evs:
            raise UnknownEntityError(f"미등록 데이터셋 {ds}")
        g = evs[0]
        return {"name": g.get("name"), "source_id": g.get("source_id"),
                "state": evs[-1].get("to_state")}

    def _dataset_transition(self, ds, to, note, now, *, commit):
        m = self._dataset_meta(ds)
        frm = m["state"]
        if not M.can_dataset_transition(frm, to):
            raise IllegalDatasetTransition(f"데이터셋 {ds} {frm}→{to} 불가")
        return self._dataset_event(ds, m["name"], m["source_id"], frm, to, note, now, commit=commit)

    def create_dataset(self, name, source_id="", now="", *, commit=False) -> DatasetEventRecord:
        """데이터셋 생성(genesis CREATED, 이벤트 소싱)."""
        ds = M.dataset_id(name)
        evs = ledger.dataset_events(ds)
        if evs:
            return DatasetEventRecord(**{k: v for k, v in evs[0].items()
                                         if k in DatasetEventRecord.__dataclass_fields__})
        if source_id and not ledger.source_by_id(source_id):
            raise UnknownEntityError(f"미등록 소스 {source_id}")
        ev = self._dataset_event(ds, name, source_id, GENESIS, M.D_CREATED, "created", now,
                                 commit=commit)
        parent = M.artifact_id(M.ART_SOURCE, source_id) if source_id else ""
        if source_id and not ledger.source_by_id(source_id):
            parent = ""
        self._artifact(M.ART_DATASET, ds, parent, now, commit=commit)
        return ev

    def validate_dataset(self, ds, note="validated", now="", *, commit=False):
        return self._dataset_transition(ds, M.D_VALIDATED, note, now, commit=commit)

    def mark_available(self, ds, note="available", now="", *, commit=False):
        return self._dataset_transition(ds, M.D_AVAILABLE, note, now, commit=commit)

    def archive_dataset(self, ds, note="archived", now="", *, commit=False):
        return self._dataset_transition(ds, M.D_ARCHIVED, note, now, commit=commit)

    # ══════════════ create_version (재현성·계보) ══════════════
    def create_version(self, ds, version, payload=None, row_count=0, schema=None, now="",
                       *, commit=False) -> DatasetVersionRecord:
        """데이터셋 버전 생성(내용 해시·계보). **재현성 보장 — 데이터 자체는 저장하지 않고 해시·메타만.**"""
        self._dataset_meta(ds)
        vid = M.version_id(ds, version)
        existing = next((v for v in ledger.versions_for(ds) if v.get("version_id") == vid), None)
        if existing:
            return DatasetVersionRecord(**{k: v for k, v in existing.items()
                                           if k in DatasetVersionRecord.__dataclass_fields__})
        prior = ledger.versions_for(ds)
        parent = prior[-1].get("version_id") if prior else ""
        rec = DatasetVersionRecord(
            version_id=vid, dataset_id=ds, version=version,
            content_hash=M.data_content_hash(payload), row_count=int(row_count),
            schema_hash=M.data_content_hash(schema), parent_version=parent, created_at=now,
            input_hash=input_digest(ds, version), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.version_exists, ledger.versions_head, ledger.append_version, vid,
                         rec, commit=commit)
        self._artifact(M.ART_VERSION, vid, M.artifact_id(M.ART_DATASET, ds), now, commit=commit)
        return DatasetVersionRecord(**rec)

    # ══════════════ prepare_features ══════════════
    def prepare_features(self, ds, name, features, version_id="", description="", now="",
                         *, commit=False) -> FeatureSetRecord:
        """피처셋 준비(메타). **피처 메타 기록만 — 실행 아님.**"""
        self._dataset_meta(ds)
        fid = M.feature_set_id(ds, name)
        existing = next((f for f in ledger.read_features() if f.get("feature_set_id") == fid), None)
        if existing:
            return FeatureSetRecord(**{k: v for k, v in existing.items()
                                       if k in FeatureSetRecord.__dataclass_fields__})
        rec = FeatureSetRecord(feature_set_id=fid, dataset_id=ds, version_id=version_id,
                               features=list(features), description=description, created_at=now,
                               input_hash=input_digest(ds, name), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.feature_exists, ledger.features_head, ledger.append_feature, fid,
                         rec, commit=commit)
        self._artifact(M.ART_FEATURE, fid, M.artifact_id(M.ART_DATASET, ds), now, commit=commit)
        return FeatureSetRecord(**rec)

    # ══════════════ record_quality ══════════════
    def record_quality(self, ds, dimension, score, passed=True, issues=None, version_id="", now="",
                       *, commit=False) -> QualityReportRecord:
        """품질 리포트 기록(불변). **검증 기록만.**"""
        self._dataset_meta(ds)
        if dimension not in M.QUALITY_DIMENSIONS:
            raise ValueError(f"미지원 dimension {dimension}")
        seq = len([q for q in ledger.quality_for(ds) if q.get("dimension") == dimension])
        qid = M.quality_id(ds, dimension, seq)
        rec = QualityReportRecord(
            quality_id=qid, dataset_id=ds, version_id=version_id, dimension=dimension,
            score=M.clamp01(score), passed=bool(passed), issues=list(issues or []), created_at=now,
            input_hash=input_digest(ds, dimension, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.quality_exists, ledger.quality_head, ledger.append_quality, qid,
                         rec, commit=commit)
        return QualityReportRecord(**rec)

    # ══════════════ generate_report ══════════════
    def generate_report(self, scope="SYSTEM", now="", *, commit=False) -> DataInfraReportRecord:
        """데이터 인프라 리포트(소스·데이터셋·버전·피처·품질 집계). **is_binding=False, DATA ≠ TRADING.**"""
        sources = ledger.read_sources()
        datasets = ledger.dataset_ids()
        states = {d: self.dataset_state(d) for d in datasets}
        st_dist: dict = {}
        for st in states.values():
            st_dist[st] = st_dist.get(st, 0) + 1
        src_dist: dict = {}
        for s in sources:
            src_dist[s.get("source_type")] = src_dist.get(s.get("source_type"), 0) + 1
        rid = M.report_id(scope, now)
        rec = DataInfraReportRecord(
            report_id=rid, scope=scope, source_count=len(sources), dataset_count=len(datasets),
            available_dataset_count=sum(1 for st in states.values() if st == M.D_AVAILABLE),
            version_count=len(ledger.read_versions()), feature_set_count=len(ledger.read_features()),
            quality_count=len(ledger.read_quality()),
            source_type_distribution=dict(sorted(src_dist.items())),
            state_distribution=dict(sorted(st_dist.items())), is_binding=False, disclaimer=_DISCLAIMER,
            created_at=now, input_hash=input_digest(scope, now), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.report_exists, ledger.reports_head, ledger.append_report, rid, rec,
                         commit=commit)
        self._artifact(M.ART_REPORT, rid, "", now, commit=commit)
        return DataInfraReportRecord(**rec)

    def verify_integrity(self) -> dict:
        from jarvis.data_infrastructure.verify import verify_chain
        return verify_chain()

    def list_datasets(self) -> list:
        return ledger.dataset_ids()

    def datasets_in_state(self, state) -> list:
        return sorted(d for d in ledger.dataset_ids() if self.dataset_state(d) == state)

    def summary(self, now="") -> DataInfraSummary:
        return DataInfraSummary(
            timestamp=now, source_count=len(ledger.read_sources()),
            dataset_event_count=len(ledger.read_dataset_events()),
            dataset_count=len(ledger.dataset_ids()), version_count=len(ledger.read_versions()),
            feature_set_count=len(ledger.read_features()), quality_count=len(ledger.read_quality()),
            report_count=len(ledger.read_reports()), artifact_count=len(ledger.read_artifacts()))
