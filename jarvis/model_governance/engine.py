"""Model Governance Engine (P9.9) — 모델 생명주기 관리·감사. **실행/학습/배포 없음.**

모델/버전을 불변으로 등록하고 생명주기 상태머신(DRAFT→TRAINED→EVALUATED→APPROVED→
DEPLOYED_CANDIDATE→RETIRED)을 관리하며 학습메타·평가·승인·배포기록·drift 를 남긴다.
**모델 실행·학습 실행·배포 실행·trading decision 없음.** APPROVED/DEPLOYED_CANDIDATE 는 기록일
뿐 실제 모델/거래 시스템 무변경. execution/broker/portfolio import 없음. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.model_governance import ledger
from jarvis.model_governance.models import (
    APPROVE,
    APPROVED,
    DEPLOYED_CANDIDATE,
    DRAFT,
    EVALUATED,
    GENESIS,
    REJECTED,
    RETIRED,
    TRAINED,
    ApprovalError,
    DeploymentRecord,
    EvaluationReport,
    IllegalTransition,
    ImmutableModelError,
    ImmutableVersionError,
    ModelApproval,
    ModelDriftReport,
    ModelGovernanceReport,
    ModelMetadata,
    ModelVersion,
    TrainingRun,
    approval_id,
    can_transition,
    content_hash,
    deployment_id,
    drift_level,
    drift_report_id,
    evaluation_id,
    evaluation_verdict,
    input_digest,
    is_valid_decision,
    is_valid_drift_type,
    model_hash as _model_hash,
    relative_change,
    training_run_id,
    version_event_id,
    version_hash as _version_hash,
    version_key as _vkey,
)


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ModelGovernanceEngine:
    """모델 거버넌스 엔진. 불변·append-only·결정적. 실행/학습/배포/거래 없음."""

    # ── register_model ──
    def register_model(self, model_id: str, name: str, description: str, model_type: str,
                       task: str, owner: str, now: str = "",
                       *, commit: bool = False) -> ModelMetadata:
        mh = _model_hash(model_id, name, model_type, task, description)
        for m in ledger.read_models():
            if m.get("model_id") == model_id:
                if m.get("model_hash") != mh:
                    raise ImmutableModelError(f"{model_id} 는 불변 — 메타 변경 불가")
                return ModelMetadata(**{k: v for k, v in m.items()
                                        if k in ModelMetadata.__dataclass_fields__})
        rec = ModelMetadata(
            model_id=model_id, name=name, description=description, model_type=model_type,
            task=task, owner=owner, created_at=now, model_hash=mh, input_hash=mh,
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.model_hash_exists(mh):
            head = ledger.models_head()
            ledger.append_model(_seal(rec, head["record_hash"] if head else GENESIS))
        return ModelMetadata(**rec)

    # ── 버전 생명주기(이벤트 소싱) ──
    def _version_meta(self, vkey: str) -> dict | None:
        evs = ledger.version_events_for(vkey)
        return evs[0] if evs else None

    def current_state(self, vkey: str) -> str:
        evs = ledger.version_events_for(vkey)
        return evs[-1].get("to_state", "") if evs else ""

    def _emit_version(self, vkey: str, meta: dict, frm: str, to: str, now: str,
                      *, actor: str, commit: bool) -> dict:
        if not can_transition(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단")
        eid = version_event_id(vkey, frm, to)
        rec = ModelVersion(
            version_id=eid, version_key=vkey, model_id=meta["model_id"],
            version=meta["version"], framework=meta["framework"],
            version_hash=meta["version_hash"], from_state=frm, to_state=to, status=to,
            created_at=now, actor=actor, input_hash=input_digest(vkey, frm, to),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.version_event_exists(eid):
            head = ledger.versions_head()
            ledger.append_version(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def create_version(self, model_id: str, version: str, framework: str, params: dict,
                       now: str = "", *, commit: bool = False) -> ModelVersion:
        vkey = _vkey(model_id, version)
        vh = _version_hash(model_id, version, framework, params)
        existing = ledger.version_events_for(vkey)
        if existing:
            if existing[0].get("version_hash") != vh:
                raise ImmutableVersionError(f"{vkey} 는 불변 — 버전 내용 변경 불가")
            return ModelVersion(**existing[-1])   # 멱등: 현재 상태 반환
        meta = {"model_id": model_id, "version": version, "framework": framework,
                "version_hash": vh}
        rec = self._emit_version(vkey, meta, "", DRAFT, now, actor="system", commit=commit)
        return ModelVersion(**rec)

    def _advance(self, vkey: str, to: str, now: str, *, actor: str, commit: bool) -> dict:
        meta = self._version_meta(vkey)
        if meta is None:
            raise IllegalTransition(f"미존재 버전 {vkey}")
        return self._emit_version(vkey, meta, self.current_state(vkey), to, now,
                                  actor=actor, commit=commit)

    # ── record_training (DRAFT→TRAINED) ──
    def record_training(self, model_id: str, version: str, dataset_ref: str,
                        training_params: dict, duration_seconds: float = 0.0, now: str = "",
                        *, commit: bool = False) -> TrainingRun:
        vkey = _vkey(model_id, version)
        ih = input_digest(vkey, dataset_ref, sorted((training_params or {}).items()))
        rid = training_run_id(vkey, ih)
        rec = TrainingRun(
            run_id=rid, version_key=vkey, dataset_ref=dataset_ref,
            training_params=dict(training_params or {}), duration_seconds=float(duration_seconds),
            status="RECORDED", created_at=now, input_hash=ih, previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.training_exists(rid):
            head = ledger.training_head()
            ledger.append_training(_seal(rec, head["record_hash"] if head else GENESIS))
        self._advance(vkey, TRAINED, now, actor="trainer", commit=commit)
        return TrainingRun(**rec)

    # ── record_evaluation (TRAINED→EVALUATED) ──
    def record_evaluation(self, model_id: str, version: str, *, accuracy: float = 0.0,
                          sharpe: float = 0.0, max_drawdown: float = 0.0,
                          stability: float = 0.0, validation_period: str = "",
                          benchmark_comparison: dict | None = None,
                          confidence_score: float = 0.0, now: str = "",
                          commit: bool = False) -> EvaluationReport:
        vkey = _vkey(model_id, version)
        verdict = evaluation_verdict(accuracy, sharpe, max_drawdown, stability, confidence_score)
        ih = input_digest(vkey, accuracy, sharpe, max_drawdown, stability, confidence_score,
                          validation_period)
        rid = evaluation_id(vkey, ih)
        rec = EvaluationReport(
            report_id=rid, version_key=vkey, accuracy=float(accuracy), sharpe=float(sharpe),
            max_drawdown=float(max_drawdown), stability=float(stability),
            validation_period=validation_period,
            benchmark_comparison=dict(benchmark_comparison or {}),
            confidence_score=float(confidence_score), verdict=verdict, created_at=now,
            input_hash=ih, previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.evaluation_exists(rid):
            head = ledger.evaluations_head()
            ledger.append_evaluation(_seal(rec, head["record_hash"] if head else GENESIS))
        self._advance(vkey, EVALUATED, now, actor="evaluator", commit=commit)
        return EvaluationReport(**rec)

    # ── approve_model (EVALUATED→APPROVED/REJECTED) ──
    def approve_model(self, model_id: str, version: str, approver: str, decision: str,
                      rationale: str = "", evaluation_ref: str = "", now: str = "",
                      *, commit: bool = False) -> ModelApproval:
        if not approver:
            raise ApprovalError("승인자 필요")
        if not is_valid_decision(decision):
            raise ApprovalError(f"허용되지 않은 결정: {decision}")
        vkey = _vkey(model_id, version)
        cur = self.current_state(vkey)
        if cur != EVALUATED:
            raise IllegalTransition(f"승인은 EVALUATED 에서만 가능(현재 {cur})")
        aid = approval_id(vkey, approver, decision)
        rec = ModelApproval(
            approval_id=aid, version_key=vkey, approver=approver, decision=decision,
            rationale=rationale, evaluation_ref=evaluation_ref, created_at=now,
            input_hash=input_digest(vkey, approver, decision), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.approval_exists(aid):
            head = ledger.approvals_head()
            ledger.append_approval(_seal(rec, head["record_hash"] if head else GENESIS))
        self._advance(vkey, APPROVED if decision == APPROVE else REJECTED, now,
                      actor=approver, commit=commit)
        return ModelApproval(**rec)

    # ── record_deployment (APPROVED→DEPLOYED_CANDIDATE) ──
    def record_deployment(self, model_id: str, version: str, environment: str,
                          deployed_by: str, note: str = "", now: str = "",
                          *, commit: bool = False) -> DeploymentRecord:
        """**실제 배포 아님 — 배포 후보 기록만.** 모델/거래 시스템 무변경."""
        vkey = _vkey(model_id, version)
        cur = self.current_state(vkey)
        if cur != APPROVED:
            raise IllegalTransition(f"배포기록은 APPROVED 에서만 가능(현재 {cur})")
        did = deployment_id(vkey, environment)
        rec = DeploymentRecord(
            deployment_id=did, version_key=vkey, environment=environment,
            deployed_by=deployed_by, status="CANDIDATE_RECORDED", note=note, created_at=now,
            input_hash=input_digest(vkey, environment), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.deployment_exists(did):
            head = ledger.deployments_head()
            ledger.append_deployment(_seal(rec, head["record_hash"] if head else GENESIS))
        self._advance(vkey, DEPLOYED_CANDIDATE, now, actor=deployed_by, commit=commit)
        return DeploymentRecord(**rec)

    def retire_version(self, model_id: str, version: str, now: str = "",
                       *, actor: str = "operator", commit: bool = False) -> dict:
        vkey = _vkey(model_id, version)
        return self._advance(vkey, RETIRED, now, actor=actor, commit=commit)

    # ── detect_model_drift ──
    def detect_model_drift(self, model_id: str, version: str, drift_type: str, *,
                           baseline: float = 0.0, current: float = 0.0,
                           drift_score: float | None = None, warning_threshold: float = 0.1,
                           critical_threshold: float = 0.25, now: str = "",
                           commit: bool = False) -> ModelDriftReport:
        if not is_valid_drift_type(drift_type):
            raise ValueError(f"허용되지 않은 drift 유형: {drift_type}")
        if drift_score is None:
            drift_score = relative_change(baseline, current)
        drift_score = round(float(drift_score), 8)
        level = drift_level(drift_score, warning_threshold, critical_threshold)
        findings = [] if level == "NO_DRIFT" else [
            f"{drift_type}:{level}:score={drift_score}"]
        ih = input_digest(model_id, version, drift_type, drift_score, baseline, current)
        rid = drift_report_id(model_id, drift_type, ih)
        rec = ModelDriftReport(
            report_id=rid, model_id=model_id, version=version, drift_type=drift_type,
            drift_score=drift_score, drift_level=level, baseline=float(baseline),
            current=float(current), findings=findings, created_at=now, input_hash=ih,
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.drift_exists(rid):
            head = ledger.drift_head()
            ledger.append_drift(_seal(rec, head["record_hash"] if head else GENESIS))
        return ModelDriftReport(**rec)

    # ── generate_governance_report ──
    def generate_governance_report(self, now: str = "") -> ModelGovernanceReport:
        models = {m.get("model_id") for m in ledger.read_models()}
        vkeys = {r.get("version_key") for r in ledger.read_versions()}
        dist: dict = {}
        for vk in vkeys:
            st = self.current_state(vk)
            dist[st] = dist.get(st, 0) + 1
        approved = dist.get(APPROVED, 0)
        deployed = dist.get(DEPLOYED_CANDIDATE, 0)
        drifts = ledger.read_drift()
        crit = sum(1 for d in drifts if d.get("drift_level") == "CRITICAL_DRIFT")
        warn = sum(1 for d in drifts if d.get("drift_level") == "WARNING_DRIFT")
        confs = [float(e.get("confidence_score", 0.0)) for e in ledger.read_evaluations()]
        avg_conf = round(sum(confs) / len(confs), 4) if confs else 0.0
        return ModelGovernanceReport(
            timestamp=now, model_count=len(models), version_count=len(vkeys),
            state_distribution=dict(sorted(dist.items())), approved_count=approved,
            deployed_candidate_count=deployed, drift_critical=crit, drift_warning=warn,
            average_confidence=avg_conf)
