"""Research Validation Score (P205) — 연구 예측 품질 점수. **표본 부족 시 숫자 미표시(PROVISIONAL).**

**graded 예측(RIGHT/WRONG) >= 20 전에는 절대 숫자 점수를 내지 않는다.** 그 전엔 status=PROVISIONAL.
데이터 5개로 "62.4점"을 찍는 게 가장 위험한 자기기만이므로 하드 게이트.

구성(표본 충분 시): Accuracy · Calibration · Baseline-relative performance · Sample confidence.
INVALIDATED(사전 리스크관리 성공)·INCONCLUSIVE(데이터 부족)는 RIGHT/WRONG 채점에서 제외.

**재사용**: prediction_registry(P201, graded_predictions). 새 원장 없음.
원칙(§Constitution): 통합·측정만 · 결정적 · 자문 전용 · 투자 추천 아님 · 거래·집행 없음 · 사람이 결정.
"""
from __future__ import annotations

MIN_GRADED = 20
# confidence → 표명 확률(calibration 기준)
_STATED_PROB = {"HIGH": 0.75, "MEDIUM": 0.5, "LOW": 0.3}
_BASELINE_RATE = 0.5   # null(랜덤) 베이스라인 — 초과분이 edge
_W = {"accuracy": 0.4, "calibration": 0.3, "baseline_relative": 0.2, "sample_confidence": 0.1}


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _calibration(scorable_rows) -> dict:
    """confidence 버킷별 표명확률 vs 실제 적중률 → calibration(1 - 평균 오차)."""
    buckets: dict = {}
    for r in scorable_rows:
        c = str(r.get("confidence", "MEDIUM")).upper()
        buckets.setdefault(c, {"n": 0, "right": 0})
        buckets[c]["n"] += 1
        if r.get("outcome") == "RIGHT":
            buckets[c]["right"] += 1
    per_bucket = {}
    errs = []
    for c, b in buckets.items():
        hit = b["right"] / b["n"] if b["n"] else 0.0
        stated = _STATED_PROB.get(c, 0.5)
        per_bucket[c] = {"n": b["n"], "hit_rate": round(hit, 4), "stated_prob": stated,
                         "gap": round(abs(stated - hit), 4)}
        errs.append(abs(stated - hit))
    calibration = round(1.0 - (sum(errs) / len(errs)), 4) if errs else None
    return {"score": calibration, "per_confidence": per_bucket}


def build_validation_score() -> dict:
    """Research Validation Score(자문). graded<20 이면 PROVISIONAL(숫자 없음). 결정적·읽기전용."""
    graded = _safe(lambda: __import__("jarvis.research_workflow.prediction_registry",
                                      fromlist=["graded_predictions"]).graded_predictions(), []) or []
    scorable = [r for r in graded if r.get("outcome") in ("RIGHT", "WRONG")]
    n = len(scorable)
    outcome_counts: dict = {}
    for r in graded:
        outcome_counts[r.get("outcome")] = outcome_counts.get(r.get("outcome"), 0) + 1

    # ★ 하드 게이트 — 표본 부족 시 숫자 미표시
    if n < MIN_GRADED:
        return {"status": "PROVISIONAL", "score": None,
                "graded_scorable": n, "needed": MIN_GRADED, "shortfall": MIN_GRADED - n,
                "graded_total": len(graded), "outcome_counts": dict(sorted(outcome_counts.items())),
                "requires_human_review": True, "is_advisory": True, "is_decision": False,
                "note": (f"PROVISIONAL — scorable(RIGHT/WRONG)={n} < {MIN_GRADED}. 숫자 점수 미표시. "
                         "표본 충분해질 때까지 정직하게 보류(자기기만 차단). 투자 추천 아님.")}

    right = sum(1 for r in scorable if r["outcome"] == "RIGHT")
    accuracy = round(right / n, 4)
    calib = _calibration(scorable)
    baseline_relative = round(accuracy - _BASELINE_RATE, 4)   # 랜덤 대비 edge
    sample_confidence = round(min(1.0, n / 50.0), 4)

    components = {"accuracy": accuracy, "calibration": calib["score"],
                  "baseline_relative": baseline_relative, "sample_confidence": sample_confidence}
    composite = round(_W["accuracy"] * accuracy
                      + _W["calibration"] * (calib["score"] or 0.0)
                      + _W["baseline_relative"] * max(0.0, baseline_relative + 0.5)
                      + _W["sample_confidence"] * sample_confidence, 4)

    return {"status": "SCORED", "score": composite, "components": components,
            "calibration_detail": calib["per_confidence"],
            "graded_scorable": n, "graded_total": len(graded),
            "outcome_counts": dict(sorted(outcome_counts.items())),
            "is_investment_recommendation": False,
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Research Validation Score — accuracy·calibration·baseline-relative·sample. "
                     "INVALIDATED/INCONCLUSIVE 제외. 연구 품질 지표, 투자 추천 아님. 사람이 해석.")}
