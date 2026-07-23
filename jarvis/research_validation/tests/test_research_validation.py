"""P10.9 Research Validation & Reproducibility Governance 테스트. **평가 기록 전용.**

검증 레지스트리(불변)·생명주기(CREATED→RUNNING→COMPLETED→REVIEWED→ARCHIVED, 차단전이)·세션·재현성
체크리스트(8항목 PASS/WARNING/FAILED)·증거·리플레이 검증(REPRODUCIBLE/NON_REPRODUCIBLE)·계보 무결성
(dangling/cycle)·검증 점수(가중)·감사 요약·verify(체인/변조/중복/계보/리플레이 일관성)·CLI·보안
(금지import·실행/배포/자본배분/권한/config/autonomy 변경 없음·상위 원장 무변경·삭제 API 없음·불변·
VALIDATED≠APPROVED·score≠approval·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from jarvis.research_validation import ledger
from jarvis.research_validation import models as M
from jarvis.research_validation.engine import ResearchValidationEngine
from jarvis.research_validation.models import (
    ARCHIVED,
    COMPLETED,
    CREATED,
    FAILED,
    NON_REPRODUCIBLE,
    PASS,
    REPRODUCIBLE,
    REVIEWED,
    RUNNING,
    WARNING,
    IllegalTransition,
    ImmutableValidationError,
    UnknownValidation,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"
T2 = "2026-07-23T00:02:00Z"

_ALL_PASS = {k: PASS for k in M.CHECKLIST_ITEMS}
_MIXED = {**{k: PASS for k in M.CHECKLIST_ITEMS}, M.REPRODUCIBILITY: WARNING,
          M.ARTIFACT_AVAILABILITY: FAILED}


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_validation.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchValidationEngine()


def _val(eng, layer="research_governance", tid="ST1", vtype=M.FULL_VALIDATION, commit=True):
    return eng.register_validation(layer, tid, vtype, "", T0, commit=commit)


# ── Validation Registry ──
def test_register_validation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _val(eng)
    assert v.status == CREATED and v.target_layer == "research_governance"
    assert eng.validation_state(v.validation_id) == CREATED


def test_validation_id_deterministic():
    a = M.validation_id("l", "t", "FULL")
    assert a == M.validation_id("l", "t", "FULL") and a.startswith("RVV:")


def test_validation_commit_persists(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _val(_eng(), commit=True)
    assert len(ledger.read_validation_events()) == 1


def test_validation_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _val(_eng(), commit=False)
    assert ledger.read_validation_events() == []


def test_validation_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _val(eng)
    _val(eng)
    assert len(ledger.distinct_validations()) == 1


def test_validation_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _val(eng)
    vid = v.validation_id
    eng.transition_validation(vid, RUNNING, T1, commit=True)
    eng.transition_validation(vid, COMPLETED, T1, commit=True)
    eng.transition_validation(vid, REVIEWED, T2, commit=True)
    eng.transition_validation(vid, ARCHIVED, T2, commit=True)
    assert eng.validation_state(vid) == ARCHIVED


def test_validation_invalid_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _val(eng)
    with pytest.raises(IllegalTransition):
        eng.transition_validation(v.validation_id, COMPLETED, T1, commit=True)


def test_validation_archived_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _val(eng)
    for to in (RUNNING, COMPLETED, REVIEWED, ARCHIVED):
        eng.transition_validation(v.validation_id, to, T1, commit=True)
    with pytest.raises(IllegalTransition):
        eng.transition_validation(v.validation_id, RUNNING, T2, commit=True)


def test_validation_transition_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownValidation):
        _eng().transition_validation("GHOST", RUNNING, T1, commit=True)


def test_validation_transition_table():
    assert M.can_transition_validation("", CREATED)
    assert M.can_transition_validation(CREATED, RUNNING)
    assert M.can_transition_validation(RUNNING, COMPLETED)
    assert M.can_transition_validation(COMPLETED, REVIEWED)
    assert not M.can_transition_validation(CREATED, COMPLETED)
    assert not M.can_transition_validation(ARCHIVED, CREATED)


@pytest.mark.parametrize("vtype", list(M.VALIDATION_TYPES))
def test_validation_types(tmp_path, monkeypatch, vtype):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = eng.register_validation("research_governance", "X", vtype, "", T0, commit=True)
    assert v.validation_type == vtype


def test_validation_artifact_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _val(eng)
    arts = {a["artifact_id"]: a for a in ledger.read_artifacts()}
    va = arts[M.artifact_id(M.ART_VALIDATION, v.validation_id)]
    assert va["parent_artifact"] == M.artifact_id(M.ART_TARGET, "research_governance:ST1")
    assert va["parent_artifact"] in arts


# ── Session ──
def test_create_session(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = eng.create_session("q3_audit", "human_validator", ["research_governance"], "review", T0,
                           commit=True)
    assert s.validator == "human_validator"
    assert len(ledger.read_sessions()) == 1


def test_session_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_session("a", "v", ["l"], "", T0, commit=True)
    eng.create_session("a", "v", ["l"], "", T0, commit=True)
    assert len(ledger.read_sessions()) == 1


def test_session_id_deterministic_order():
    assert M.session_id("n", "v", ["b", "a"]) == M.session_id("n", "v", ["a", "b"])


# ── Checklist ──
def test_checklist_all_pass(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _val(eng)
    c = eng.evaluate_checklist(v.validation_id, _ALL_PASS, T1, commit=True)
    assert c.summary["overall"] == PASS and c.summary["pass"] == 8


def test_checklist_mixed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _val(eng)
    c = eng.evaluate_checklist(v.validation_id, _MIXED, T1, commit=True)
    assert c.summary["overall"] == FAILED  # 하나라도 FAILED → FAILED
    assert c.summary["failed"] == 1 and c.summary["warning"] == 1


def test_checklist_warning_overall(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _val(eng)
    items = {**_ALL_PASS, M.REPRODUCIBILITY: WARNING}
    c = eng.evaluate_checklist(v.validation_id, items, T1, commit=True)
    assert c.summary["overall"] == WARNING


def test_checklist_all_eight_items(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _val(eng)
    c = eng.evaluate_checklist(v.validation_id, _ALL_PASS, T1, commit=True)
    assert set(c.items) == set(M.CHECKLIST_ITEMS)
    assert len(M.CHECKLIST_ITEMS) == 8


def test_checklist_missing_item_defaults_failed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _val(eng)
    c = eng.evaluate_checklist(v.validation_id, {M.REPRODUCIBILITY: PASS}, T1, commit=True)
    assert c.items[M.LINEAGE_COMPLETENESS] == FAILED  # 미기입 → FAILED


def test_checklist_advances_to_running(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _val(eng)
    eng.evaluate_checklist(v.validation_id, _ALL_PASS, T1, commit=True)
    assert eng.validation_state(v.validation_id) == RUNNING


def test_checklist_unknown_validation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownValidation):
        _eng().evaluate_checklist("GHOST", _ALL_PASS, T1, commit=True)


def test_checklist_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _val(eng)
    eng.evaluate_checklist(v.validation_id, _ALL_PASS, T1, commit=True)
    eng.evaluate_checklist(v.validation_id, _ALL_PASS, T1, commit=True)
    assert len(ledger.read_checklists()) == 1


def test_checklist_summary_helper():
    s = M.checklist_summary({"a": PASS, "b": WARNING, "c": FAILED})
    assert s == {"pass": 1, "warning": 1, "failed": 1, "overall": FAILED}


def test_checklist_result_helper():
    assert M.checklist_result(True) == PASS
    assert M.checklist_result(True, warn=True) == WARNING
    assert M.checklist_result(False) == FAILED


# ── Evidence ──
def test_record_evidence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _val(eng)
    e = eng.record_evidence(v.validation_id, "backtest_log", "log", "rg:bt1", {"rows": 100}, T1,
                            commit=True)
    assert e.reference == "rg:bt1" and e.evidence_hash.startswith("sha256:")
    assert len(ledger.read_evidence()) == 1


def test_evidence_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _val(eng)
    eng.record_evidence(v.validation_id, "e", "log", "ref", {}, T1, commit=True)
    eng.record_evidence(v.validation_id, "e", "log", "ref", {}, T1, commit=True)
    assert len(ledger.read_evidence()) == 1


def test_evidence_unknown_validation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownValidation):
        _eng().record_evidence("GHOST", "e", "log", "r", {}, T1, commit=True)


def test_evidence_hash_stable():
    assert M.evidence_hash({"a": 1, "b": 2}) == M.evidence_hash({"b": 2, "a": 1})


# ── Replay Verification ──
def test_output_hash_deterministic():
    a = M.output_hash({"x": 1}, {"m": 2}, "7")
    b = M.output_hash({"x": 1}, {"m": 2}, "7")
    assert a == b


def test_output_hash_varies():
    assert M.output_hash({"x": 1}, {}, "0") != M.output_hash({"x": 2}, {}, "0")
    assert M.output_hash({"x": 1}, {}, "0") != M.output_hash({"x": 1}, {}, "1")


def test_verify_replay_reproducible(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _val(eng)
    r = eng.verify_replay(v.validation_id, {"lookback": 50}, {"m": 1}, "0", "", T1, commit=True)
    assert r.result == REPRODUCIBLE
    assert r.original_output_hash == r.replay_output_hash


def test_verify_replay_non_reproducible(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _val(eng)
    r = eng.verify_replay(v.validation_id, {"lookback": 50}, {"m": 1}, "0",
                          "sha256:deadbeefdeadbeef", T1, commit=True)
    assert r.result == NON_REPRODUCIBLE
    assert r.original_output_hash != r.replay_output_hash


def test_verify_replay_records_only(tmp_path, monkeypatch):
    """NON_REPRODUCIBLE 는 기록만 — 어떤 자동 조치도 없다."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _val(eng)
    eng.verify_replay(v.validation_id, {"x": 1}, {}, "0", "sha256:0000000000000000", T1,
                      commit=True)
    assert len(ledger.read_replay_reports()) == 1
    assert not hasattr(eng, "fix_reproducibility")


def test_verify_replay_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _val(eng)
    eng.verify_replay(v.validation_id, {"x": 1}, {}, "0", "", T1, commit=True)
    eng.verify_replay(v.validation_id, {"x": 1}, {}, "0", "", T1, commit=True)
    assert len(ledger.read_replay_reports()) == 1


def test_verify_replay_unknown_validation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownValidation):
        _eng().verify_replay("GHOST", {}, {}, "0", "", T1, commit=True)


# ── Lineage Validation ──
def _seed(sp, filename, rows):
    with open(sp(filename), "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_validate_lineage_clean(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    # 건전한 아티팩트 체인(root + child)
    _seed(sp, "rg_artifacts.jsonl", [
        {"artifact_id": "A1", "parent_artifact": ""},
        {"artifact_id": "A2", "parent_artifact": "A1"}])
    eng = _eng()
    v = _val(eng)
    l = eng.validate_lineage(v.validation_id, "research_governance", T1, commit=True)
    assert l.ok is True and l.issues == [] and l.n_checked == 2


def test_validate_lineage_dangling_parent(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "rg_artifacts.jsonl", [{"artifact_id": "A2", "parent_artifact": "GHOST"}])
    eng = _eng()
    v = _val(eng)
    l = eng.validate_lineage(v.validation_id, "research_governance", T1, commit=True)
    assert l.ok is False
    assert any("dangling_parent" in i for i in l.issues)


def test_validate_lineage_cycle(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "rg_artifacts.jsonl", [
        {"artifact_id": "A1", "parent_artifact": "A2"},
        {"artifact_id": "A2", "parent_artifact": "A1"}])
    eng = _eng()
    v = _val(eng)
    l = eng.validate_lineage(v.validation_id, "research_governance", T1, commit=True)
    assert any("cycle" in i for i in l.issues)


def test_validate_lineage_empty_source(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _val(eng)
    l = eng.validate_lineage(v.validation_id, "research_governance", T1, commit=True)
    assert l.n_checked == 0 and l.ok is True  # 빈 원장은 이슈 없음


def test_validate_lineage_unknown_validation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownValidation):
        _eng().validate_lineage("GHOST", "research_governance", T1, commit=True)


def test_validate_lineage_all_layers(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    for layer in M.TARGET_LAYERS:
        v = eng.register_validation(layer, "X", M.LINEAGE_VALIDATION, "", T0, commit=True)
        l = eng.validate_lineage(v.validation_id, layer, T1, commit=True)
        assert l.target_layer == layer


def test_detect_cycle_helper():
    assert M.detect_cycle([("a", "b"), ("b", "a")]) == ["a", "b", "a"]
    assert M.detect_cycle([("a", "b")]) == []


# ── Validation Score ──
def test_score_weights_sum_one():
    assert abs(sum(M.SCORE_WEIGHTS.values()) - 1.0) < 1e-9


def test_compute_score_all_ones():
    comps = {k: 1.0 for k in M.SCORE_WEIGHTS}
    assert abs(M.compute_score(comps) - 1.0) < 1e-9


def test_compute_score_weighted():
    comps = {k: 0.0 for k in M.SCORE_WEIGHTS}
    comps["lineage"] = 1.0
    assert abs(M.compute_score(comps) - 0.20) < 1e-9


def test_checklist_to_components_all_pass():
    comps = M.checklist_to_components(_ALL_PASS)
    assert all(abs(v - 1.0) < 1e-9 for v in comps.values())


def test_compute_validation_score_from_checklist(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _val(eng)
    eng.evaluate_checklist(v.validation_id, _ALL_PASS, T1, commit=True)
    s = eng.compute_validation_score(v.validation_id, None, T1, commit=True)
    assert abs(s.overall_score - 1.0) < 1e-9 and s.grade == "A"


def test_compute_validation_score_explicit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _val(eng)
    comps = {k: 0.5 for k in M.SCORE_WEIGHTS}
    s = eng.compute_validation_score(v.validation_id, comps, T1, commit=True)
    assert abs(s.overall_score - 0.5) < 1e-9 and s.grade == "C"


def test_score_advances_to_completed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _val(eng)
    eng.evaluate_checklist(v.validation_id, _ALL_PASS, T1, commit=True)
    eng.compute_validation_score(v.validation_id, None, T1, commit=True)
    assert eng.validation_state(v.validation_id) == COMPLETED


def test_score_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _val(eng)
    eng.compute_validation_score(v.validation_id, {k: 1.0 for k in M.SCORE_WEIGHTS}, T1,
                                 commit=True)
    eng.compute_validation_score(v.validation_id, {k: 1.0 for k in M.SCORE_WEIGHTS}, T1,
                                 commit=True)
    assert len(ledger.read_scores()) == 1


def test_score_unknown_validation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownValidation):
        _eng().compute_validation_score("GHOST", {}, T1, commit=True)


def test_score_grade_boundaries():
    assert M.score_grade(0.9) == "A"
    assert M.score_grade(0.75) == "B"
    assert M.score_grade(0.6) == "C"
    assert M.score_grade(0.3) == "D"


def test_score_not_approval(tmp_path, monkeypatch):
    """점수 레코드에 approval/deployment 필드가 없어야 한다 — 품질 라벨일 뿐."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _val(eng)
    s = eng.compute_validation_score(v.validation_id, {k: 1.0 for k in M.SCORE_WEIGHTS}, T1,
                                     commit=True)
    d = s.to_dict()
    for banned in ("approved", "deployed", "deployable", "approval"):
        assert banned not in d


# ── Audit Summary ──
def _full(eng):
    v = _val(eng)
    eng.evaluate_checklist(v.validation_id, _ALL_PASS, T1, commit=True)
    eng.record_evidence(v.validation_id, "log", "log", "rg:bt", {}, T1, commit=True)
    eng.verify_replay(v.validation_id, {"x": 1}, {}, "0", "", T1, commit=True)
    eng.validate_lineage(v.validation_id, "research_governance", T1, commit=True)
    eng.compute_validation_score(v.validation_id, None, T1, commit=True)
    return v


def test_audit_summary_totals(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    rep = eng.generate_audit_summary(T2)
    assert rep.validation_count == 1 and rep.checklist_count == 1
    assert rep.evidence_count == 1 and rep.replay_count == 1
    assert rep.lineage_report_count == 1 and rep.score_count == 1


def test_audit_summary_mean_score(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    rep = eng.generate_audit_summary(T2)
    assert abs(rep.mean_score - 1.0) < 1e-9


def test_audit_summary_non_reproducible_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _val(eng)
    eng.verify_replay(v.validation_id, {"x": 1}, {}, "0", "sha256:0000000000000000", T1,
                      commit=True)
    rep = eng.generate_audit_summary(T2)
    assert rep.non_reproducible_count == 1


def test_audit_summary_distributions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    rep = eng.generate_audit_summary(T2)
    assert rep.target_layer_distribution.get("research_governance") == 1
    assert rep.checklist_overall_distribution.get(PASS) == 1


def test_audit_summary_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    assert eng.generate_audit_summary(T2).to_dict() == eng.generate_audit_summary(T2).to_dict()


def test_audit_summary_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    rep = _eng().generate_audit_summary(T0)
    assert rep.validation_count == 0 and rep.mean_score == 0.0


# ── verify ──
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_validation.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_full_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_validation.verify import verify_chain
    eng = _eng()
    _full(eng)
    res = verify_chain()
    assert res["ok"] is True
    assert res["lineage"]["ok"] is True and res["replay"]["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_validation.verify import verify_chain
    eng = _eng()
    _val(eng)
    recs = ledger.read_validation_events()
    recs[0]["target_id"] = "TAMPERED"
    with open(sp("rv_validations.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_chain_break(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_validation.verify import verify_ledger
    eng = _eng()
    _val(eng, tid="A")
    _val(eng, tid="B")
    recs = ledger.read_validation_events()
    recs[1]["previous_hash"] = "GENESIS"
    with open(sp("rv_validations.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert verify_ledger(ledger.VALIDATIONS)["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_validation.verify import verify_ledger
    eng = _eng()
    _val(eng)
    recs = ledger.read_validation_events()
    dup = dict(recs[0])
    dup["previous_hash"] = recs[0]["record_hash"]
    with open(sp("rv_validations.jsonl"), "a") as f:
        f.write(json.dumps(dup) + "\n")
    assert verify_ledger(ledger.VALIDATIONS)["ok"] is False


def test_verify_detects_dangling_checklist(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_validation.verify import lineage_validation
    rec = {"checklist_id": "RVC:x", "validation_id": "RVV:ghost", "items": {}, "summary": {},
           "created_at": T0, "previous_hash": "GENESIS"}
    rec["record_hash"] = M.content_hash(rec)
    with open(sp("rv_checklists.jsonl"), "w") as f:
        f.write(json.dumps(rec) + "\n")
    res = lineage_validation()
    assert res["ok"] is False
    assert any("dangling_checklist" in i for i in res["issues"])


def test_verify_detects_artifact_cycle(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_validation.verify import lineage_validation
    a1 = {"artifact_id": "A1", "artifact_type": "X", "ref_id": "r", "parent_artifact": "A2",
          "validation_id": "", "created_at": T0, "previous_hash": "GENESIS"}
    a1["record_hash"] = M.content_hash(a1)
    a2 = {"artifact_id": "A2", "artifact_type": "X", "ref_id": "r", "parent_artifact": "A1",
          "validation_id": "", "created_at": T0, "previous_hash": a1["record_hash"]}
    a2["record_hash"] = M.content_hash(a2)
    with open(sp("rv_artifacts.jsonl"), "w") as f:
        f.write(json.dumps(a1) + "\n")
        f.write(json.dumps(a2) + "\n")
    assert any("circular_dependency" in i for i in lineage_validation()["issues"])


def test_verify_replay_consistency_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_validation.verify import replay_consistency
    # 위조: 해시가 다른데 REPRODUCIBLE 로 선언
    rec = {"replay_id": "RVP:x", "validation_id": "RVV:1",
           "original_output_hash": "sha256:aaaa", "replay_output_hash": "sha256:bbbb",
           "result": "REPRODUCIBLE", "created_at": T0, "previous_hash": "GENESIS"}
    rec["record_hash"] = M.content_hash(rec)
    with open(sp("rv_replay_reports.jsonl"), "w") as f:
        f.write(json.dumps(rec) + "\n")
    res = replay_consistency()
    assert res["ok"] is False
    assert any("inconsistent_replay" in i for i in res["issues"])


# ── replay determinism ──
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_validation.verify import replay
    eng = _eng()
    _full(eng)
    assert replay(eng, T2)["deterministic"] is True


# ── content hash ──
def test_content_hash_excludes_chain_fields():
    a = {"x": 1, "previous_hash": "A", "record_hash": "B", "report_hash": "C"}
    b = {"x": 1, "previous_hash": "Z", "record_hash": "Z", "report_hash": "Z"}
    assert M.content_hash(a) == M.content_hash(b)


# ── CLI ──
def test_cli_validate_and_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_validation.__main__ import main
    rc = main(["validate", "--target-layer", "research_governance", "--target-id", "ST1",
               "--commit"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["validation"]["target_layer"] == "research_governance"
    main(["summary"])
    assert json.loads(capsys.readouterr().out)["validation_count"] == 1


def test_cli_full_workflow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_validation.__main__ import main
    main(["validate", "--target-layer", "research_governance", "--target-id", "ST1", "--commit"])
    vid = json.loads(capsys.readouterr().out)["validation"]["validation_id"]
    main(["checklist", "--validation-id", vid, "--items-json", json.dumps(_ALL_PASS), "--commit"])
    c = json.loads(capsys.readouterr().out)["checklist"]
    assert c["summary"]["overall"] == PASS
    main(["replay", "--validation-id", vid, "--inputs-json", json.dumps({"x": 1}),
          "--metadata-json", json.dumps({"m": 1}), "--seed", "0", "--commit"])
    r = json.loads(capsys.readouterr().out)["replay"]
    assert r["result"] == REPRODUCIBLE
    main(["score", "--validation-id", vid, "--commit"])
    s = json.loads(capsys.readouterr().out)["score"]
    assert s["grade"] == "A"
    rc = main(["verify"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_lineage(tmp_path, monkeypatch, capsys):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "rg_artifacts.jsonl", [{"artifact_id": "A1", "parent_artifact": ""}])
    from jarvis.research_validation.__main__ import main
    main(["validate", "--target-layer", "research_governance", "--target-id", "ST1", "--commit"])
    vid = json.loads(capsys.readouterr().out)["validation"]["validation_id"]
    main(["lineage", "--validation-id", vid, "--target-layer", "research_governance", "--commit"])
    l = json.loads(capsys.readouterr().out)["lineage_report"]
    assert l["ok"] is True


def test_cli_replay_non_reproducible(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_validation.__main__ import main
    main(["validate", "--target-layer", "research_governance", "--target-id", "ST1", "--commit"])
    vid = json.loads(capsys.readouterr().out)["validation"]["validation_id"]
    main(["replay", "--validation-id", vid, "--inputs-json", json.dumps({"x": 1}),
          "--seed", "0", "--original-hash", "sha256:0000000000000000", "--commit"])
    r = json.loads(capsys.readouterr().out)["replay"]
    assert r["result"] == NON_REPRODUCIBLE


# ── 보안·불변·READ ONLY 가드 ──
def test_no_forbidden_imports():
    import jarvis.research_validation.engine as eng_mod
    import jarvis.research_validation.models as mdl_mod
    import jarvis.research_validation.ledger as led_mod
    import jarvis.research_validation.verify as ver_mod
    src = ""
    for m in (eng_mod, mdl_mod, led_mod, ver_mod):
        with open(m.__file__) as f:
            src += f.read()
    _j = "jarvis."
    forbidden = [_j + "live_execution", _j + "broker", _j + "order",
                 _j + "portfolio.", _j + "risk_governor", _j + "permission",
                 "place_order(", "submit_order(", "execute_trade(", "deploy_strategy(",
                 "allocate_capital(", "promote_model(", "activate_live("]
    for token in forbidden:
        assert token not in src, f"forbidden reference: {token}"


def test_no_execution_authority_api():
    api = set(dir(ResearchValidationEngine))
    for banned in ("execute", "trade", "place_order", "allocate", "deploy", "promote",
                   "activate_live", "approve", "approve_for_trading", "change_permission",
                   "set_autonomy"):
        assert banned not in api


def test_validated_not_approved(tmp_path, monkeypatch):
    """검증 COMPLETED 이어도 승인/배포 권한은 전혀 없다."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _full(eng)
    assert eng.validation_state(v.validation_id) == COMPLETED
    assert not hasattr(eng, "approve")
    assert not hasattr(eng, "mark_deployable")


def test_live_execution_disabled_invariant():
    import jarvis.config as _cfg
    assert _cfg.live_execution_enabled() is False
    assert _cfg.AUTONOMY_LEVEL < _cfg.MIN_LIVE_LEVEL


def test_autonomy_unchanged_after_validation(tmp_path, monkeypatch):
    import jarvis.config as _cfg
    before = _cfg.AUTONOMY_LEVEL
    _iso(tmp_path, monkeypatch)
    _full(_eng())
    assert _cfg.AUTONOMY_LEVEL == before
    assert _cfg.live_execution_enabled() is False


def test_no_delete_or_update_api():
    import importlib
    for mod_name in ("engine", "ledger"):
        m = importlib.import_module(f"jarvis.research_validation.{mod_name}")
        for attr in dir(m):
            low = attr.lower()
            assert not low.startswith("delete_")
            assert not low.startswith("update_")
            assert not low.startswith("remove_")


def test_ledgers_namespaced_rv_prefix():
    for filename, _ in ledger.ALL_LEDGERS:
        assert filename.startswith("rv_")


def test_no_collision_with_existing_prefixes():
    ours = {fn for fn, _ in ledger.ALL_LEDGERS}
    known = {"rg_strategies.jsonl", "ai_signals.jsonl", "pr_portfolios.jsonl",
             "kg_entities.jsonl", "arg_agents.jsonl", "di_candidates.jsonl",
             "sim_scenarios.jsonl"}
    assert ours.isdisjoint(known)
    assert all(fn.startswith("rv_") for fn in ours)


def test_source_ledgers_read_only_not_owned():
    owned = {fn for fn, _ in ledger.ALL_LEDGERS}
    for layer, files in ledger.SOURCE_LEDGERS.items():
        for fn in files:
            assert fn not in owned


def test_existing_source_ledgers_untouched(tmp_path, monkeypatch):
    """상위 P10.2~P10.8 원장을 시드한 뒤 전체 검증 워크플로를 돌려도 원본 SHA256 불변."""
    sp = _iso(tmp_path, monkeypatch)
    seeds = {"rg_strategies.jsonl": [{"strategy_id": "ST1"}],
             "rg_artifacts.jsonl": [{"artifact_id": "A1", "parent_artifact": ""}],
             "ai_signals.jsonl": [{"signal_id": "SG1"}],
             "kg_entities.jsonl": [{"entity_id": "KGE:1"}],
             "sim_scenarios.jsonl": [{"scenario_id": "SSC:1"}]}
    hashes = {}
    for fn, rows in seeds.items():
        _seed(sp, fn, rows)
        hashes[fn] = hashlib.sha256(open(sp(fn), "rb").read()).hexdigest()
    eng = _eng()
    targets = eng.list_source_targets("research_governance")
    v = eng.register_validation("research_governance", targets[0] if targets else "ST1",
                                M.FULL_VALIDATION, "", T0, commit=True)
    eng.evaluate_checklist(v.validation_id, _ALL_PASS, T1, commit=True)
    eng.validate_lineage(v.validation_id, "research_governance", T1, commit=True)
    eng.compute_validation_score(v.validation_id, None, T1, commit=True)
    eng.generate_audit_summary(T2)
    for fn, h in hashes.items():
        assert hashlib.sha256(open(sp(fn), "rb").read()).hexdigest() == h


def test_engine_only_appends_rv_files(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    created = [f for f in os.listdir(tmp_path) if f.endswith(".jsonl")]
    assert created and all(f.startswith("rv_") for f in created)


def test_list_source_targets(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "rg_strategies.jsonl", [{"strategy_id": "ST1"}, {"strategy_id": "ST2"}])
    assert _eng().list_source_targets("research_governance") == ["ST1", "ST2"]


def test_list_source_targets_does_not_mutate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "ai_signals.jsonl", [{"signal_id": "SG1"}])
    before = hashlib.sha256(open(sp("ai_signals.jsonl"), "rb").read()).hexdigest()
    _eng().list_source_targets("alpha_intelligence")
    after = hashlib.sha256(open(sp("ai_signals.jsonl"), "rb").read()).hexdigest()
    assert before == after


def test_target_layers_match_source_ledgers():
    assert set(M.TARGET_LAYERS) == set(ledger.SOURCE_LEDGERS)


# ── 추가: ID/헬퍼/필드 세부 ──
def test_validation_id_varies():
    assert M.validation_id("l", "A", "FULL") != M.validation_id("l", "B", "FULL")
    assert M.validation_id("l", "A", "FULL") != M.validation_id("l", "A", "LINEAGE")


def test_checklist_id_prefix():
    assert M.checklist_id("RVV:x").startswith("RVC:")


def test_evidence_id_prefix():
    assert M.evidence_id("RVV:x", "e").startswith("RVD:")


def test_replay_id_prefix():
    assert M.replay_id("RVV:x").startswith("RVP:")


def test_score_id_prefix():
    assert M.score_id("RVV:x").startswith("RVSC:")


def test_artifact_id_prefix():
    assert M.artifact_id(M.ART_VALIDATION, "x").startswith("RVA:")


def test_lineage_report_id_prefix():
    assert M.lineage_report_id("RVV:x").startswith("RVL:")


def test_default_validation_type_full(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = eng.register_validation("research_governance", "X", now=T0, commit=True)
    assert v.validation_type == M.FULL_VALIDATION


def test_evidence_type_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _val(eng)
    e = eng.record_evidence(v.validation_id, "e1", "dataset_snapshot", "dg:DS1", {}, T1,
                            commit=True)
    assert e.evidence_type == "dataset_snapshot"


def test_checklist_to_components_partial():
    items = {M.LINEAGE_COMPLETENESS: PASS, M.REPRODUCIBILITY: WARNING,
             M.DETERMINISTIC_REPLAY: FAILED}
    comps = M.checklist_to_components(items)
    assert comps["lineage"] == 1.0
    assert comps["reproducibility"] == 0.25  # (0.5 + 0.0)/2


def test_output_hash_empty_inputs():
    assert M.output_hash({}, {}, "0") == M.output_hash({}, {}, "0")


def test_validation_score_component_persisted(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _val(eng)
    s = eng.compute_validation_score(v.validation_id, {k: 1.0 for k in M.SCORE_WEIGHTS}, T1,
                                     commit=True)
    assert set(s.components) == set(M.SCORE_WEIGHTS)


def test_audit_summary_session_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_session("s", "v", ["l"], "", T0, commit=True)
    _full(eng)
    rep = eng.generate_audit_summary(T2)
    assert rep.session_count == 1


def test_full_lineage_intact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_validation.verify import lineage_validation
    eng = _eng()
    _full(eng)
    res = lineage_validation()
    assert res["ok"] is True and not res["issues"]


def test_score_artifact_parent_checklist(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _val(eng)
    eng.evaluate_checklist(v.validation_id, _ALL_PASS, T1, commit=True)
    s = eng.compute_validation_score(v.validation_id, None, T1, commit=True)
    arts = {a["artifact_id"]: a for a in ledger.read_artifacts()}
    sa = arts[M.artifact_id(M.ART_SCORE, s.score_id)]
    assert sa["parent_artifact"] == M.artifact_id(M.ART_CHECKLIST,
                                                  M.checklist_id(v.validation_id))
    assert sa["parent_artifact"] in arts
