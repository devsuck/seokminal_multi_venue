"""P10.20 Research Governance Feedback Intelligence 테스트. **거버넌스 폐루프 학습 기록 전용.**

피드백(불변·범주 검증)·이슈(생명주기 DETECTED→ANALYZED→TRACKED→ARCHIVED·심각도·추적)·패턴(재발 탐지·
신뢰도 계산·불변)·테마(집계·계보·불변)·집계(결정적)·검토(비집행)·리포트(결정적)·verify(체인/변조/중복/전이/
집계/참조/계보)·replay·상위 READ ONLY 보호·CLI·보안(금지import·정책수정/실행/승인/자동조치 없음·상위 원장
무변경·삭제 API 없음·불변·FEEDBACK≠CHANGE·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import json
import os

import pytest

from jarvis.governance_feedback import ledger
from jarvis.governance_feedback import models as M
from jarvis.governance_feedback.engine import GovernanceFeedbackEngine
from jarvis.governance_feedback.models import (
    ACKNOWLEDGE,
    ANALYZED,
    ARCHIVED,
    DECLINING,
    DETECTED,
    ESCALATE,
    IMPROVING,
    MONITOR,
    STABLE,
    TRACKED,
    IllegalTransition,
    ImmutableFeedbackError,
    ImmutablePatternError,
    InvalidFeedbackCategory,
    InvalidReviewDecision,
    UnknownIssue,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"
T2 = "2026-07-23T00:02:00Z"

_HI = {"issue_resolution_rate": 0.9, "recurring_issue_rate": 0.1, "feedback_responsiveness": 0.85,
       "pattern_stability": 0.8, "documentation_coverage": 0.9}
_LO = {"issue_resolution_rate": 0.1, "recurring_issue_rate": 0.9, "feedback_responsiveness": 0.2,
       "pattern_stability": 0.2, "documentation_coverage": 0.1}


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.governance_feedback.ledger.state_path", sp)
    return sp


def _eng():
    return GovernanceFeedbackEngine()


def _fb(eng, layer="research_compliance", cat=None, desc="OOS evidence missing", ev="ref1",
        sev="HIGH", commit=True):
    return eng.record_feedback(layer, cat or M.F_VALIDATION_ISSUE, desc, ev, sev, T0,
                               commit=commit)


def _issue(eng, src="research_compliance:ST1", freq=3, impact="HIGH", commit=True):
    return eng.register_issue(src, freq, impact, "", T0, commit=commit)


def _full(eng):
    """layer→feedback→issue→pattern→theme→aggregate→review→report end-to-end."""
    f = _fb(eng)
    i = _issue(eng)
    p = eng.analyze_pattern(M.F_VALIDATION_ISSUE, None, None, T0, commit=True)
    eng.create_theme("strengthen OOS validation", [p.pattern_id, f.feedback_id], "HIGH", T0,
                     commit=True)
    eng.aggregate_feedback("2026-Q3", _HI, None, T0, commit=True)
    eng.create_review("gov_officer", i.issue_id, ESCALATE, "recurring", T0, commit=True)
    eng.generate_report("GLOBAL", _HI, T1, commit=True)
    return f, i, p


# ── Feedback ──
def test_feedback_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    f = _fb(_eng())
    assert f.feedback_id.startswith("GFB:")
    assert f.category == M.F_VALIDATION_ISSUE
    assert f.severity == "HIGH"


def test_feedback_invalid_category(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(InvalidFeedbackCategory):
        _eng().record_feedback("L", "not_a_cat", "d", "", "LOW", T0, commit=True)


def test_feedback_all_categories(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    for i, cat in enumerate(M.FEEDBACK_CATEGORIES):
        f = eng.record_feedback("L", cat, f"d{i}", "", "MEDIUM", T0, commit=True)
        assert f.category == cat
    assert len(ledger.read_feedback()) == len(M.FEEDBACK_CATEGORIES)


def test_feedback_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _fb(eng)
    b = _fb(eng)
    assert a.feedback_id == b.feedback_id
    assert len(ledger.read_feedback()) == 1


def test_feedback_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _fb(eng, sev="HIGH")
    with pytest.raises(ImmutableFeedbackError):
        _fb(eng, sev="LOW")


def test_feedback_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    f = _fb(_eng())
    assert f.feedback_id == M.feedback_id("research_compliance", M.F_VALIDATION_ISSUE,
                                          "OOS evidence missing")


def test_feedback_not_committed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _fb(_eng(), commit=False)
    assert ledger.read_feedback() == []


def test_feedback_records_layer_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    f = _fb(_eng())
    assert ledger.artifact_exists(M.artifact_id(M.ART_LAYER, "research_compliance"))
    fa = next(a for a in ledger.read_artifacts()
              if a["ref_id"] == f.feedback_id and a["artifact_type"] == M.ART_FEEDBACK)
    assert fa["parent_artifact"] == M.artifact_id(M.ART_LAYER, "research_compliance")


def test_feedback_by_category(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _fb(eng, desc="d1")
    _fb(eng, desc="d2")
    assert len(ledger.feedback_by_category(M.F_VALIDATION_ISSUE)) == 2


# ── Issue ──
def test_issue_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    i = _issue(_eng())
    assert i.issue_id.startswith("GFI:")
    assert i.to_state == DETECTED
    assert i.frequency == 3


def test_issue_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    i = _issue(eng)
    eng.transition_issue(i.issue_id, ANALYZED, T1, commit=True)
    eng.transition_issue(i.issue_id, TRACKED, T2, commit=True)
    assert eng.issue_state(i.issue_id) == TRACKED


def test_issue_track_helper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    i = _issue(eng)
    eng.track_issue(i.issue_id, T1, commit=True)
    assert eng.issue_state(i.issue_id) == TRACKED


def test_issue_illegal_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    i = _issue(eng)
    with pytest.raises(IllegalTransition):
        eng.transition_issue(i.issue_id, TRACKED, T1, commit=True)


def test_issue_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownIssue):
        _eng().transition_issue("GFI:nope", ANALYZED, T1, commit=True)


def test_issue_archived_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    i = _issue(eng)
    eng.transition_issue(i.issue_id, ARCHIVED, T1, commit=True)
    with pytest.raises(IllegalTransition):
        eng.transition_issue(i.issue_id, ANALYZED, T2, commit=True)


def test_issue_severity_impact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    i = _issue(_eng(), impact="CRITICAL")
    assert i.impact == "CRITICAL"


def test_issue_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _issue(eng)
    b = _issue(eng)
    assert a.issue_id == b.issue_id
    assert len(ledger.distinct_issues()) == 1


def test_issue_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    i = _issue(_eng())
    assert i.issue_id == M.issue_id("research_compliance:ST1", "HIGH")


def test_issue_frequency_map(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_issue("srcA", 1, "HIGH", "", T0, commit=True)
    eng.register_issue("srcB", 1, "LOW", "", T0, commit=True)
    freq = eng.issue_frequency()
    assert freq.get("srcA") == 1 and freq.get("srcB") == 1


def test_issue_can_transition_table():
    assert M.can_transition_issue("", DETECTED)
    assert M.can_transition_issue(DETECTED, ANALYZED)
    assert M.can_transition_issue(ANALYZED, TRACKED)
    assert not M.can_transition_issue(DETECTED, TRACKED)
    assert not M.can_transition_issue(TRACKED, DETECTED)


def test_issue_no_fix_field(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    i = _issue(_eng())
    d = i.to_dict()
    for banned in ("fix", "correct", "remediate", "auto"):
        assert banned not in d


# ── Pattern ──
def test_pattern_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = _eng().analyze_pattern(M.F_VALIDATION_ISSUE, ["L1", "L2"], 4, T0, commit=True)
    assert p.pattern_id.startswith("GFP:")
    assert p.occurrences == 4
    assert p.related_sources == ["L1", "L2"]


def test_pattern_confidence_calculation():
    # 5+ occurrences, 3+ sources -> full confidence 0.6*1 + 0.4*1 = 1.0
    assert M.pattern_confidence(5, 3) == 1.0
    # 0 occurrences -> 0
    assert M.pattern_confidence(0, 0) == 0.0
    # partial
    assert abs(M.pattern_confidence(5, 0) - 0.6) < 1e-9
    assert abs(M.pattern_confidence(0, 3) - 0.4) < 1e-9


def test_pattern_recurrence_detection(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.record_feedback("L1", M.F_DATA_ISSUE, "d1", "", "HIGH", T0, commit=True)
    eng.record_feedback("L2", M.F_DATA_ISSUE, "d2", "", "HIGH", T0, commit=True)
    p = eng.analyze_pattern(M.F_DATA_ISSUE, None, None, T0, commit=True)
    assert p.occurrences == 2
    assert set(p.related_sources) == {"L1", "L2"}


def test_pattern_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.analyze_pattern(M.F_DATA_ISSUE, ["L1"], 2, T0, commit=True)
    with pytest.raises(ImmutablePatternError):
        eng.analyze_pattern(M.F_DATA_ISSUE, ["L1", "L2"], 5, T0, commit=True)


def test_pattern_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.analyze_pattern(M.F_DATA_ISSUE, ["L1"], 2, T0, commit=True)
    b = eng.analyze_pattern(M.F_DATA_ISSUE, ["L1"], 2, T0, commit=True)
    assert a.pattern_id == b.pattern_id
    assert len(ledger.read_patterns()) == 1


def test_pattern_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = _eng().analyze_pattern(M.F_DATA_ISSUE, ["L1"], 1, T0, commit=True)
    assert p.pattern_id == M.pattern_id(M.F_DATA_ISSUE)


def test_recurring_patterns(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.analyze_pattern(M.F_DATA_ISSUE, ["L1", "L2", "L3"], 5, T0, commit=True)  # conf 1.0
    eng.analyze_pattern(M.F_WORKFLOW_ISSUE, [], 0, T0, commit=True)  # conf 0.0
    rec = eng.recurring_patterns(0.6)
    assert len(rec) == 1


# ── Theme ──
def test_theme_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    t = _eng().create_theme("improve docs", ["GFB:x"], "HIGH", T0, commit=True)
    assert t.theme_id.startswith("GFT:")
    assert t.priority == "HIGH"
    assert t.supporting_feedback == ["GFB:x"]


def test_theme_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.create_theme("improve docs", [], "LOW", T0, commit=True)
    b = eng.create_theme("improve docs", [], "HIGH", T0, commit=True)
    assert a.theme_id == b.theme_id
    assert a.priority == b.priority == "LOW"  # first wins
    assert len(ledger.read_themes()) == 1


def test_theme_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    t = _eng().create_theme("improve docs", [], "LOW", T0, commit=True)
    assert t.theme_id == M.theme_id("improve docs")


def test_theme_parent_links_pattern(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = eng.analyze_pattern(M.F_DATA_ISSUE, ["L1"], 2, T0, commit=True)
    t = eng.create_theme("theme1", [p.pattern_id], "HIGH", T0, commit=True)
    ta = next(a for a in ledger.read_artifacts()
              if a["ref_id"] == t.theme_id and a["artifact_type"] == M.ART_THEME)
    assert ta["parent_artifact"] == M.artifact_id(M.ART_PATTERN, p.pattern_id)


def test_theme_analytical_no_action_field(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    t = _eng().create_theme("t", [], "LOW", T0, commit=True)
    d = t.to_dict()
    for banned in ("action", "apply", "implement", "execute"):
        assert banned not in d


# ── Aggregation ──
def test_aggregate_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _fb(eng)
    agg = eng.aggregate_feedback("2026-Q3", _HI, None, T0, commit=True)
    assert agg.aggregation_id.startswith("GFA:")
    assert agg.period == "2026-Q3"
    assert "category_counts" in agg.trend_summary


def test_aggregate_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _fb(eng)
    a = eng.aggregate_feedback("2026-Q3", _HI, None, T0, commit=False)
    b = eng.aggregate_feedback("2026-Q3", _HI, None, T0, commit=False)
    assert a.to_dict() == b.to_dict()


def test_aggregate_duplicate_detection(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.aggregate_feedback("2026-Q3", _HI, None, T0, commit=True)
    eng.aggregate_feedback("2026-Q3", _HI, None, T0, commit=True)
    assert len(ledger.read_aggregations()) == 1


def test_aggregate_trend_labels(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    up = eng.aggregate_feedback("P1", _HI, 0.1, T0, commit=True)
    assert up.trend_summary["label"] == IMPROVING
    down = eng.aggregate_feedback("P2", _LO, 0.9, T0, commit=True)
    assert down.trend_summary["label"] == DECLINING


def test_aggregate_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    agg = _eng().aggregate_feedback("2026-Q3", {}, None, T0, commit=True)
    assert agg.aggregation_id == M.aggregation_id("2026-Q3")


# ── Review ──
def test_review_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    rv = _eng().create_review("officer", "GFI:x", ACKNOWLEDGE, "seen", T0, commit=True)
    assert rv.review_id.startswith("GFV:")
    assert rv.decision == ACKNOWLEDGE


def test_review_all_decisions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    for i, dec in enumerate(M.REVIEW_DECISIONS):
        rv = eng.create_review(f"r{i}", "tgt", dec, "", T0, commit=True)
        assert rv.decision == dec


def test_review_invalid_decision(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(InvalidReviewDecision):
        _eng().create_review("r", "tgt", "APPROVE", "", T0, commit=True)


def test_review_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.create_review("r", "tgt", ACKNOWLEDGE, "", T0, commit=True)
    b = eng.create_review("r", "tgt", ESCALATE, "", T0, commit=True)
    assert a.review_id == b.review_id
    assert a.decision == b.decision == ACKNOWLEDGE


# ── Governance score / analyze ──
def test_governance_score_high():
    assert M.governance_score(_HI) > 0.7


def test_governance_score_low():
    assert M.governance_score(_LO) < 0.4


def test_governance_score_recurring_inverse():
    # recurring_issue_rate 0.0 -> inverse 1.0 contributes 0.25
    s = M.governance_score({"recurring_issue_rate": 0.0})
    assert abs(s - 0.25) < 1e-9


def test_governance_weights_sum_one():
    assert abs(sum(M.GOVERNANCE_WEIGHTS.values()) - 1.0) < 1e-9


def test_governance_health_labels():
    assert M.governance_health(_HI) == "HEALTHY"
    assert M.governance_health(_LO) == "DEGRADED"
    assert M.governance_health({"issue_resolution_rate": 1.0,
                                "feedback_responsiveness": 1.0}) == "WARNING"


def test_trend_label():
    assert M.trend_label(0.1) == IMPROVING
    assert M.trend_label(-0.1) == DECLINING
    assert M.trend_label(0.0) == STABLE


def test_analyze(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = _eng().analyze(_HI)
    assert res["governance_health"] == "HEALTHY"
    assert res["governance_score"] > 0.7


def test_severity_weight():
    assert M.severity_weight("CRITICAL") == 1.0
    assert M.severity_weight("???") == 0.0


# ── Report ──
def test_report_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    r = eng.generate_report("GLOBAL", _HI, T2, commit=True)
    assert r.report_id.startswith("GFR:")
    assert r.feedback_count >= 1
    assert r.issue_count >= 1
    assert r.pattern_count >= 1


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
    assert M.F_VALIDATION_ISSUE in r.feedback_category_distribution
    assert DETECTED in r.issue_state_distribution


def test_report_unresolved_and_opportunity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    r = eng.generate_report("GLOBAL", _HI, T2, commit=True)
    assert len(r.unresolved_issue_summary) >= 1
    assert len(r.improvement_opportunity_map) >= 1


def test_report_has_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", _HI, T0, commit=True)
    assert "FEEDBACK ≠ CHANGE" in r.disclaimer


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


def test_report_recurring_pattern_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.analyze_pattern(M.F_DATA_ISSUE, ["L1", "L2", "L3"], 5, T0, commit=True)
    r = eng.generate_report("GLOBAL", _HI, T1, commit=True)
    assert r.recurring_pattern_count == 1


# ── Lineage / verify ──
def test_verify_lineage_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    assert eng.verify_lineage()["ok"] is True


def test_trace_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    f = _fb(eng)
    anc = eng.trace_lineage(M.artifact_id(M.ART_FEEDBACK, f.feedback_id))
    assert M.artifact_id(M.ART_LAYER, "research_compliance") in anc


def test_verify_chain_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    from jarvis.governance_feedback.verify import verify_chain
    res = verify_chain()
    assert res["ok"] is True
    assert res["n"] >= 1


def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_feedback.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _fb(eng)
    p = sp("gf_feedback.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["severity"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.governance_feedback.verify import verify_ledger
    assert verify_ledger(ledger.FEEDBACK)["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _fb(eng, desc="d1")
    _fb(eng, desc="d2")
    p = sp("gf_feedback.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:deadbeef"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.governance_feedback.verify import verify_ledger
    assert verify_ledger(ledger.FEEDBACK)["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _fb(eng)
    p = sp("gf_feedback.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows.append(dict(rows[0]))
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.governance_feedback.verify import verify_ledger
    assert verify_ledger(ledger.FEEDBACK)["ok"] is False


def test_verify_issue_transitions_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    i = _issue(eng)
    eng.track_issue(i.issue_id, T1, commit=True)
    from jarvis.governance_feedback.verify import issue_transition_validation
    assert issue_transition_validation()["ok"] is True


def test_verify_detects_bad_transition(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _issue(eng)
    p = sp("gf_issues.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["to_state"] = "TRACKED"  # illegal from GENESIS
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.governance_feedback.verify import issue_transition_validation
    assert issue_transition_validation()["ok"] is False


def test_verify_aggregation_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.aggregate_feedback("2026-Q3", _HI, None, T0, commit=True)
    from jarvis.governance_feedback.verify import aggregation_validation
    assert aggregation_validation()["ok"] is True


def test_verify_detects_invalid_aggregation(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.aggregate_feedback("2026-Q3", _HI, None, T0, commit=True)
    p = sp("gf_aggregations.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["period"] = "2027-Q1"  # id no longer matches period
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.governance_feedback.verify import aggregation_validation
    res = aggregation_validation()
    assert res["ok"] is False
    assert any("invalid_aggregation" in i for i in res["issues"])


def test_verify_reference_dangling(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _fb(eng)
    from jarvis.governance_feedback.models import content_hash
    rec = {"artifact_id": "GFX:broken", "artifact_type": "THEME", "ref_id": "x",
           "parent_artifact": "GFX:ghost", "created_at": T0, "input_hash": "", "record_hash": "",
           "previous_hash": ledger.artifacts_head()["record_hash"]}
    rec["record_hash"] = content_hash(rec)
    ledger.append_artifact(rec)
    from jarvis.governance_feedback.verify import reference_validation
    assert reference_validation()["ok"] is False


def test_verify_full_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    from jarvis.governance_feedback.verify import verify_chain
    res = verify_chain()
    assert res["ok"] is True
    assert res["issue_transitions"]["ok"] is True
    assert res["aggregation"]["ok"] is True
    assert res["reference"]["ok"] is True
    assert res["lineage"]["ok"] is True


def test_verify_lineage_cycle_detection(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _fb(eng)
    from jarvis.governance_feedback.models import content_hash
    h = ledger.artifacts_head()["record_hash"]
    a1 = {"artifact_id": "GFX:c1", "artifact_type": "THEME", "ref_id": "x1",
          "parent_artifact": "GFX:c2", "created_at": T0, "input_hash": "", "record_hash": "",
          "previous_hash": h}
    a1["record_hash"] = content_hash(a1)
    ledger.append_artifact(a1)
    a2 = {"artifact_id": "GFX:c2", "artifact_type": "THEME", "ref_id": "x2",
          "parent_artifact": "GFX:c1", "created_at": T0, "input_hash": "", "record_hash": "",
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
    from jarvis.governance_feedback.verify import replay
    assert replay(eng, T0)["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    s = eng.summary(T0)
    assert s.feedback_count >= 1
    assert s.issue_count >= 1
    assert s.pattern_count >= 1
    assert s.theme_count >= 1
    assert s.aggregation_count >= 1
    assert s.review_count >= 1


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
    for layer in ("research_compliance", "research_observability", "research_orchestration",
                  "research_evolution"):
        assert layer in ledger.SOURCE_LEDGERS


# ── CLI ──
def test_cli_feedback(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_feedback.__main__ import main
    rc = main(["feedback", "--source-layer", "rc", "--category", "data_issue", "--description",
               "d", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["feedback"]["feedback_id"].startswith("GFB:")


def test_cli_issue(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_feedback.__main__ import main
    rc = main(["issue", "--source", "rc:ST1", "--frequency", "3", "--impact", "HIGH", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["issue"]["issue_id"].startswith("GFI:")


def test_cli_pattern(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_feedback.__main__ import main
    rc = main(["pattern", "--issue-type", "data_issue", "--sources", "L1,L2", "--occurrences",
               "4", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["pattern"]["pattern_id"].startswith("GFP:")


def test_cli_theme(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_feedback.__main__ import main
    rc = main(["theme", "--description", "improve docs", "--priority", "HIGH", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["theme"]["theme_id"].startswith("GFT:")


def test_cli_aggregate(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_feedback.__main__ import main
    rc = main(["aggregate", "--period", "2026-Q3", "--metrics-json", json.dumps(_HI), "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["aggregation"]["aggregation_id"].startswith("GFA:")


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_feedback.__main__ import main
    rc = main(["report", "--metrics-json", json.dumps(_HI), "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["report"]["report_id"].startswith("GFR:")


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_feedback.__main__ import main
    main(["feedback", "--source-layer", "rc", "--category", "data_issue", "--description", "d",
          "--commit"])
    capsys.readouterr()
    rc = main(["verify"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_feedback.__main__ import main
    main(["feedback", "--source-layer", "rc", "--category", "data_issue", "--description", "d",
          "--commit"])
    capsys.readouterr()
    rc = main(["replay"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_feedback.__main__ import main
    rc = main(["summary"])
    assert rc == 0
    assert "feedback_count" in json.loads(capsys.readouterr().out)


# ── 보안·불변·READ ONLY 가드 ──
def test_no_forbidden_imports():
    import jarvis.governance_feedback.engine as eng_mod
    import jarvis.governance_feedback.models as mdl_mod
    import jarvis.governance_feedback.ledger as led_mod
    import jarvis.governance_feedback.verify as ver_mod
    import jarvis.governance_feedback.__main__ as cli_mod
    src = ""
    for m in (eng_mod, mdl_mod, led_mod, ver_mod, cli_mod):
        with open(m.__file__) as f:
            src += f.read()
    _j = "jarvis."
    forbidden = [_j + "execution", _j + "broker", _j + "order",
                 _j + "portfolio_execution", _j + "capital_allocation", _j + "live_trading",
                 _j + "permission", _j + "risk_controller",
                 "place_order(", "submit_order(", "execute_trade(", "deploy_strategy(",
                 "allocate_capital(", "modify_policy(", "change_permission(", "auto_fix(",
                 "auto_apply("]
    for token in forbidden:
        assert token not in src, f"forbidden reference: {token}"


def test_no_execution_keyword_methods():
    import jarvis.governance_feedback.engine as eng_mod
    with open(eng_mod.__file__) as f:
        src = f.read()
    for kw in ("def execute", "def deploy", "def trade", "def place_order",
               "def allocate_capital", "def modify_policy", "def change_permission",
               "def auto_fix", "def auto_apply"):
        assert kw not in src


def test_no_execution_authority_api():
    api = set(dir(GovernanceFeedbackEngine))
    for banned in ("execute", "deploy", "trade", "place_order", "allocate_capital",
                   "modify_policy", "change_permission", "auto_fix", "auto_apply"):
        assert banned not in api


def test_feedback_not_change(tmp_path, monkeypatch):
    """피드백 레코드에 change/apply/modify/execute 필드가 없어야 한다."""
    _iso(tmp_path, monkeypatch)
    f = _fb(_eng())
    d = f.to_dict()
    for banned in ("change", "apply", "modify", "execute", "deploy"):
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
        m = importlib.import_module(f"jarvis.governance_feedback.{mod_name}")
        for name in dir(m):
            low = name.lower()
            assert not low.startswith("delete_")
            assert not low.startswith("update_")
            assert not low.startswith("remove_")


def test_ledger_prefix_gf(tmp_path, monkeypatch):
    for fn, _idf in ledger.ALL_LEDGERS:
        assert fn.startswith("gf_")


def test_all_ledgers_distinct():
    names = [fn for fn, _ in ledger.ALL_LEDGERS]
    assert len(names) == len(set(names)) == 8


def test_engine_no_upstream_layer_import():
    import jarvis.governance_feedback.engine as eng_mod
    with open(eng_mod.__file__) as f:
        src = f.read()
    for up in ("import jarvis.research_compliance", "import jarvis.research_observability",
               "import jarvis.research_orchestration", "import jarvis.meta_intelligence"):
        assert up not in src


# ── 추가 커버리지 ──
def test_id_prefixes_distinct():
    prefixes = {
        M.feedback_id("a", "b", "c")[:4],
        M.issue_id("a", "b")[:4],
        M.issue_event_id("a", "", DETECTED)[:4],
        M.pattern_id("a")[:4],
        M.theme_id("a")[:4],
        M.aggregation_id("a")[:4],
        M.review_id("a", "b")[:4],
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


def test_detect_cycle_finds():
    assert M.detect_cycle([("a", "b"), ("b", "a")])


def test_detect_cycle_none():
    assert M.detect_cycle([("a", "b"), ("b", "c")]) == []


def test_feedback_categories_count():
    assert len(M.FEEDBACK_CATEGORIES) == 6


def test_issue_states_count():
    assert len(M.ISSUE_STATES) == 4


def test_review_decisions_count():
    assert len(M.REVIEW_DECISIONS) == 3


def test_node_types_count():
    assert len(M.NODE_TYPES) == 6


def test_pattern_confidence_bounds():
    assert M.pattern_confidence(100, 100) == 1.0
    assert M.pattern_confidence(-5, -5) == 0.0


def test_no_commit_no_files(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _fb(eng, commit=False)
    _issue(eng, commit=False)
    for fn, _ in ledger.ALL_LEDGERS:
        assert ledger.read_jsonl(fn) == []


def test_feedback_to_dict_roundtrip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    f = _fb(_eng())
    d = f.to_dict()
    assert d["feedback_id"] == f.feedback_id
    assert set(("source_layer", "category", "description", "severity")).issubset(d)


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


def test_feedback_input_hash(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    f = _fb(_eng())
    assert f.input_hash == M.input_digest("research_compliance", M.F_VALIDATION_ISSUE,
                                          "OOS evidence missing")


def test_pattern_related_sources_sorted(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = _eng().analyze_pattern(M.F_DATA_ISSUE, ["L3", "L1", "L2"], 3, T0, commit=True)
    assert p.related_sources == ["L1", "L2", "L3"]


def test_summary_state_distributions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    s = eng.summary(T0)
    assert M.F_VALIDATION_ISSUE in s.feedback_category_distribution
    assert DETECTED in s.issue_state_distribution


def test_unresolved_issue_summary_empty_when_archived(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    i = _issue(eng)
    eng.transition_issue(i.issue_id, ARCHIVED, T1, commit=True)
    assert eng.unresolved_issue_summary() == []


def test_source_ledgers_not_gf_prefixed():
    for layer, (fn, idf) in ledger.SOURCE_LEDGERS.items():
        assert not fn.startswith("gf_")
        assert isinstance(idf, str)


def test_engine_reused(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    f1 = _fb(eng, desc="d1")
    f2 = _fb(eng, desc="d2")
    assert f1.feedback_id != f2.feedback_id
    assert len(ledger.read_feedback()) == 2


def test_disclaimer_full_phrases(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", _HI, T0, commit=True)
    for phrase in ("FEEDBACK ≠ CHANGE", "PATTERN ≠ DECISION", "RECOMMENDATION ≠ IMPLEMENTATION",
                   "TREND ≠ AUTOMATIC ACTION"):
        assert phrase in r.disclaimer


def test_governance_score_partial_metrics():
    s = M.governance_score({"issue_resolution_rate": 1.0, "feedback_responsiveness": 1.0})
    assert abs(s - (0.30 + 0.20)) < 1e-9


def test_improvement_opportunity_map(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    t = eng.create_theme("t1", ["GFB:a", "GFB:b"], "HIGH", T0, commit=True)
    m = eng.improvement_opportunity_map()
    assert m.get(t.theme_id) == 2
