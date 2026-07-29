"""Prediction Coverage Audit (P204.5) — "우리가 무엇을 기록하고 있나"를 측정한다. **지표만, 대시보드 없음.**

점수(P205)보다 먼저 봐야 하는 것: capture 커버리지. STRONG 만 기록하면 "70% 적중" 착각이 생기므로
**무엇이 빠졌는지**를 먼저 본다.

측정: capture rate(완결성) · missing captures(필드 결측) · confidence 분포 · source 분포 ·
missing invalidation · missing horizon · duplicate predictions · pending/evaluated 비율.

**재사용**: prediction_registry(P201). 새 원장 없음. 지표만(대시보드/점수 없음).
원칙(§Constitution): 통합·측정만 · 결정적 · 자문 전용 · 거래·집행 없음.
"""
from __future__ import annotations


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _pct(n, d):
    return round(100.0 * n / d, 1) if d else None


def build_coverage_audit() -> dict:
    """예측 capture 커버리지 감사(결정적·읽기전용). 지표만 — 대시보드/점수 없음."""
    from jarvis.research_workflow import prediction_registry as pr

    preds = _safe(pr.list_predictions, []) or []
    latest_state, latest_outcome = _safe(pr._latest_outcomes, ({}, {}))
    total = len(preds)

    by_conf: dict = {}
    by_source: dict = {}
    missing_invalidation = 0
    missing_horizon = 0
    missing_evidence = 0
    complete = 0
    seen_theses: dict = {}
    duplicates = 0
    for p in preds:
        by_conf[p.get("confidence", "?")] = by_conf.get(p.get("confidence", "?"), 0) + 1
        by_source[p.get("source", "?")] = by_source.get(p.get("source", "?"), 0) + 1
        has_inval = bool(str(p.get("invalidation_condition", "")).strip())
        has_hor = bool(str(p.get("expected_horizon", "")).strip())
        has_ev = bool(p.get("evidence_used"))
        if not has_inval:
            missing_invalidation += 1
        if not has_hor:
            missing_horizon += 1
        if not has_ev:
            missing_evidence += 1
        if has_inval and has_hor and has_ev:
            complete += 1
        key = (str(p.get("thesis", "")).strip().lower(), p.get("strategy_id"))
        seen_theses[key] = seen_theses.get(key, 0) + 1
    duplicates = sum(c - 1 for c in seen_theses.values() if c > 1)

    evaluated = sum(1 for pid in latest_outcome)
    pending = total - evaluated

    # 4개 소스 모두 capture 중인가(committee/agent/human_hypothesis/automatic_discovery)
    expected_sources = ("committee", "agent", "human_hypothesis", "automatic_discovery")
    source_coverage = {s: by_source.get(s, 0) for s in expected_sources}
    sources_missing = [s for s in expected_sources if by_source.get(s, 0) == 0]

    return {"total_predictions": total,
            # capture rate = 필드 완결성(invalidation+horizon+evidence 모두 있는 비율).
            # 참고: 진짜 capture rate(연구산출 대비)는 hook 전면 배선 후 산출(현재 denominator 없음).
            "capture_completeness_pct": _pct(complete, total),
            "capture_rate_note": "완결성 기준. 연구산출 대비 진짜 capture rate 는 hook 배선 후.",
            "missing_captures": {"invalidation_condition": missing_invalidation,
                                 "expected_horizon": missing_horizon,
                                 "evidence_used": missing_evidence},
            "missing_invalidation_pct": _pct(missing_invalidation, total),
            "missing_horizon_pct": _pct(missing_horizon, total),
            "confidence_distribution": dict(sorted(by_conf.items())),
            "source_distribution": dict(sorted(by_source.items())),
            "source_coverage": source_coverage, "sources_missing": sources_missing,
            "duplicate_predictions": duplicates,
            "pending": pending, "evaluated": evaluated,
            "pending_evaluated_ratio": _pct(pending, total),
            # P205 게이트: 완결성 90% 넘고 graded>=20 이면 Edge Score 공개 권고
            "ready_for_score": bool(total and (complete / total) >= 0.9),
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Prediction Coverage Audit(읽기전용) — 무엇을 기록 중인가. 지표만(대시보드/점수 없음). "
                     "완결성 90%+ & graded>=20 이면 P205 Edge Score 공개. 새 원장 없음.")}
