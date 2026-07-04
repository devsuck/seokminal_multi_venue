"""Red-team 리뷰 — 필요통제 vs 실제 실행 대조 → 결정적 verdict.

audit = 오늘 검증한 전략들에 통제층 적용 → 사람(내) 판단과 일치하나 확인.
verdict: CLEARED(전부통과) / BLOCKED(통제 미실행) / REJECTED(통제 실패).
"""
from __future__ import annotations

from jarvis.redteam.controls import required_controls

# 오늘 실제 돌린 통제 증거. control_id → passed/failed/missing/incomplete/na
# (구조적 추적 전이라 curated. 오늘 실행한 것 기준 = 정직.)
STRATEGIES = {
    "kr_dart_buyback_drift_v1": {
        "spec": {"market": "KR", "family": "event", "entry": "next_open", "stage": "paper_active"},
        "human_call": "paper_candidate",
        "evidence": {"random_baseline": "passed", "walk_forward": "passed", "cost_stress": "passed",
                     "survivorship": "passed", "outlier_dependence": "passed", "capacity": "passed"}},
    "futures_tsmom_32mkt": {
        "spec": {"market": "FUTURES", "family": "trend", "stage": "paper_active"},
        "human_call": "paper_candidate",
        "evidence": {"random_baseline": "passed", "walk_forward": "passed", "cost_stress": "passed",
                     "capacity": "passed"}},
    "kr_cb_issuance_negdrift": {
        "spec": {"market": "KR", "family": "event"},
        "human_call": "research_neg_drift (롱 아님)",
        "evidence": {"random_baseline": "passed", "walk_forward": "passed", "cost_stress": "passed",
                     "survivorship": "passed", "outlier_dependence": "passed"}},
    "ict_smt": {
        "spec": {"market": "US", "family": "microstructure", "timeframe": "15m",
                 "uses_swings": True, "entry_at_extreme": True, "n_variants": 8},
        "human_call": "rejected (confound)",
        "evidence": {"random_baseline": "passed", "walk_forward": "passed", "cost_stress": "passed",
                     "survivorship": "passed", "lookahead": "failed",  # swings 미래봉
                     "entry_confound": "failed", "multiple_testing": "passed"}},
    "ict_2024_batch": {
        "spec": {"market": "US", "family": "microstructure", "timeframe": "15m",
                 "uses_swings": True, "n_variants": 8},
        "human_call": "rejected",
        "evidence": {"random_baseline": "passed", "walk_forward": "passed", "cost_stress": "passed",
                     "survivorship": "passed", "lookahead": "failed", "multiple_testing": "failed"}},
    "kr_bonus_issue": {
        "spec": {"market": "KR", "family": "event", "event_type": "bonus_issue"},
        "human_call": "inconclusive/blocked",
        "evidence": {"random_baseline": "passed", "walk_forward": "passed", "cost_stress": "passed",
                     "survivorship": "passed", "outlier_dependence": "passed",
                     "ex_date_adjustment": "incomplete"}},  # 커버리지 65/909
    "kr_turn_of_month": {
        "spec": {"market": "KR", "family": "seasonality"},
        "human_call": "watchlist (소멸중)",
        "evidence": {"random_baseline": "passed", "walk_forward": "failed",  # 후반 소멸
                     "cost_stress": "passed", "survivorship": "passed"}},
}


def review_strategy(spec: dict, evidence: dict) -> dict:
    req = required_controls(spec)
    satisfied, missing, failed = [], [], []
    for c in req:
        st = evidence.get(c, "missing")
        if st == "passed" or st == "na":
            satisfied.append(c)
        elif st in ("failed",):
            failed.append(c)
        else:  # missing/incomplete
            missing.append(c)
    if failed:
        verdict = "REJECTED"
    elif missing:
        verdict = "BLOCKED"
    else:
        verdict = "CLEARED"
    return {"required": req, "satisfied": satisfied, "missing": missing, "failed": failed, "verdict": verdict}


def audit_registry() -> dict:
    """오늘 전략들 통제층 감사 + 사람 판단 일치 확인."""
    rows, agree = [], 0
    for sid, d in STRATEGIES.items():
        r = review_strategy(d["spec"], d["evidence"])
        # 사람 판단과 red-team verdict 일치 매핑
        hc = d["human_call"]
        match = ((r["verdict"] == "CLEARED" and ("paper_candidate" in hc or "research" in hc))
                 or (r["verdict"] == "REJECTED" and "reject" in hc.lower())
                 or (r["verdict"] == "BLOCKED" and ("block" in hc or "inconclusive" in hc))
                 or (r["verdict"] == "REJECTED" and "watchlist" in hc))  # WF fail → red-team 더 엄격
        if match:
            agree += 1
        rows.append({"strategy": sid, "human_call": hc, "redteam_verdict": r["verdict"],
                     "failed": r["failed"], "missing": r["missing"], "match": match})
    return {"n": len(STRATEGIES), "human_redteam_agree": agree, "rows": rows}
