"""Model Management Engine (P43) — AI/ML 모델 생애주기 관리. **라이브 배포 없음, 동작 없음.**

모델·버전·검증·성능·메타를 기록·관리한다. **라이브 배포 없음 — 연구용 관리만.** execution/broker/live_trading/
portfolio_execution import·호출 없음. MANAGED ≠ DEPLOYED · AVAILABLE_FOR_RESEARCH ≠ LIVE. 결정적·불변·append-only·
이벤트 소싱. 상위 계층은 READ ONLY.
"""
from __future__ import annotations

from jarvis.model_management import ledger
from jarvis.model_management import models as M
from jarvis.model_management.models import (
    GENESIS,
    ArtifactRecord,
    IllegalModelTransition,
    ModelEventRecord,
    ModelMetadataRecord,
    ModelReportRecord,
    ModelSummary,
    ModelVersionRecord,
    PerformanceRecord,
    UnknownEntityError,
    ValidationResultRecord,
    content_hash,
    input_digest,
)

_DISCLAIMER = ("Model Management Layer 데이터 — MANAGED ≠ DEPLOYED · AVAILABLE_FOR_RESEARCH ≠ LIVE. "
               "AI/ML 모델 생애주기·검증·성능·메타 관리 전용 — 라이브 배포·거래·실행·자본 배분 없음. 연구용 관리만.")


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ModelManagementEngine:
    """모델 관리 엔진. 불변·append-only·이벤트 소싱·결정적. 라이브 배포/거래/실행/배분 권한 없음."""

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

    # ══════════════ 모델 생애주기(event-sourced) ══════════════
    def _model_event(self, mdl, name, mtype, frm, to, note, now, *, commit):
        seq = len(ledger.model_events(mdl))
        eid = M.model_event_id(mdl, to, seq)
        rec = ModelEventRecord(
            model_event_id=eid, model_id=mdl, name=name, model_type=mtype, from_state=frm,
            to_state=to, note=note, occurred_at=now, input_hash=input_digest(mdl, to, seq),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.model_event_exists, ledger.models_head, ledger.append_model_event,
                         eid, rec, commit=commit)
        return ModelEventRecord(**rec)

    def model_state(self, mdl) -> str | None:
        evs = ledger.model_events(mdl)
        return evs[-1].get("to_state") if evs else None

    def _model_meta(self, mdl) -> dict:
        evs = ledger.model_events(mdl)
        if not evs:
            raise UnknownEntityError(f"미등록 모델 {mdl}")
        g = evs[0]
        return {"name": g.get("name"), "model_type": g.get("model_type"),
                "state": evs[-1].get("to_state")}

    def _model_transition(self, mdl, to, note, now, *, commit):
        m = self._model_meta(mdl)
        frm = m["state"]
        if not M.can_model_transition(frm, to):
            raise IllegalModelTransition(f"모델 {mdl} {frm}→{to} 불가")
        return self._model_event(mdl, m["name"], m["model_type"], frm, to, note, now, commit=commit)

    def register_model(self, name, model_type, now="", *, commit=False) -> ModelEventRecord:
        """모델 등록(genesis REGISTERED, 이벤트 소싱)."""
        if model_type not in M.MODEL_TYPES:
            raise ValueError(f"미지원 model_type {model_type}")
        mdl = M.model_id(name)
        evs = ledger.model_events(mdl)
        if evs:
            return ModelEventRecord(**{k: v for k, v in evs[0].items()
                                       if k in ModelEventRecord.__dataclass_fields__})
        ev = self._model_event(mdl, name, model_type, GENESIS, M.M_REGISTERED, "registered", now,
                               commit=commit)
        self._artifact(M.ART_MODEL, mdl, "", now, commit=commit)
        return ev

    def mark_validated(self, mdl, note="validated", now="", *, commit=False):
        return self._model_transition(mdl, M.M_VALIDATED, note, now, commit=commit)

    def mark_available(self, mdl, note="available_for_research", now="", *, commit=False):
        return self._model_transition(mdl, M.M_AVAILABLE, note, now, commit=commit)

    def archive_model(self, mdl, note="archived", now="", *, commit=False):
        return self._model_transition(mdl, M.M_ARCHIVED, note, now, commit=commit)

    # ══════════════ create_version ══════════════
    def create_version(self, mdl, version, payload=None, framework="", now="",
                       *, commit=False) -> ModelVersionRecord:
        """모델 버전 생성(내용 해시·계보). **메타·해시만 — 배포 아님.**"""
        self._model_meta(mdl)
        vid = M.version_id(mdl, version)
        existing = next((v for v in ledger.versions_for(mdl) if v.get("version_id") == vid), None)
        if existing:
            return ModelVersionRecord(**{k: v for k, v in existing.items()
                                         if k in ModelVersionRecord.__dataclass_fields__})
        prior = ledger.versions_for(mdl)
        parent = prior[-1].get("version_id") if prior else ""
        rec = ModelVersionRecord(
            version_id=vid, model_id=mdl, version=version,
            content_hash=M.artifact_content_hash(payload), framework=framework, parent_version=parent,
            created_at=now, input_hash=input_digest(mdl, version), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.version_exists, ledger.versions_head, ledger.append_version, vid,
                         rec, commit=commit)
        self._artifact(M.ART_VERSION, vid, M.artifact_id(M.ART_MODEL, mdl), now, commit=commit)
        return ModelVersionRecord(**rec)

    # ══════════════ validate_model (검증 결과 기록 + 전이) ══════════════
    def validate_model(self, mdl, check, passed=True, score=1.0, details="", version_id="", now="",
                       *, commit=False) -> ValidationResultRecord:
        """모델 검증 결과 기록(불변). 모델 REGISTERED→VALIDATED. **검증·기록만.**"""
        self._model_meta(mdl)
        if check not in M.VALIDATION_CHECKS:
            raise ValueError(f"미지원 check {check}")
        seq = len([v for v in ledger.validations_for(mdl) if v.get("check") == check])
        vid = M.validation_id(mdl, check, seq)
        rec = ValidationResultRecord(
            validation_id=vid, model_id=mdl, version_id=version_id, check=check, passed=bool(passed),
            score=M.clamp01(score), details=details, created_at=now,
            input_hash=input_digest(mdl, check, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.validation_exists, ledger.validations_head, ledger.append_validation,
                         vid, rec, commit=commit)
        if self.model_state(mdl) == M.M_REGISTERED:
            self._model_transition(mdl, M.M_VALIDATED, f"validated:{check}", now, commit=commit)
        return ValidationResultRecord(**rec)

    # ══════════════ record_performance ══════════════
    def record_performance(self, mdl, metric, value, dataset_ref="", version_id="", now="",
                           *, commit=False) -> PerformanceRecord:
        """성능 이력 기록(불변)."""
        self._model_meta(mdl)
        seq = len([p for p in ledger.performance_for(mdl) if p.get("metric") == metric])
        pid = M.performance_id(mdl, metric, seq)
        rec = PerformanceRecord(
            performance_id=pid, model_id=mdl, version_id=version_id, metric=metric,
            value=float(value), dataset_ref=dataset_ref, created_at=now,
            input_hash=input_digest(mdl, metric, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.performance_exists, ledger.performance_head, ledger.append_performance,
                         pid, rec, commit=commit)
        return PerformanceRecord(**rec)

    # ══════════════ record_metadata ══════════════
    def record_metadata(self, mdl, key, value, now="", *, commit=False) -> ModelMetadataRecord:
        """모델 메타데이터 기록(불변)."""
        self._model_meta(mdl)
        mid = M.metadata_id(mdl, key)
        existing = next((m for m in ledger.read_metadata() if m.get("metadata_id") == mid), None)
        if existing:
            return ModelMetadataRecord(**{k: v for k, v in existing.items()
                                          if k in ModelMetadataRecord.__dataclass_fields__})
        rec = ModelMetadataRecord(metadata_id=mid, model_id=mdl, key=key, value=str(value),
                                  created_at=now, input_hash=input_digest(mdl, key),
                                  previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.metadata_exists, ledger.metadata_head, ledger.append_metadata, mid,
                         rec, commit=commit)
        return ModelMetadataRecord(**rec)

    # ══════════════ compare_models (결정적 성능 비교) ══════════════
    def compare_models(self, mdl_a, mdl_b) -> dict:
        """두 모델 최신 성능 비교(결정적 델타, READ ONLY). **비교·요약만 — 선택/배포 아님.**"""
        self._model_meta(mdl_a)
        self._model_meta(mdl_b)
        pa: dict = {}
        for p in ledger.performance_for(mdl_a):
            pa[p.get("metric")] = p.get("value")
        pb: dict = {}
        for p in ledger.performance_for(mdl_b):
            pb[p.get("metric")] = p.get("value")
        metrics = sorted(set(pa) | set(pb))
        deltas = {m: M.metric_delta(pa.get(m, 0.0), pb.get(m, 0.0)) for m in metrics}
        return {"model_a": mdl_a, "model_b": mdl_b, "metric_deltas": deltas,
                "a_state": self.model_state(mdl_a), "b_state": self.model_state(mdl_b)}

    # ══════════════ generate_report ══════════════
    def generate_report(self, scope="SYSTEM", now="", *, commit=False) -> ModelReportRecord:
        """모델 관리 리포트(모델·버전·검증·성능·메타 집계). **is_binding=False, MANAGED ≠ DEPLOYED.**"""
        models = ledger.model_ids()
        states = {m: self.model_state(m) for m in models}
        metas = {m: self._model_meta(m) for m in models}
        st_dist: dict = {}
        for st in states.values():
            st_dist[st] = st_dist.get(st, 0) + 1
        ty_dist: dict = {}
        for m in models:
            ty_dist[metas[m]["model_type"]] = ty_dist.get(metas[m]["model_type"], 0) + 1
        rid = M.report_id(scope, now)
        rec = ModelReportRecord(
            report_id=rid, scope=scope, model_count=len(models),
            available_model_count=sum(1 for st in states.values() if st == M.M_AVAILABLE),
            version_count=len(ledger.read_versions()),
            validation_count=len(ledger.read_validations()),
            performance_count=len(ledger.read_performance()),
            metadata_count=len(ledger.read_metadata()),
            type_distribution=dict(sorted(ty_dist.items())),
            state_distribution=dict(sorted(st_dist.items())), is_binding=False, disclaimer=_DISCLAIMER,
            created_at=now, input_hash=input_digest(scope, now), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.report_exists, ledger.reports_head, ledger.append_report, rid, rec,
                         commit=commit)
        self._artifact(M.ART_REPORT, rid, "", now, commit=commit)
        return ModelReportRecord(**rec)

    def verify_integrity(self) -> dict:
        from jarvis.model_management.verify import verify_chain
        return verify_chain()

    def list_models(self) -> list:
        return ledger.model_ids()

    def models_in_state(self, state) -> list:
        return sorted(m for m in ledger.model_ids() if self.model_state(m) == state)

    def summary(self, now="") -> ModelSummary:
        return ModelSummary(
            timestamp=now, model_event_count=len(ledger.read_model_events()),
            model_count=len(ledger.model_ids()), version_count=len(ledger.read_versions()),
            validation_count=len(ledger.read_validations()),
            performance_count=len(ledger.read_performance()),
            metadata_count=len(ledger.read_metadata()), report_count=len(ledger.read_reports()),
            artifact_count=len(ledger.read_artifacts()))
