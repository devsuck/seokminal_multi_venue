"""P9.9 Model Governance & AI Oversight 테스트. **관리·감사 전용.**

레지스트리(불변)·버전·생명주기 상태머신(DRAFT→...→RETIRED, 차단전이)·학습메타·평가(verdict 기록)·
승인·배포기록(record-only)·drift(feature/prediction/performance, NO/WARNING/CRITICAL)·거버넌스
리포트·verify(체인/변조/중복)·replay·CLI·보안(금지import·집행/브로커 없음·자동배포 없음·기존 원장
무변경·삭제 API 없음·불변·append-only).

패키지 내부 tests/ — 상위 tests/conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from jarvis.model_governance import ledger
from jarvis.model_governance import models as M
from jarvis.model_governance.engine import ModelGovernanceEngine
from jarvis.model_governance.models import (
    APPROVE,
    APPROVED,
    CRITICAL_DRIFT,
    DEPLOYED_CANDIDATE,
    DRAFT,
    EVALUATED,
    FAIL,
    FEATURE_DRIFT,
    NO_DRIFT,
    PASS,
    PERFORMANCE_DRIFT,
    PREDICTION_DRIFT,
    REJECT,
    REJECTED,
    RETIRED,
    TRAINED,
    WARN,
    WARNING_DRIFT,
    ApprovalError,
    IllegalTransition,
    ImmutableModelError,
    ImmutableVersionError,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.model_governance.ledger.state_path", sp)
    return sp


def _eng():
    return ModelGovernanceEngine()


def _reg(eng, mid="M1", commit=True):
    return eng.register_model(mid, f"{mid} name", "desc", "xgboost", "classification",
                              "quant", T0, commit=commit)


def _ver(eng, mid="M1", v="1", params=None, commit=True):
    return eng.create_version(mid, v, "xgboost-2", params or {"lr": 0.1}, T0, commit=commit)


def _to_trained(eng, mid="M1", v="1"):
    _reg(eng, mid)
    _ver(eng, mid, v)
    eng.record_training(mid, v, "ds@1", {"lr": 0.1}, 12.0, T0, commit=True)


def _to_evaluated(eng, mid="M1", v="1", **ev):
    _to_trained(eng, mid, v)
    kw = dict(accuracy=0.9, sharpe=1.5, max_drawdown=-0.1, stability=0.8,
              confidence_score=0.85, validation_period="2020-2024")
    kw.update(ev)
    eng.record_evaluation(mid, v, now=T0, commit=True, **kw)


def _to_approved(eng, mid="M1", v="1"):
    _to_evaluated(eng, mid, v)
    eng.approve_model(mid, v, "cro", APPROVE, "ok", now=T0, commit=True)


# ── 1~13. models 순수 ──
def test_can_transition_allowed():
    assert M.can_transition("", DRAFT) and M.can_transition(DRAFT, TRAINED)
    assert M.can_transition(TRAINED, EVALUATED) and M.can_transition(EVALUATED, APPROVED)
    assert M.can_transition(APPROVED, DEPLOYED_CANDIDATE)
    assert M.can_transition(DEPLOYED_CANDIDATE, RETIRED)


def test_can_transition_blocked():
    assert not M.can_transition(DRAFT, EVALUATED)
    assert not M.can_transition(TRAINED, APPROVED)
    assert not M.can_transition(RETIRED, DRAFT)
    assert not M.can_transition(REJECTED, APPROVED)


def test_model_hash_deterministic():
    assert M.model_hash("M", "n", "t", "task", "d") == M.model_hash("M", "n", "t", "task", "d")


def test_version_hash_deterministic():
    assert M.version_hash("M", "1", "fw", {"a": 1}) == M.version_hash("M", "1", "fw", {"a": 1})


def test_content_hash_excludes():
    a = {"x": 1, "previous_hash": "p1", "record_hash": "r1"}
    b = {"x": 1, "previous_hash": "p2", "record_hash": "r2"}
    assert M.content_hash(a) == M.content_hash(b)


def test_version_key():
    assert M.version_key("M1", "2") == "M1@2"


def test_is_valid_decision():
    assert M.is_valid_decision(APPROVE) and not M.is_valid_decision("AUTO_DEPLOY")


def test_is_valid_drift_type():
    assert M.is_valid_drift_type(FEATURE_DRIFT) and not M.is_valid_drift_type("X")


def test_evaluation_verdict_pass():
    assert M.evaluation_verdict(0.9, 1.5, -0.1, 0.8, 0.8) == PASS


def test_evaluation_verdict_fail():
    assert M.evaluation_verdict(0.9, 0.3, -0.1, 0.8, 0.8) == FAIL   # sharpe<0.5


def test_evaluation_verdict_warn():
    assert M.evaluation_verdict(0.9, 0.8, -0.1, 0.6, 0.6) == WARN


def test_drift_level_thresholds():
    assert M.drift_level(0.05, 0.1, 0.25) == NO_DRIFT
    assert M.drift_level(0.15, 0.1, 0.25) == WARNING_DRIFT
    assert M.drift_level(0.30, 0.1, 0.25) == CRITICAL_DRIFT


def test_relative_change():
    assert round(M.relative_change(1.0, 0.7), 4) == 0.3


# ── 14~17. Model Registry ──
def test_register_model_creates(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    m = _reg(_eng(), commit=False)
    assert m.model_id == "M1" and m.model_hash.startswith("sha256:")


def test_register_commit_appends(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _reg(_eng())
    assert len(ledger.read_models()) == 1


def test_register_duplicate_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng)
    _reg(eng)
    assert len(ledger.read_models()) == 1


def test_register_immutable_violation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng, mid="M1")
    with pytest.raises(ImmutableModelError):
        eng.register_model("M1", "DIFFERENT", "d", "xgboost", "classification", "quant", T0,
                           commit=True)


# ── 18~22. Version ──
def test_create_version_draft(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng)
    v = _ver(eng)
    assert v.to_state == DRAFT and eng.current_state("M1@1") == DRAFT


def test_version_commit_appends(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng)
    _ver(eng, v="1")
    assert len(ledger.read_versions()) == 1


def test_version_duplicate_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng)
    _ver(eng, v="1")
    _ver(eng, v="1")
    assert len(ledger.version_events_for("M1@1")) == 1


def test_version_immutable_violation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng)
    _ver(eng, v="1", params={"lr": 0.1})
    with pytest.raises(ImmutableVersionError):
        _ver(eng, v="1", params={"lr": 0.9})


def test_current_state_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().current_state("GHOST@1") == ""


# ── 23~27. Training ──
def test_training_transitions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng)
    _ver(eng)
    eng.record_training("M1", "1", "ds@1", {"lr": 0.1}, 5.0, T0, commit=True)
    assert eng.current_state("M1@1") == TRAINED


def test_training_records_run(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng)
    _ver(eng)
    r = eng.record_training("M1", "1", "ds@1", {"lr": 0.1}, 5.0, T0, commit=True)
    assert r.status == "RECORDED" and len(ledger.read_training()) == 1


def test_training_requires_draft(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_trained(eng)   # already TRAINED
    with pytest.raises(IllegalTransition):
        eng.record_training("M1", "1", "ds@2", {}, 1.0, T1, commit=True)


def test_training_append_only(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_trained(eng)
    assert len(ledger.read_training()) == 1


def test_training_duplicate_prevention(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng)
    _ver(eng)
    eng.record_training("M1", "1", "ds@1", {"lr": 0.1}, 5.0, T0, commit=True)
    # 동일 학습 입력 재기록은 run dedup(전이는 이미 TRAINED)
    try:
        eng.record_training("M1", "1", "ds@1", {"lr": 0.1}, 5.0, T1, commit=True)
    except IllegalTransition:
        pass
    assert len(ledger.read_training()) == 1


# ── 28~33. Evaluation ──
def test_evaluation_transitions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_trained(eng)
    eng.record_evaluation("M1", "1", accuracy=0.9, sharpe=1.5, max_drawdown=-0.1,
                          stability=0.8, confidence_score=0.85, now=T0, commit=True)
    assert eng.current_state("M1@1") == EVALUATED


def test_evaluation_requires_trained(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng)
    _ver(eng)   # DRAFT
    with pytest.raises(IllegalTransition):
        eng.record_evaluation("M1", "1", sharpe=1.5, now=T0, commit=True)


def test_evaluation_verdict_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_trained(eng)
    r = eng.record_evaluation("M1", "1", accuracy=0.9, sharpe=0.3, max_drawdown=-0.1,
                              stability=0.8, confidence_score=0.85, now=T0, commit=True)
    assert r.verdict == FAIL   # 기록 라벨만


def test_evaluation_metrics_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_trained(eng)
    r = eng.record_evaluation("M1", "1", accuracy=0.9, sharpe=1.5, max_drawdown=-0.1,
                              stability=0.8, validation_period="2020-2024",
                              benchmark_comparison={"kospi": 0.05}, confidence_score=0.85,
                              now=T0, commit=True).to_dict()
    for k in ("accuracy", "sharpe", "max_drawdown", "stability", "validation_period",
              "benchmark_comparison", "confidence_score"):
        assert k in r


def test_evaluation_append_only(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_evaluated(eng)
    assert len(ledger.read_evaluations()) == 1


def test_evaluation_duplicate_prevention(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_trained(eng)
    kw = dict(accuracy=0.9, sharpe=1.5, max_drawdown=-0.1, stability=0.8, confidence_score=0.85)
    eng.record_evaluation("M1", "1", now=T0, commit=True, **kw)
    try:
        eng.record_evaluation("M1", "1", now=T1, commit=True, **kw)
    except IllegalTransition:
        pass
    assert len(ledger.read_evaluations()) == 1


# ── 34~41. Approval ──
def test_approve_requires_evaluated(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_trained(eng)   # TRAINED, not EVALUATED
    with pytest.raises(IllegalTransition):
        eng.approve_model("M1", "1", "cro", APPROVE, now=T0, commit=True)


def test_approve_missing_approver_raises(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_evaluated(eng)
    with pytest.raises(ApprovalError):
        eng.approve_model("M1", "1", "", APPROVE, now=T0, commit=True)


def test_approve_invalid_decision_raises(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_evaluated(eng)
    with pytest.raises(ApprovalError):
        eng.approve_model("M1", "1", "cro", "AUTO_DEPLOY", now=T0, commit=True)


def test_approve_transitions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_evaluated(eng)
    eng.approve_model("M1", "1", "cro", APPROVE, now=T0, commit=True)
    assert eng.current_state("M1@1") == APPROVED


def test_reject_transitions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_evaluated(eng)
    eng.approve_model("M1", "1", "cro", REJECT, now=T0, commit=True)
    assert eng.current_state("M1@1") == REJECTED


def test_approval_records(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_evaluated(eng)
    eng.approve_model("M1", "1", "cro", APPROVE, now=T0, commit=True)
    assert len(ledger.read_approvals()) == 1


def test_approval_duplicate_prevented(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_evaluated(eng)
    eng.approve_model("M1", "1", "cro", APPROVE, now=T0, commit=True)
    try:
        eng.approve_model("M1", "1", "cro", APPROVE, now=T1, commit=True)
    except IllegalTransition:
        pass
    assert len(ledger.read_approvals()) == 1


def test_approve_is_record_only(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_evaluated(eng)
    models_before = len(ledger.read_models())
    eng.approve_model("M1", "1", "cro", APPROVE, now=T0, commit=True)
    # 승인은 모델 레지스트리를 변경하지 않음(기록만)
    assert len(ledger.read_models()) == models_before


# ── 42~47. Deployment (record-only) ──
def test_deploy_requires_approved(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_evaluated(eng)   # EVALUATED, not APPROVED
    with pytest.raises(IllegalTransition):
        eng.record_deployment("M1", "1", "shadow", "ops", now=T0, commit=True)


def test_deploy_transitions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_approved(eng)
    eng.record_deployment("M1", "1", "shadow", "ops", now=T0, commit=True)
    assert eng.current_state("M1@1") == DEPLOYED_CANDIDATE


def test_deploy_record_only_status(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_approved(eng)
    r = eng.record_deployment("M1", "1", "shadow", "ops", now=T0, commit=True)
    assert r.status == "CANDIDATE_RECORDED"   # 실제 배포 아님


def test_deploy_records(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_approved(eng)
    eng.record_deployment("M1", "1", "shadow", "ops", now=T0, commit=True)
    assert len(ledger.read_deployments()) == 1


def test_deploy_duplicate_prevention(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_approved(eng)
    eng.record_deployment("M1", "1", "shadow", "ops", now=T0, commit=True)
    try:
        eng.record_deployment("M1", "1", "shadow", "ops", now=T1, commit=True)
    except IllegalTransition:
        pass
    assert len(ledger.read_deployments()) == 1


def test_deploy_no_execution_ledgers(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_approved(eng)
    eng.record_deployment("M1", "1", "shadow", "ops", now=T0, commit=True)
    # 실제 배포/거래 원장 미생성 — mg_ 원장만
    for banned in ("live_execution_requests.jsonl", "order_lifecycle_events.jsonl",
                   "paper_orders.jsonl"):
        assert not os.path.exists(sp(banned))


# ── 48~52. Lifecycle full + illegal ──
def test_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_approved(eng)
    eng.record_deployment("M1", "1", "shadow", "ops", now=T0, commit=True)
    eng.retire_version("M1", "1", T0, commit=True)
    assert eng.current_state("M1@1") == RETIRED


def test_illegal_skip_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng)
    _ver(eng)   # DRAFT
    with pytest.raises(IllegalTransition):
        eng.record_evaluation("M1", "1", sharpe=1.0, now=T0, commit=True)   # DRAFT→EVALUATED 차단


def test_illegal_from_retired(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_approved(eng)
    eng.retire_version("M1", "1", T0, commit=True)
    with pytest.raises(IllegalTransition):
        eng.record_deployment("M1", "1", "shadow", "ops", now=T0, commit=True)


def test_retire_from_approved(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_approved(eng)
    eng.retire_version("M1", "1", T0, commit=True)
    assert eng.current_state("M1@1") == RETIRED


def test_rejected_is_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_evaluated(eng)
    eng.approve_model("M1", "1", "cro", REJECT, now=T0, commit=True)
    with pytest.raises(IllegalTransition):
        eng.record_deployment("M1", "1", "shadow", "ops", now=T0, commit=True)


# ── 53~59. Drift ──
def test_feature_drift_no(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().detect_model_drift("M1", "1", FEATURE_DRIFT, baseline=100.0, current=105.0)
    assert r.drift_level == NO_DRIFT


def test_prediction_drift_warning(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().detect_model_drift("M1", "1", PREDICTION_DRIFT, baseline=0.5, current=0.575)
    assert r.drift_level == WARNING_DRIFT


def test_performance_drift_critical(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().detect_model_drift("M1", "1", PERFORMANCE_DRIFT, baseline=1.5, current=1.0)
    assert r.drift_level == CRITICAL_DRIFT   # rel change 0.33


def test_drift_invalid_type_raises(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        _eng().detect_model_drift("M1", "1", "COSMIC_DRIFT", baseline=1.0, current=2.0)


def test_drift_from_score(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().detect_model_drift("M1", "1", FEATURE_DRIFT, drift_score=0.4)
    assert r.drift_level == CRITICAL_DRIFT


def test_drift_append_dedup(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.detect_model_drift("M1", "1", FEATURE_DRIFT, baseline=100.0, current=140.0, commit=True)
    eng.detect_model_drift("M1", "1", FEATURE_DRIFT, baseline=100.0, current=140.0,
                           now=T1, commit=True)
    assert len(ledger.read_drift()) == 1


def test_drift_findings(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().detect_model_drift("M1", "1", PERFORMANCE_DRIFT, baseline=1.5, current=0.5)
    assert r.findings and "PERFORMANCE_DRIFT" in r.findings[0]


# ── 60~65. Governance report ──
def test_report_model_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng, mid="M1")
    _reg(eng, mid="M2")
    assert eng.generate_governance_report(T0).model_count == 2


def test_report_state_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_approved(eng)
    rep = eng.generate_governance_report(T0)
    assert rep.state_distribution.get(APPROVED) == 1


def test_report_approved_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_approved(eng)
    assert eng.generate_governance_report(T0).approved_count == 1


def test_report_deployed_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_approved(eng)
    eng.record_deployment("M1", "1", "shadow", "ops", now=T0, commit=True)
    assert eng.generate_governance_report(T0).deployed_candidate_count == 1


def test_report_drift_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.detect_model_drift("M1", "1", PERFORMANCE_DRIFT, baseline=1.5, current=1.0, commit=True)
    assert eng.generate_governance_report(T0).drift_critical == 1


def test_report_avg_confidence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_evaluated(eng, mid="M1", v="1")
    assert eng.generate_governance_report(T0).average_confidence == 0.85


# ── 66~71. Verify / tamper / replay ──
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.model_governance.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_chain_intact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.model_governance.verify import verify_chain
    eng = _eng()
    _to_approved(eng)
    eng.record_deployment("M1", "1", "shadow", "ops", now=T0, commit=True)
    res = verify_chain()
    assert res["ok"] and res["n"] >= 5


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.model_governance.verify import verify_chain
    _reg(_eng())
    path = sp("mg_models.jsonl")
    recs = [json.loads(ln) for ln in open(path) if ln.strip()]
    recs[0]["task"] = "TAMPERED"
    with open(path, "w") as f:
        f.write(json.dumps(recs[0]) + "\n")
    assert verify_chain()["ledgers"]["mg_models.jsonl"]["reason"] == "record_hash_mismatch"


def test_verify_detects_broken_previous_hash(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.model_governance.verify import verify_chain
    eng = _eng()
    _reg(eng, mid="M1")
    _reg(eng, mid="M2")
    path = sp("mg_models.jsonl")
    recs = [json.loads(ln) for ln in open(path) if ln.strip()]
    recs[1]["previous_hash"] = "sha256:deadbeef"
    with open(path, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ledgers"]["mg_models.jsonl"]["reason"] == "previous_hash_broken"


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.model_governance.verify import verify_chain
    _reg(_eng())
    path = sp("mg_models.jsonl")
    rec = [json.loads(ln) for ln in open(path) if ln.strip()][0]
    with open(path, "a") as f:
        f.write(json.dumps(rec) + "\n")
    assert verify_chain()["ledgers"]["mg_models.jsonl"]["reason"] in {"duplicate_id",
                                                                      "previous_hash_broken"}


def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_approved(eng)
    from jarvis.model_governance.verify import replay
    assert replay(eng, T0)["deterministic"] is True


# ── 72~80. CLI ──
def test_cli_register(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.model_governance.__main__ import main
    rc = main(["register", "--model-id", "M1", "--name", "n", "--model-type", "xgb",
               "--task", "cls", "--owner", "q", "--commit"])
    assert rc == 0 and "model" in capsys.readouterr().out


def test_cli_version(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.model_governance.__main__ import main
    main(["register", "--model-id", "M1", "--name", "n", "--model-type", "xgb",
          "--task", "cls", "--owner", "q", "--commit"])
    rc = main(["version", "--model-id", "M1", "--version", "1", "--framework", "fw", "--commit"])
    assert rc == 0 and "version" in capsys.readouterr().out


def test_cli_evaluate(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_trained(eng)
    from jarvis.model_governance.__main__ import main
    rc = main(["evaluate", "--model-id", "M1", "--version", "1", "--sharpe", "1.5",
               "--stability", "0.8", "--confidence", "0.8", "--commit"])
    assert rc == 0 and "evaluation" in capsys.readouterr().out


def test_cli_approve(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_evaluated(eng)
    from jarvis.model_governance.__main__ import main
    rc = main(["approve", "--model-id", "M1", "--version", "1", "--approver", "cro",
               "--decision", "APPROVE", "--commit"])
    assert rc == 0 and "approval" in capsys.readouterr().out


def test_cli_deploy(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_approved(eng)
    from jarvis.model_governance.__main__ import main
    rc = main(["deploy", "--model-id", "M1", "--version", "1", "--environment", "shadow",
               "--by", "ops", "--commit"])
    assert rc == 0 and "deployment" in capsys.readouterr().out


def test_cli_drift(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.model_governance.__main__ import main
    rc = main(["drift", "--model-id", "M1", "--version", "1", "--drift-type", "FEATURE_DRIFT",
               "--baseline", "100", "--current", "140", "--commit"])
    assert rc == 0 and "drift" in capsys.readouterr().out


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.model_governance.__main__ import main
    assert main(["verify"]) == 0
    assert "ok" in capsys.readouterr().out


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.model_governance.__main__ import main
    assert main(["summary"]) == 0
    assert "model_count" in capsys.readouterr().out


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.model_governance.__main__ import main
    assert main(["replay"]) == 0
    assert "deterministic" in capsys.readouterr().out


# ── 81~91. 보안/충돌회피/불변 ──
def test_no_forbidden_imports():
    import importlib
    import inspect
    _j = "jarvis."
    forbidden = (_j + "execution", _j + "live_execution", _j + "paper_execution",
                 _j + "execution_control", _j + "execution_risk", _j + "execution_cost",
                 _j + "portfolio", _j + "broker_readonly", _j + "risk.governor")
    for m in ("models", "engine", "ledger", "verify", "__init__", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.model_governance.{m}"))
        for f in forbidden:
            assert f not in src, f"{m} references {f}"


def test_no_execution_capability():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.model_governance.{m}"))
        for banned in ("submit_order", "place_order", "cancel_order", ".buy(", ".sell(",
                       "model.fit(", "model.predict(", ".train(", "kill_switch("):
            assert banned not in src, f"{m} has execution verb {banned}"


def test_no_broker_or_portfolio():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.model_governance.{m}"))
        for banned in ("gateway.", "broker.submit", "broker_api", "portfolio.",
                       "rebalance(", "allocate_capital"):
            assert banned not in src, f"{m} has broker/portfolio verb {banned}"


def test_no_autonomous_deployment():
    import importlib
    import inspect
    for m in ("engine", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.model_governance.{m}"))
        for banned in ("auto_deploy", "deploy_now", "push_to_prod", "activate_model",
                       "load_model("):
            assert banned not in src, f"{m} has autonomous deploy verb {banned}"


def test_ledger_no_delete_api():
    import inspect
    from jarvis.model_governance import ledger as L
    src = inspect.getsource(L)
    for banned in ("def delete", "def update", "def remove", "def overwrite"):
        assert banned not in src


def test_existing_ledgers_unchanged(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    # 기존 P9.7 approvals/drift_reports 원장을 두고 P9.9가 절대 건드리지 않음
    for fn in ("approvals.jsonl", "drift_reports.jsonl"):
        with open(sp(fn), "w") as f:
            f.write(json.dumps({"pre": "existing"}) + "\n")
    before = {fn: hashlib.sha256(open(sp(fn), "rb").read()).hexdigest()
              for fn in ("approvals.jsonl", "drift_reports.jsonl")}
    eng = _eng()
    _to_approved(eng)
    eng.detect_model_drift("M1", "1", FEATURE_DRIFT, baseline=1.0, current=2.0, commit=True)
    after = {fn: hashlib.sha256(open(sp(fn), "rb").read()).hexdigest()
             for fn in ("approvals.jsonl", "drift_reports.jsonl")}
    assert before == after   # 기존 원장 무변경
    assert os.path.exists(sp("mg_approvals.jsonl")) and os.path.exists(sp("mg_drift_reports.jsonl"))


def test_no_permission_escalation():
    from jarvis.permissions.policy import ACTION_PERMISSIONS, FORBIDDEN
    assert len(FORBIDDEN) == 6
    for kw in ("model_governance", "deploy_model", "model_approve"):
        assert not any(kw in a.lower() for a in ACTION_PERMISSIONS), kw


def test_append_only_never_deletes(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng, mid="M1")
    n1 = len(ledger.read_models())
    _reg(eng, mid="M2")
    assert len(ledger.read_models()) > n1


def test_no_config_mutation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    import jarvis.config as cfg
    from jarvis.permissions.policy import FORBIDDEN
    a0, f0 = cfg.AUTONOMY_LEVEL, len(FORBIDDEN)
    eng = _eng()
    _to_approved(eng)
    eng.record_deployment("M1", "1", "shadow", "ops", now=T0, commit=True)
    assert cfg.AUTONOMY_LEVEL == a0 and len(FORBIDDEN) == f0


def test_autonomy_invariant():
    from jarvis.config import AUTONOMY_LEVEL, MIN_LIVE_LEVEL, live_execution_enabled
    assert AUTONOMY_LEVEL == 5 and MIN_LIVE_LEVEL == 6
    assert live_execution_enabled() is False
