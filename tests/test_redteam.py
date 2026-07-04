"""Red-team 통제층 테스트 — 오늘 교훈이 자동 요구되나."""
from __future__ import annotations

from jarvis.redteam.controls import required_controls
from jarvis.redteam.review import audit_registry, review_strategy


def test_extreme_entry_requires_confound():
    req = required_controls({"market": "US", "entry_at_extreme": True, "timeframe": "15m", "uses_swings": True})
    assert "entry_confound" in req   # SMT 잡는 통제
    assert "lookahead" in req


def test_bonus_issue_requires_ex_date():
    req = required_controls({"market": "KR", "family": "event", "event_type": "bonus_issue"})
    assert "ex_date_adjustment" in req   # 무상증자 아티팩트 잡는 통제


def test_multiple_variants_requires_bh():
    req = required_controls({"market": "US", "n_variants": 8})
    assert "multiple_testing" in req


def test_kr_equity_requires_survivorship():
    assert "survivorship" in required_controls({"market": "KR", "family": "event"})


def test_base_controls_always():
    req = required_controls({"market": "FUTURES", "family": "trend"})
    assert set(["random_baseline", "walk_forward", "cost_stress"]).issubset(req)


def test_review_rejects_on_failed_control():
    r = review_strategy({"market": "US", "entry_at_extreme": True, "uses_swings": True, "timeframe": "15m"},
                        {"random_baseline": "passed", "walk_forward": "passed", "cost_stress": "passed",
                         "survivorship": "passed", "lookahead": "failed", "entry_confound": "failed"})
    assert r["verdict"] == "REJECTED"
    assert "entry_confound" in r["failed"]


def test_review_blocks_on_missing():
    r = review_strategy({"market": "KR", "family": "event", "event_type": "bonus_issue"},
                        {"random_baseline": "passed", "walk_forward": "passed", "cost_stress": "passed",
                         "survivorship": "passed", "outlier_dependence": "passed"})
    assert r["verdict"] == "BLOCKED"
    assert "ex_date_adjustment" in r["missing"]


def test_review_clears_when_all_passed():
    r = review_strategy({"market": "KR", "family": "event", "entry": "next_open"},
                        {"random_baseline": "passed", "walk_forward": "passed", "cost_stress": "passed",
                         "survivorship": "passed", "outlier_dependence": "passed"})
    assert r["verdict"] == "CLEARED"


def test_audit_agrees_with_human():
    a = audit_registry()
    assert a["human_redteam_agree"] == a["n"]   # 전부 일치(오늘 판단 검증)
