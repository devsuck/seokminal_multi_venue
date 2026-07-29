"""Research Accountability Loop (P211) — 연구를 **측정 가능하게**. 회계 루프를 닫는다. **평가만, 실행 없음.**

Forward evaluation · prediction registry 통합 · research batting average · calibration · edge score ·
confidence decay · prediction lifecycle(RIGHT/WRONG/INVALIDATED/INCONCLUSIVE).

**철칙**: 평가는 **항상 예측 시점에 박제된 frozen success_rule 로만**. 사후 평가 없음. 골대 이동 없음.
**절대 pending 을 숨기지 않는다** — Pending · Evaluated · Invalidated 를 **항상 분리 표시**.

**재사용**: prediction_registry(P201, frozen-rule evaluate)·research_validation_score(P205)·
prediction_coverage_audit(P204.5). 새 원장 없음(rmi_ 재사용). 실행/배분/포트폴리오 없음.
"""
from __future__ import annotations

# horizon 문자열 → 일수(confidence decay 계산). 미지 → 90일 기본.
_HORIZON_DAYS = {"1M": 30, "1MO": 30, "3M": 90, "6M": 180, "9M": 270, "1Y": 365, "12M": 365}
_DEFAULT_HORIZON_DAYS = 90
_STATED_PROB = {"HIGH": 0.75, "MEDIUM": 0.5, "LOW": 0.3}
# 평가 결과 3버킷(항상 분리) — INVALIDATED 는 실패 아님(사전 리스크관리 성공)
_EVALUATED_OUTCOMES = ("RIGHT", "WRONG")
_INVALIDATED = "INVALIDATED"
_INCONCLUSIVE = "INCONCLUSIVE"


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _parse_date(s: str):
    """ISO(YYYY-MM-DD 또는 …THH:MM:SSZ) → datetime. 앞 10자(날짜)만 사용(관대·결정적)."""
    from datetime import datetime, timezone
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _days_between(a: str, b: str) -> int | None:
    da, db = _parse_date(a), _parse_date(b)
    if da is None or db is None:
        return None
    return (db - da).days


def _horizon_days(horizon: str) -> int:
    h = str(horizon or "").strip().upper().replace(" ", "")
    return _HORIZON_DAYS.get(h, _DEFAULT_HORIZON_DAYS)


# ── Forward evaluation — 반드시 frozen rule 로만(사후 평가·골대이동 없음) ──
def evaluate_forward(prediction_id: str, forward_result: dict, *, now: str = "", commit: bool = False) -> dict:
    """예측 1건을 forward 결과로 평가 — **박제된 frozen success_rule 로만**(prediction_registry.evaluate 위임).

    forward_result 는 규칙을 바꿀 수 없다(baseline_outperformance/thesis_held/invalidation_triggered/
    insufficient_data 같은 관측만 제공). 규칙은 예측 스냅샷의 것만 사용 → 사후 편향 차단.
    """
    return _safe(lambda: __import__("jarvis.research_workflow.prediction_registry",
                                    fromlist=["evaluate"]).evaluate(prediction_id, forward_result,
                                                                    now=now, commit=commit),
                 {"error": "evaluate failed", "prediction_id": prediction_id, "is_decision": False})


def evaluate_forward_batch(forward_results: dict, *, now: str = "", commit: bool = False) -> dict:
    """여러 예측을 forward 결과로 일괄 평가. forward_results = {prediction_id: forward_result}. frozen rule 만."""
    outcomes: dict = {}
    evaluated = []
    for pid, fr in (forward_results or {}).items():
        r = evaluate_forward(pid, fr, now=now, commit=commit)
        oc = r.get("outcome")
        if oc:
            outcomes[oc] = outcomes.get(oc, 0) + 1
        evaluated.append({"prediction_id": pid, "outcome": oc, "used_frozen_rule": r.get("used_frozen_rule")})
    return {"evaluated": len(evaluated), "by_outcome": dict(sorted(outcomes.items())),
            "results": evaluated, "used_frozen_rule": True, "no_posthoc": True,
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": "Forward batch evaluation — frozen rule 만 사용. 사후 평가·골대이동 없음."}


# ── Confidence decay — 평가 안 된 채 horizon 지나면 신뢰 감쇠(결정적) ──
def confidence_decay(prediction: dict, *, now: str = "") -> dict:
    """예측이 horizon 을 넘겨 미평가로 남으면 confidence 감쇠(결정적). 오래된 미확인 베팅은 덜 신뢰."""
    captured = prediction.get("captured_at", "")
    horizon_days = _horizon_days(prediction.get("expected_horizon"))
    age = _days_between(captured, now)
    base = _STATED_PROB.get(str(prediction.get("confidence", "MEDIUM")).upper(), 0.5)
    if age is None:
        return {"factor": 1.0, "effective_confidence": base, "status": "UNKNOWN_AGE",
                "age_days": None, "horizon_days": horizon_days}
    if age <= horizon_days:
        return {"factor": 1.0, "effective_confidence": round(base, 4), "status": "WITHIN_HORIZON",
                "age_days": age, "horizon_days": horizon_days}
    overdue = age - horizon_days
    factor = max(0.0, 1.0 - overdue / max(1, horizon_days))   # horizon 만큼 더 지나면 0
    status = "EXPIRED" if factor <= 0.0 else "DECAYING"
    return {"factor": round(factor, 4), "effective_confidence": round(base * factor, 4),
            "status": status, "age_days": age, "horizon_days": horizon_days, "overdue_days": overdue}


def _lifecycle_buckets(now: str) -> dict:
    """예측을 Pending/Evaluated/Invalidated/Inconclusive 로 분리(항상, pending 숨김 없음)."""
    from jarvis.research_workflow import prediction_registry as pr
    preds = _safe(pr.list_predictions, []) or []
    _, latest_outcome = _safe(pr._latest_outcomes, ({}, {}))
    pending, evaluated, invalidated, inconclusive = [], [], [], []
    for p in preds:
        pid = p.get("prediction_id")
        oc = latest_outcome.get(pid)
        row = {"prediction_id": pid, "confidence": p.get("confidence"), "source": p.get("source"),
               "strategy_family": p.get("strategy_family"),
               "decay": confidence_decay(p, now=now)}
        if oc in _EVALUATED_OUTCOMES:
            evaluated.append({**row, "outcome": oc})
        elif oc == _INVALIDATED:
            invalidated.append({**row, "outcome": oc})
        elif oc == _INCONCLUSIVE:
            inconclusive.append({**row, "outcome": oc})
        else:
            pending.append(row)
    return {"pending": pending, "evaluated": evaluated,
            "invalidated": invalidated, "inconclusive": inconclusive}


def accountability_report(*, now: str = "") -> dict:
    """연구 회계 루프 리포트 — batting average·calibration·edge score·confidence decay + 생명주기 분리 표시.

    **항상 Pending/Evaluated/Invalidated/Inconclusive 분리**(pending 숨김 없음). 평가는 frozen rule 만. 읽기전용.
    """
    buckets = _lifecycle_buckets(now)
    n_pending = len(buckets["pending"])
    n_eval = len(buckets["evaluated"])
    n_inval = len(buckets["invalidated"])
    n_incon = len(buckets["inconclusive"])

    right = sum(1 for r in buckets["evaluated"] if r["outcome"] == "RIGHT")
    wrong = n_eval - right
    # Research batting average — RIGHT/(RIGHT+WRONG). INVALIDATED/INCONCLUSIVE 제외(정직).
    batting_average = round(right / n_eval, 4) if n_eval else None

    # Edge score = P205 research_validation_score(PROVISIONAL<20). 재사용.
    score = _safe(lambda: __import__("jarvis.research_workflow.research_validation_score",
                                     fromlist=["build_validation_score"]).build_validation_score(),
                  {"status": "PROVISIONAL", "score": None})

    # confidence decay 요약(pending 중 감쇠/만료)
    decay_status: dict = {}
    for r in buckets["pending"]:
        s = r["decay"]["status"]
        decay_status[s] = decay_status.get(s, 0) + 1

    return {
        # ★ 절대 pending 숨기지 않음 — 4버킷 항상 분리
        "lifecycle": {"pending": n_pending, "evaluated": n_eval,
                      "invalidated": n_inval, "inconclusive": n_incon},
        "batting_average": {"value": batting_average, "right": right, "wrong": wrong,
                            "note": "RIGHT/(RIGHT+WRONG). INVALIDATED/INCONCLUSIVE 제외."},
        "edge_score": {"status": score.get("status"), "score": score.get("score"),
                       "graded_scorable": score.get("graded_scorable"),
                       "needed": score.get("needed"),
                       "components": score.get("components")},
        "calibration": score.get("calibration_detail") if score.get("status") == "SCORED" else None,
        "confidence_decay": {"pending_by_status": dict(sorted(decay_status.items())),
                             "note": "미평가로 horizon 초과 시 신뢰 감쇠(오래된 미확인 베팅)."},
        "buckets": buckets,
        "evaluation_rule": "frozen_success_rule_only",
        "no_posthoc_evaluation": True, "no_goalpost_movement": True,
        "hides_pending": False,
        "requires_human_review": True, "is_advisory": True, "is_decision": False,
        "note": ("Research Accountability(읽기전용) — 회계 루프. Pending/Evaluated/Invalidated/Inconclusive "
                 "항상 분리(pending 숨김 없음). 평가는 frozen rule 만(사후·골대이동 없음). "
                 "batting average·calibration·edge score·confidence decay. 실행/배분 없음."),
    }
