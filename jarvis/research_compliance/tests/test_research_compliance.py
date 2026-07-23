"""P10.19 Research Compliance & Integrity Governance 테스트. **거버넌스 기준 준수 관찰 전용.**

규칙(불변·버전·범주 검증)·점검(PASS/WARNING/FAIL·증거·규칙 참조)·증거(체크섬·불변)·검토(결정 워크플로·
검토자 필수)·위반(생명주기 DETECTED→REVIEWED→RESOLVED·심각도·계보)·권고(불변)·리포트(결정적)·verify(체인/
변조/중복/전이/규칙참조/증거참조/계보)·replay·상위 READ ONLY 보호·CLI·보안(금지import·실행/수정/승인/배포
없음·상위 원장 무변경·삭제 API 없음·불변·COMPLIANCE CHECK≠APPROVAL·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import json
import os

import pytest

from jarvis.research_compliance import ledger
from jarvis.research_compliance import models as M
from jarvis.research_compliance.engine import ResearchComplianceEngine
from jarvis.research_compliance.models import (
    ACCEPT,
    ARCHIVED,
    AT_RISK,
    COMPLIANT,
    DETECTED,
    FAIL,
    NON_COMPLIANT,
    PASS,
    REJECT,
    REQUEST_CHANGE,
    RESOLVED,
    REVIEWED,
    WARNING,
    IllegalTransition,
    ImmutableCheckError,
    ImmutableEvidenceError,
    ImmutableRuleError,
    InvalidCheckResult,
    InvalidReviewDecision,
    InvalidRuleCategory,
    InvalidViolationCategory,
    MissingReviewer,
    UnknownRule,
    UnknownViolation,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"
T2 = "2026-07-23T00:02:00Z"

_HI = {"rule_coverage": 0.9, "evidence_completeness": 0.9, "check_pass_rate": 0.85,
       "violation_resolution_rate": 0.9, "lineage_integrity": 0.8}
_LO = {"rule_coverage": 0.2, "evidence_completeness": 0.1, "check_pass_rate": 0.2,
       "violation_resolution_rate": 0.1, "lineage_integrity": 0.2}


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_compliance.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchComplianceEngine()


def _rule(eng, cat=None, desc="OOS evidence required", sev="HIGH", ver="1.0", meta=None,
          commit=True):
    return eng.register_rule(cat or M.C_VALIDATION_REQUIREMENT, desc, sev, ver, meta or {}, T0,
                             commit=commit)


def _evidence(eng, src="research_governance:ST1", ref="artifact:oos_curve", payload="data",
              commit=True):
    return eng.register_evidence(src, ref, payload, "", "E1", T0, commit=commit)


def _violation(eng, cat=None, src="research_governance:ST1", sev="HIGH", commit=True):
    return eng.record_violation(cat or M.C_VALIDATION_REQUIREMENT, src, sev, ["ev1"], T0,
                                commit=commit)


def _full(eng):
    """object→rule→evidence→check→review→violation→recommendation→report end-to-end."""
    eng._ensure_object_artifact("research_governance:ST1", T0, commit=True)
    r = _rule(eng)
    e = _evidence(eng)
    c = eng.run_check(r.rule_id, "research_governance:ST1", PASS, e.evidence_id, {}, T0,
                      commit=True)
    eng.create_review("alice", c.check_id, ACCEPT, "ok", T0, commit=True)
    v = _violation(eng, cat=M.C_DOCUMENTATION, src="research_governance:ST2")
    eng.create_recommendation(v.violation_id, "add docstring", "docs missing", "HIGH", [], T0,
                              commit=True)
    eng.generate_report("GLOBAL", _HI, T1, commit=True)
    return r, e, c, v


# ── Rule ──
def test_rule_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _rule(_eng())
    assert r.rule_id.startswith("RCR:")
    assert r.category == M.C_VALIDATION_REQUIREMENT
    assert r.severity == "HIGH"


def test_rule_invalid_category(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(InvalidRuleCategory):
        _eng().register_rule("not_a_cat", "x", "LOW", "1.0", {}, T0, commit=True)


def test_rule_all_categories(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    for i, cat in enumerate(M.RULE_CATEGORIES):
        r = eng.register_rule(cat, f"desc{i}", "MEDIUM", "1.0", {}, T0, commit=True)
        assert r.category == cat
    assert len(ledger.read_rules()) == len(M.RULE_CATEGORIES)


def test_rule_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _rule(eng)
    b = _rule(eng)
    assert a.rule_id == b.rule_id
    assert len(ledger.read_rules()) == 1


def test_rule_immutable_metadata(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _rule(eng, sev="HIGH")
    with pytest.raises(ImmutableRuleError):
        _rule(eng, sev="LOW")


def test_rule_version_distinct(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r1 = _rule(eng, ver="1.0")
    r2 = _rule(eng, ver="2.0")
    assert r1.rule_id != r2.rule_id
    assert len(ledger.read_rules()) == 2


def test_rule_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _rule(_eng())
    assert r.rule_id == M.rule_id(M.C_VALIDATION_REQUIREMENT, "OOS evidence required", "1.0")


def test_rule_not_committed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _rule(_eng(), commit=False)
    assert ledger.read_rules() == []


def test_rule_artifact_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _rule(_eng())
    assert ledger.artifact_exists(M.artifact_id(M.ART_RULE, r.rule_id))


# ── Evidence ──
def test_evidence_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _evidence(_eng())
    assert e.evidence_id.startswith("RCE:")
    assert e.checksum.startswith("sha256:")


def test_evidence_checksum_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng().register_evidence("s", "ref", "payload", "", "E1", T0, commit=True)
    assert e.checksum == M.checksum("payload")


def test_evidence_explicit_checksum(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng().register_evidence("s", "ref", None, "sha256:abcd", "E1", T0, commit=True)
    assert e.checksum == "sha256:abcd"


def test_evidence_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_evidence("s", "ref", "payload1", "", "E1", T0, commit=True)
    with pytest.raises(ImmutableEvidenceError):
        eng.register_evidence("s", "ref", "payload2", "", "E1", T0, commit=True)


def test_evidence_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _evidence(eng)
    b = _evidence(eng)
    assert a.evidence_id == b.evidence_id
    assert len(ledger.read_evidence()) == 1


def test_evidence_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _evidence(_eng())
    assert e.evidence_id == M.evidence_id("research_governance:ST1", "artifact:oos_curve")


def test_evidence_parent_links_object(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng._ensure_object_artifact("research_governance:ST1", T0, commit=True)
    e = _evidence(eng)
    ea = next(a for a in ledger.read_artifacts()
              if a["ref_id"] == e.evidence_id and a["artifact_type"] == M.ART_EVIDENCE)
    assert ea["parent_artifact"] == M.artifact_id(M.ART_OBJECT, "research_governance:ST1")


# ── Check ──
def test_check_pass(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _rule(eng)
    c = eng.run_check(r.rule_id, "src1", PASS, "", {}, T0, commit=True)
    assert c.check_id.startswith("RCC:")
    assert c.result == PASS


def test_check_warning_fail(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r1 = _rule(eng, desc="d1")
    r2 = _rule(eng, desc="d2")
    cw = eng.run_check(r1.rule_id, "s", WARNING, "", {}, T0, commit=True)
    cf = eng.run_check(r2.rule_id, "s", FAIL, "", {}, T0, commit=True)
    assert cw.result == WARNING
    assert cf.result == FAIL


def test_check_requires_rule(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownRule):
        _eng().run_check("RCR:nope", "src", PASS, "", {}, T0, commit=True)


def test_check_invalid_result(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _rule(eng)
    with pytest.raises(InvalidCheckResult):
        eng.run_check(r.rule_id, "s", "MAYBE", "", {}, T0, commit=True)


def test_check_derive_result_all(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _rule(eng)
    c = eng.run_check(r.rule_id, "s", None, "", {"a": True, "b": True}, T0, commit=True)
    assert c.result == PASS


def test_check_derive_result_partial(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _rule(eng)
    c = eng.run_check(r.rule_id, "s", None, "", {"a": True, "b": False}, T0, commit=True)
    assert c.result == WARNING


def test_check_derive_result_none(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _rule(eng)
    c = eng.run_check(r.rule_id, "s", None, "", {"a": False, "b": False}, T0, commit=True)
    assert c.result == FAIL


def test_check_immutable_result(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _rule(eng)
    eng.run_check(r.rule_id, "s", PASS, "", {}, T0, commit=True)
    with pytest.raises(ImmutableCheckError):
        eng.run_check(r.rule_id, "s", FAIL, "", {}, T0, commit=True)


def test_check_parent_links_rule(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _rule(eng)
    c = eng.run_check(r.rule_id, "s", PASS, "", {}, T0, commit=True)
    ca = next(a for a in ledger.read_artifacts()
              if a["ref_id"] == c.check_id and a["artifact_type"] == M.ART_CHECK)
    assert ca["parent_artifact"] == M.artifact_id(M.ART_RULE, r.rule_id)


def test_check_completeness_framework(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _rule(eng, cat=M.C_DOCUMENTATION)
    c = eng.check_completeness(r.rule_id, "src", {"hypothesis": True, "dataset_reference": True,
                                                  "experiment_lineage": True}, T0, commit=True)
    assert c.result == PASS
    assert set(c.checklist) == set(M.COMPLETENESS_REQUIREMENTS)


def test_check_validation_framework(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _rule(eng)
    c = eng.check_validation(r.rule_id, "src", {"out_of_sample": True, "robustness": False,
                                                "reproducibility": True}, T0, commit=True)
    assert c.result == WARNING


def test_check_integrity_framework(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _rule(eng, cat=M.C_DATA_INTEGRITY)
    c = eng.check_integrity(r.rule_id, "src", {}, T0, commit=True)
    assert c.result == FAIL


# ── Review ──
def test_review_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    rv = _eng().create_review("alice", "RCC:x", ACCEPT, "ok", T0, commit=True)
    assert rv.review_id.startswith("RCW:")
    assert rv.decision == ACCEPT
    assert rv.reviewer == "alice"


def test_review_all_decisions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    for i, dec in enumerate(M.REVIEW_DECISIONS):
        rv = eng.create_review(f"r{i}", "tgt", dec, "", T0, commit=True)
        assert rv.decision == dec


def test_review_missing_reviewer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(MissingReviewer):
        _eng().create_review("", "tgt", ACCEPT, "", T0, commit=True)


def test_review_invalid_decision(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(InvalidReviewDecision):
        _eng().create_review("alice", "tgt", "MAYBE", "", T0, commit=True)


def test_review_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.create_review("alice", "tgt", ACCEPT, "", T0, commit=True)
    b = eng.create_review("alice", "tgt", REJECT, "", T0, commit=True)
    assert a.review_id == b.review_id
    assert a.decision == b.decision == ACCEPT  # first wins (immutable identity)


def test_review_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    rv = _eng().create_review("alice", "tgt", ACCEPT, "", T0, commit=True)
    assert rv.review_id == M.review_id("alice", "tgt")


def test_review_parent_links_check(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _rule(eng)
    c = eng.run_check(r.rule_id, "s", PASS, "", {}, T0, commit=True)
    rv = eng.create_review("alice", c.check_id, ACCEPT, "", T0, commit=True)
    ra = next(a for a in ledger.read_artifacts()
              if a["ref_id"] == rv.review_id and a["artifact_type"] == M.ART_REVIEW)
    assert ra["parent_artifact"] == M.artifact_id(M.ART_CHECK, c.check_id)


# ── Violation ──
def test_violation_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    v = _violation(_eng())
    assert v.violation_id.startswith("RCX:")
    assert v.to_state == DETECTED
    assert v.severity == "HIGH"


def test_violation_invalid_category(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(InvalidViolationCategory):
        _eng().record_violation("not_a_cat", "s", "LOW", [], T0, commit=True)


def test_violation_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _violation(eng)
    eng.transition_violation(v.violation_id, REVIEWED, T1, commit=True)
    eng.transition_violation(v.violation_id, RESOLVED, T2, commit=True)
    assert eng.violation_state(v.violation_id) == RESOLVED


def test_violation_resolve_helper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _violation(eng)
    res = eng.resolve_violation(v.violation_id, T1, commit=True)
    assert eng.violation_state(v.violation_id) == RESOLVED
    assert "자동 수정" in res["note"]


def test_violation_illegal_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _violation(eng)
    with pytest.raises(IllegalTransition):
        eng.transition_violation(v.violation_id, RESOLVED, T1, commit=True)


def test_violation_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownViolation):
        _eng().transition_violation("RCX:nope", REVIEWED, T1, commit=True)


def test_violation_archived_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _violation(eng)
    eng.transition_violation(v.violation_id, ARCHIVED, T1, commit=True)
    with pytest.raises(IllegalTransition):
        eng.transition_violation(v.violation_id, REVIEWED, T2, commit=True)


def test_violation_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _violation(eng)
    b = _violation(eng)
    assert a.violation_id == b.violation_id
    assert len(ledger.distinct_violations()) == 1


def test_violation_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    v = _violation(_eng())
    assert v.violation_id == M.violation_id(M.C_VALIDATION_REQUIREMENT, "research_governance:ST1")


def test_violation_can_transition_table():
    assert M.can_transition_violation("", DETECTED)
    assert M.can_transition_violation(DETECTED, REVIEWED)
    assert M.can_transition_violation(REVIEWED, RESOLVED)
    assert not M.can_transition_violation(DETECTED, RESOLVED)
    assert not M.can_transition_violation(RESOLVED, DETECTED)


def test_violation_no_fix_field(tmp_path, monkeypatch):
    """위반 레코드에 fix/correct/remediate 필드가 없어야 한다(자동 시정 없음)."""
    _iso(tmp_path, monkeypatch)
    v = _violation(_eng())
    d = v.to_dict()
    for banned in ("fix", "correct", "remediate", "auto"):
        assert banned not in d


# ── Recommendation ──
def test_recommendation_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    rec = _eng().create_recommendation("RCX:v1", "add OOS test", "missing OOS", "HIGH", [], T0,
                                       commit=True)
    assert rec.recommendation_id.startswith("RCM:")
    assert rec.priority == "HIGH"


def test_recommendation_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.create_recommendation("RCX:v1", "act", "r", "LOW", [], T0, commit=True)
    b = eng.create_recommendation("RCX:v1", "act", "r", "LOW", [], T0, commit=True)
    assert a.recommendation_id == b.recommendation_id
    assert len(ledger.read_recommendations()) == 1


def test_recommendation_parent_links_violation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _violation(eng)
    rec = eng.create_recommendation(v.violation_id, "act", "r", "LOW", [], T0, commit=True)
    ra = next(a for a in ledger.read_artifacts()
              if a["ref_id"] == rec.recommendation_id
              and a["artifact_type"] == M.ART_RECOMMENDATION)
    assert ra["parent_artifact"] == M.artifact_id(M.ART_VIOLATION, v.violation_id)


def test_recommendation_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    rec = _eng().create_recommendation("RCX:v1", "act", "r", "LOW", [], T0, commit=True)
    assert rec.recommendation_id == M.recommendation_id("RCX:v1", "act")


# ── Compliance score / analyze / derive ──
def test_compliance_score_high():
    assert M.compliance_score(_HI) > 0.7


def test_compliance_score_low():
    assert M.compliance_score(_LO) < 0.4


def test_compliance_weights_sum_one():
    assert abs(sum(M.COMPLIANCE_WEIGHTS.values()) - 1.0) < 1e-9


def test_compliance_status_labels():
    assert M.compliance_status(_HI) == COMPLIANT
    assert M.compliance_status(_LO) == NON_COMPLIANT
    assert M.compliance_status({"rule_coverage": 1.0, "evidence_completeness": 1.0}) == AT_RISK


def test_derive_result_empty_fail():
    assert M.derive_result({}) == FAIL


def test_derive_result_helper():
    assert M.derive_result({"a": True, "b": True}) == PASS
    assert M.derive_result({"a": True, "b": False}) == WARNING
    assert M.derive_result({"a": False}) == FAIL


def test_analyze(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = _eng().analyze(_HI)
    assert res["compliance_status"] == COMPLIANT
    assert res["compliance_score"] > 0.7


def test_severity_weight():
    assert M.severity_weight("CRITICAL") == 1.0
    assert M.severity_weight("???") == 0.0


# ── Report ──
def test_report_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    r = eng.generate_report("GLOBAL", _HI, T2, commit=True)
    assert r.report_id.startswith("RCP:")
    assert r.rule_count >= 1
    assert r.check_count >= 1
    assert r.violation_count >= 1


def test_report_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    a = eng.generate_report("GLOBAL", _HI, T2, commit=False)
    b = eng.generate_report("GLOBAL", _HI, T2, commit=False)
    assert a.to_dict() == b.to_dict()


def test_report_distributions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    r = eng.generate_report("GLOBAL", _HI, T2, commit=True)
    assert PASS in r.check_result_distribution
    assert ACCEPT in r.review_decision_distribution


def test_report_integrity_findings(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _rule(eng)
    eng.run_check(r.rule_id, "srcFail", FAIL, "", {}, T0, commit=True)
    _violation(eng)
    rep = eng.generate_report("GLOBAL", _HI, T1, commit=True)
    assert any("failed_check" in f for f in rep.integrity_findings)
    assert any("open_violation" in f for f in rep.integrity_findings)


def test_report_has_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", _HI, T0, commit=True)
    assert "COMPLIANCE CHECK ≠ APPROVAL" in r.disclaimer


def test_report_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.generate_report("GLOBAL", _HI, T0, commit=True)
    eng.generate_report("GLOBAL", _HI, T0, commit=True)
    assert len(ledger.read_reports()) == 1


def test_report_no_trading_verbs(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", _HI, T0, commit=True)
    d = r.to_dict()
    d.pop("disclaimer")
    blob = json.dumps(d, ensure_ascii=False).lower()
    for verb in ("buy", "sell", "place_order", "deploy", "allocate_capital"):
        assert verb not in blob


def test_report_violation_severity_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _violation(eng, sev="CRITICAL")
    r = eng.generate_report("GLOBAL", _HI, T1, commit=True)
    assert r.violation_severity_distribution.get("CRITICAL") == 1


# ── Lineage / verify ──
def test_verify_lineage_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    assert eng.verify_lineage()["ok"] is True


def test_trace_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _rule(eng)
    c = eng.run_check(r.rule_id, "s", PASS, "", {}, T0, commit=True)
    anc = eng.trace_lineage(M.artifact_id(M.ART_CHECK, c.check_id))
    assert M.artifact_id(M.ART_RULE, r.rule_id) in anc


def test_verify_chain_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    from jarvis.research_compliance.verify import verify_chain
    res = verify_chain()
    assert res["ok"] is True
    assert res["n"] >= 1


def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_compliance.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _rule(eng)
    p = sp("rc_rules.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["severity"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_compliance.verify import verify_ledger
    assert verify_ledger(ledger.RULES)["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _rule(eng, desc="d1")
    _rule(eng, desc="d2")
    p = sp("rc_rules.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:deadbeef"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_compliance.verify import verify_ledger
    assert verify_ledger(ledger.RULES)["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _rule(eng)
    p = sp("rc_rules.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows.append(dict(rows[0]))
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_compliance.verify import verify_ledger
    assert verify_ledger(ledger.RULES)["ok"] is False


def test_verify_violation_transitions_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _violation(eng)
    eng.resolve_violation(v.violation_id, T1, commit=True)
    from jarvis.research_compliance.verify import violation_transition_validation
    assert violation_transition_validation()["ok"] is True


def test_verify_detects_bad_transition(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _violation(eng)
    p = sp("rc_violations.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["to_state"] = "RESOLVED"  # illegal from GENESIS
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_compliance.verify import violation_transition_validation
    assert violation_transition_validation()["ok"] is False


def test_verify_rule_reference_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _rule(eng)
    eng.run_check(r.rule_id, "s", PASS, "", {}, T0, commit=True)
    from jarvis.research_compliance.verify import rule_reference_validation
    assert rule_reference_validation()["ok"] is True


def test_verify_detects_missing_rule(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _rule(eng)
    eng.run_check(r.rule_id, "s", PASS, "", {}, T0, commit=True)
    p = sp("rc_checks.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["rule_id"] = "RCR:ghost"
    with open(p, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    from jarvis.research_compliance.verify import rule_reference_validation
    res = rule_reference_validation()
    assert res["ok"] is False
    assert any("missing_rule" in i for i in res["issues"])


def test_verify_evidence_reference_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _rule(eng)
    e = _evidence(eng)
    eng.run_check(r.rule_id, "s", PASS, e.evidence_id, {}, T0, commit=True)
    from jarvis.research_compliance.verify import evidence_reference_validation
    assert evidence_reference_validation()["ok"] is True


def test_verify_detects_dangling_evidence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _rule(eng)
    eng.run_check(r.rule_id, "s", PASS, "RCE:ghost", {}, T0, commit=True)
    from jarvis.research_compliance.verify import evidence_reference_validation
    res = evidence_reference_validation()
    assert res["ok"] is False
    assert any("dangling_evidence" in i for i in res["issues"])


def test_verify_full_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    from jarvis.research_compliance.verify import verify_chain
    res = verify_chain()
    assert res["ok"] is True
    assert res["violation_transitions"]["ok"] is True
    assert res["rule_reference"]["ok"] is True
    assert res["evidence_reference"]["ok"] is True
    assert res["lineage"]["ok"] is True


def test_verify_lineage_cycle_detection(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _rule(eng)
    from jarvis.research_compliance.models import content_hash
    h = ledger.artifacts_head()["record_hash"]
    a1 = {"artifact_id": "RCA:c1", "artifact_type": "CHECK", "ref_id": "x1",
          "parent_artifact": "RCA:c2", "created_at": T0, "input_hash": "", "record_hash": "",
          "previous_hash": h}
    a1["record_hash"] = content_hash(a1)
    ledger.append_artifact(a1)
    a2 = {"artifact_id": "RCA:c2", "artifact_type": "CHECK", "ref_id": "x2",
          "parent_artifact": "RCA:c1", "created_at": T0, "input_hash": "", "record_hash": "",
          "previous_hash": a1["record_hash"]}
    a2["record_hash"] = content_hash(a2)
    ledger.append_artifact(a2)
    res = eng.verify_lineage()
    assert res["ok"] is False
    assert any("cycle" in i for i in res["issues"])


# ── replay / summary ──
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    from jarvis.research_compliance.verify import replay
    assert replay(eng, T0)["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    s = eng.summary(T0)
    assert s.rule_count >= 1
    assert s.check_count >= 1
    assert s.evidence_count >= 1
    assert s.review_count >= 1
    assert s.violation_count >= 1
    assert s.recommendation_count >= 1


def test_summary_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    assert eng.summary(T0).to_dict() == eng.summary(T0).to_dict()


# ── 상위 READ ONLY ──
def test_list_source_objects_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().list_source_objects("research_governance") == []


def test_list_source_objects_reads(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("rg_strategies.jsonl"), "w") as f:
        f.write(json.dumps({"strategy_id": "ST1"}) + "\n")
        f.write(json.dumps({"strategy_id": "ST2"}) + "\n")
    out = _eng().list_source_objects("research_governance")
    assert out == ["research_governance:ST1", "research_governance:ST2"]


def test_source_read_only_no_write(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    src = sp("rg_strategies.jsonl")
    with open(src, "w") as f:
        f.write(json.dumps({"strategy_id": "ST1"}) + "\n")
    before = open(src).read()
    eng = _eng()
    _full(eng)
    eng.list_source_objects("research_governance")
    assert open(src).read() == before


def test_unknown_source_layer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().list_source_objects("nonexistent") == []


def test_source_count(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("rg_strategies.jsonl"), "w") as f:
        f.write(json.dumps({"strategy_id": "ST1"}) + "\n")
    assert ledger.source_count("research_governance") == 1
    assert ledger.source_count("nope") == 0


def test_upstream_layers_covered_read_only():
    for layer in ("research_observability", "research_orchestration", "research_evolution",
                  "research_os"):
        assert layer in ledger.SOURCE_LEDGERS


# ── CLI ──
def test_cli_rule(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_compliance.__main__ import main
    rc = main(["rule", "--category", "reproducibility", "--description", "repro required",
               "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["rule"]["rule_id"].startswith("RCR:")


def test_cli_evidence(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_compliance.__main__ import main
    rc = main(["evidence", "--source", "rg:ST1", "--artifact-reference", "oos", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["evidence"]["evidence_id"].startswith("RCE:")


def test_cli_check(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_compliance.__main__ import main
    main(["rule", "--category", "reproducibility", "--description", "d", "--commit"])
    rid = json.loads(capsys.readouterr().out)["rule"]["rule_id"]
    rc = main(["check", "--rule-id", rid, "--source", "rg:ST1", "--result", "PASS", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["check"]["result"] == "PASS"


def test_cli_review(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_compliance.__main__ import main
    rc = main(["review", "--reviewer", "alice", "--target", "RCC:x", "--decision", "ACCEPT",
               "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["review"]["decision"] == "ACCEPT"


def test_cli_violation(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_compliance.__main__ import main
    rc = main(["violation", "--category", "documentation", "--source", "rg:ST1", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["violation"]["violation_id"].startswith("RCX:")


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_compliance.__main__ import main
    rc = main(["report", "--metrics-json", json.dumps(_HI), "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["report"]["report_id"].startswith("RCP:")


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_compliance.__main__ import main
    main(["rule", "--category", "documentation", "--description", "d", "--commit"])
    capsys.readouterr()
    rc = main(["verify"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_compliance.__main__ import main
    main(["rule", "--category", "documentation", "--description", "d", "--commit"])
    capsys.readouterr()
    rc = main(["replay"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_compliance.__main__ import main
    rc = main(["summary"])
    assert rc == 0
    assert "rule_count" in json.loads(capsys.readouterr().out)


# ── 보안·불변·READ ONLY 가드 ──
def test_no_forbidden_imports():
    import jarvis.research_compliance.engine as eng_mod
    import jarvis.research_compliance.models as mdl_mod
    import jarvis.research_compliance.ledger as led_mod
    import jarvis.research_compliance.verify as ver_mod
    import jarvis.research_compliance.__main__ as cli_mod
    src = ""
    for m in (eng_mod, mdl_mod, led_mod, ver_mod, cli_mod):
        with open(m.__file__) as f:
            src += f.read()
    _j = "jarvis."
    forbidden = [_j + "execution", _j + "broker", _j + "order",
                 _j + "portfolio_execution", _j + "capital_allocation", _j + "live_trading",
                 _j + "permission", _j + "risk_controller",
                 "place_order(", "submit_order(", "execute_trade(", "deploy_strategy(",
                 "allocate_capital(", "approve_for_trading(", "modify_strategy(", "auto_fix(",
                 "auto_approve("]
    for token in forbidden:
        assert token not in src, f"forbidden reference: {token}"


def test_no_execution_keyword_methods():
    import jarvis.research_compliance.engine as eng_mod
    with open(eng_mod.__file__) as f:
        src = f.read()
    for kw in ("def execute", "def deploy", "def trade", "def place_order",
               "def allocate_capital", "def approve_for_trading", "def modify_strategy",
               "def auto_fix", "def auto_approve"):
        assert kw not in src


def test_no_execution_authority_api():
    api = set(dir(ResearchComplianceEngine))
    for banned in ("execute", "deploy", "trade", "place_order", "allocate_capital",
                   "approve_for_trading", "modify_strategy", "auto_fix", "auto_approve"):
        assert banned not in api


def test_check_not_approval(tmp_path, monkeypatch):
    """점검 레코드에 approve/deploy/execute 필드가 없어야 한다."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _rule(eng)
    c = eng.run_check(r.rule_id, "s", PASS, "", {}, T0, commit=True)
    d = c.to_dict()
    for banned in ("approve", "deploy", "execute", "auto_fix"):
        assert banned not in d


def test_live_execution_disabled_invariant():
    import jarvis.config as _cfg
    assert _cfg.live_execution_enabled() is False
    assert _cfg.AUTONOMY_LEVEL < _cfg.MIN_LIVE_LEVEL


def test_autonomy_unchanged(tmp_path, monkeypatch):
    import jarvis.config as _cfg
    before = _cfg.AUTONOMY_LEVEL
    _iso(tmp_path, monkeypatch)
    _full(_eng())
    assert _cfg.AUTONOMY_LEVEL == before
    assert _cfg.live_execution_enabled() is False


def test_no_delete_or_update_api():
    import importlib
    for mod_name in ("engine", "ledger"):
        m = importlib.import_module(f"jarvis.research_compliance.{mod_name}")
        for name in dir(m):
            low = name.lower()
            assert not low.startswith("delete_")
            assert not low.startswith("update_")
            assert not low.startswith("remove_")


def test_ledger_prefix_rc(tmp_path, monkeypatch):
    for fn, _idf in ledger.ALL_LEDGERS:
        assert fn.startswith("rc_")


def test_all_ledgers_distinct():
    names = [fn for fn, _ in ledger.ALL_LEDGERS]
    assert len(names) == len(set(names)) == 8


def test_engine_no_upstream_layer_import():
    import jarvis.research_compliance.engine as eng_mod
    with open(eng_mod.__file__) as f:
        src = f.read()
    for up in ("import jarvis.research_observability", "import jarvis.research_orchestration",
               "import jarvis.research_evolution", "import jarvis.meta_intelligence"):
        assert up not in src


# ── 추가 커버리지 ──
def test_id_prefixes_distinct():
    prefixes = {
        M.rule_id("a", "b", "1")[:4],
        M.check_id("a", "b")[:4],
        M.evidence_id("a", "b")[:4],
        M.review_id("a", "b")[:4],
        M.violation_id("a", "b")[:4],
        M.violation_event_id("a", "", DETECTED)[:4],
        M.recommendation_id("a", "b")[:4],
        M.report_id("a")[:4],
        M.artifact_id("a", "b")[:4],
    }
    assert len(prefixes) == 9


def test_content_hash_excludes_chain_fields():
    r1 = {"a": 1, "previous_hash": "x", "record_hash": "y"}
    r2 = {"a": 1, "previous_hash": "z", "record_hash": "w"}
    assert M.content_hash(r1) == M.content_hash(r2)


def test_input_digest_order_matters():
    assert M.input_digest("a", "b") != M.input_digest("b", "a")


def test_metadata_hash_order_independent():
    assert M.metadata_hash({"a": 1, "b": 2}) == M.metadata_hash({"b": 2, "a": 1})


def test_checksum_deterministic():
    assert M.checksum("abc") == M.checksum("abc")
    assert M.checksum("abc") != M.checksum("abd")


def test_detect_cycle_finds():
    assert M.detect_cycle([("a", "b"), ("b", "a")])


def test_detect_cycle_none():
    assert M.detect_cycle([("a", "b"), ("b", "c")]) == []


def test_rule_categories_count():
    assert len(M.RULE_CATEGORIES) == 6


def test_check_results_count():
    assert len(M.CHECK_RESULTS) == 3


def test_review_decisions_count():
    assert len(M.REVIEW_DECISIONS) == 3


def test_violation_states_count():
    assert len(M.VIOLATION_STATES) == 4


def test_node_types_count():
    assert len(M.NODE_TYPES) == 6


def test_framework_requirement_sets():
    assert M.COMPLETENESS_REQUIREMENTS == ("hypothesis", "dataset_reference", "experiment_lineage")
    assert M.VALIDATION_REQUIREMENTS == ("out_of_sample", "robustness", "reproducibility")
    assert M.INTEGRITY_REQUIREMENTS == ("immutable_artifact", "lineage_continuity",
                                        "evidence_present")


def test_no_commit_no_files(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _rule(eng, commit=False)
    _evidence(eng, commit=False)
    for fn, _ in ledger.ALL_LEDGERS:
        assert ledger.read_jsonl(fn) == []


def test_rule_to_dict_roundtrip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _rule(_eng())
    d = r.to_dict()
    assert d["rule_id"] == r.rule_id
    assert set(("category", "description", "severity", "version")).issubset(d)


def test_report_metrics_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", _HI, T0, commit=True)
    assert r.metrics == _HI


def test_multiple_scopes_distinct_reports(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.generate_report("A", _HI, T0, commit=True)
    eng.generate_report("B", _HI, T0, commit=True)
    assert len(ledger.read_reports()) == 2


def test_rule_input_hash(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _rule(_eng())
    assert r.input_hash == M.input_digest(M.C_VALIDATION_REQUIREMENT, "OOS evidence required",
                                          "1.0")


def test_evidence_kept_fields(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _evidence(_eng())
    assert e.source == "research_governance:ST1"
    assert e.artifact_reference == "artifact:oos_curve"


def test_violation_evidence_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    v = _violation(_eng())
    assert v.evidence == ["ev1"]


def test_summary_state_distributions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    s = eng.summary(T0)
    assert PASS in s.check_result_distribution
    assert DETECTED in s.violation_state_distribution


def test_integrity_findings_empty_when_clean(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _rule(eng)
    eng.run_check(r.rule_id, "s", PASS, "", {}, T0, commit=True)
    assert eng.integrity_findings() == []


def test_source_ledgers_not_rc_prefixed():
    for layer, (fn, idf) in ledger.SOURCE_LEDGERS.items():
        assert not fn.startswith("rc_")
        assert isinstance(idf, str)


def test_engine_reused(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r1 = _rule(eng, desc="d1")
    r2 = _rule(eng, desc="d2")
    assert r1.rule_id != r2.rule_id
    assert len(ledger.read_rules()) == 2


def test_disclaimer_full_phrases(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", _HI, T0, commit=True)
    for phrase in ("COMPLIANCE CHECK ≠ APPROVAL", "VIOLATION DETECTION ≠ CORRECTION",
                   "RECOMMENDATION ≠ ACTION", "AUDIT RESULT ≠ DEPLOYMENT PERMISSION"):
        assert phrase in r.disclaimer


def test_compliance_score_partial_metrics():
    s = M.compliance_score({"evidence_completeness": 1.0, "check_pass_rate": 1.0})
    assert abs(s - (0.25 + 0.25)) < 1e-9


def test_recommendation_priorities():
    assert set(M.PRIORITIES) == {"LOW", "MEDIUM", "HIGH", "URGENT"}
