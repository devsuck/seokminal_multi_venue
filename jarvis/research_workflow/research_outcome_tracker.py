"""Research Performance Tracking (P147) — 연구의 유용성을 측정한다. **읽기 전용, 결정적.**

추적: Hypothesis·Expected outcome·Actual outcome·Time period·Difference·Lesson. 예: "AI 반도체 수요 증가"
연구 → 이후 실제 시장/기업 결과. 출력: Research Accuracy Report. **재사용**: forward_testing/validation_gap·
paper_validation·recall. 새 저장소 없음(교훈은 기존 rmi_ 경로).

원칙(문서 §Constitution, §P147): 통합·조율만. 결정적. 거래·집행 없음. 사람 결정.
"""
from __future__ import annotations


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class ResearchOutcomeTracker:
    """연구 성과 추적 — 기대 vs 실제 → Research Accuracy Report. RESEARCH_ONLY."""

    def track(self, hypothesis: str, *, expected: dict | None = None, actual: dict | None = None,
              period: str = "", assistant=None) -> dict:
        """가설 + 기대 vs 실제 → 정확도 리포트(차이·교훈). 결정적·읽기전용."""
        h = (hypothesis or "").strip()
        exp, act = expected or {}, actual or {}

        # 지표별 차이(결정적)
        diffs = {}
        hits = 0
        total = 0
        for k in set(exp) | set(act):
            e, a = _num(exp.get(k)), _num(act.get(k))
            if e is None or a is None:
                diffs[k] = {"expected": exp.get(k), "actual": act.get(k), "difference": None}
                continue
            total += 1
            d = round(a - e, 4)
            # 방향 일치 = 적중
            if (e >= 0) == (a >= 0) and abs(d) <= abs(e) * 0.5 + 1e-9:
                hits += 1
            diffs[k] = {"expected": e, "actual": a, "difference": d,
                        "direction_match": (e >= 0) == (a >= 0)}
        accuracy = round(hits / total, 3) if total else None
        label = ("ACCURATE" if accuracy is not None and accuracy >= 0.6 else
                 "PARTIAL" if accuracy is not None and accuracy >= 0.3 else
                 "INACCURATE" if accuracy is not None else "PENDING")

        # 과거 유사 — recall
        recall = _safe(lambda: _recall(assistant, h))

        lesson = self._lesson(h, label, diffs)
        return {"hypothesis": h, "expected_outcome": exp, "actual_outcome": act,
                "time_period": period, "differences": diffs,
                "accuracy": accuracy, "accuracy_label": label,
                "lesson": lesson, "historical_context": recall,
                "report_type": "Research Accuracy Report",
                "requires_human_review": True, "is_advisory": True, "is_decision": False,
                "note": ("Research Accuracy Report(읽기전용) — 기대 vs 실제·차이·교훈. "
                         "forward_testing/recall 재사용, 새 저장소 없음.")}

    def _lesson(self, h, label, diffs) -> str:
        if label == "ACCURATE":
            return f"'{h}' 방향 예측 적중 — 근거/방법 재사용 가치."
        if label == "INACCURATE":
            worst = max((k for k in diffs if diffs[k].get("difference") is not None),
                        key=lambda k: abs(diffs[k]["difference"]), default="?")
            return f"'{h}' 예측 빗나감(주요 편차: {worst}) — 가정/기간 재검토."
        return f"'{h}' 부분 적중 — 조건부 타당성 확인 필요."


def _recall(assistant, h):
    if assistant is None:
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        assistant = ResearchAssistantEngine()
    r = assistant.recall(h)
    return {"prior_records": r.total_hits, "tried_before": r.tried_before}


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def track(hypothesis: str, *, expected=None, actual=None, period="", assistant=None) -> dict:
    """모듈 진입점 — ResearchOutcomeTracker.track 래퍼."""
    return ResearchOutcomeTracker().track(hypothesis, expected=expected, actual=actual,
                                          period=period, assistant=assistant)
