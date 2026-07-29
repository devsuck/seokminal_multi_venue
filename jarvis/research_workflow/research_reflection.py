"""Research Self Reflection (P197) — 시스템이 연구 결과를 분석한다. **성찰만, 새 메모리 생성 금지.**

질문: "무엇을 배웠나 · 무엇이 실패했나 · 어떤 가정이 틀렸나 · 무엇을 멈춰야 하나 · 무엇을 계속해야 하나."
**결과는 기존 continuous_learning(P136) 사용. 새 memory 생성 금지.**

**재사용**: continuous_learning(P136, learning_status)·self_reflection(P176)·research_ingestion(요약).
원칙(문서 §Constitution, §P197): 통합·조율만 · 결정적 · 자문 전용 · 새 메모리 없음 · 거래·집행 없음 · 사람 결정.
"""
from __future__ import annotations


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def reflect(*, cycle: dict | None = None) -> dict:
    """연구 결과 성찰 5문(결정적·읽기전용). 학습은 continuous_learning 재사용 — 새 메모리 없음."""
    status = _safe(lambda: __import__("jarvis.research_workflow.continuous_learning",
                                      fromlist=["learning_status"]).learning_status(), {}) or {}
    base = _safe(lambda: __import__("jarvis.research_workflow.self_reflection",
                                    fromlist=["reflect_on_cycle"]).reflect_on_cycle(cycle), {}) or {}
    r = base.get("reflection", {})
    summ = _safe(lambda: __import__("jarvis.research_ingestion.engine",
                                    fromlist=["ResearchIngestionEngine"]
                                    ).ResearchIngestionEngine().summary(), None)
    by_cat = (getattr(summ, "by_failure_category", None) or {}) if summ else {}

    what_learned = r.get("strengthened_evidence", []) or [f"{len(by_cat)}개 실패 카테고리 구조화"]
    what_failed = r.get("assumptions_failed", [])
    wrong_assumptions = r.get("assumptions_failed", [])[:2]
    should_stop = [f"반복 실패 '{k}' 무교정 재검증 중단" for k in sorted(by_cat, key=lambda x: -by_cat[x])[:2]]
    should_continue = r.get("test_next", []) or ["INCOMPLETE 실험의 완전 검증 지속"]

    return {"reflection": {
                "what_did_we_learn": what_learned,
                "what_failed": what_failed,
                "which_assumptions_were_wrong": wrong_assumptions,
                "what_research_should_stop": should_stop,
                "what_should_continue": should_continue},
            "learning_backend": "continuous_learning (기존 rmi_/ring_ 원장 — 새 메모리 없음)",
            "learning_status": {k: status.get(k) for k in
                                ("total_lessons", "channels", "status") if k in status},
            "new_memory_created": False,
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Research Self Reflection(읽기전용) — 5문 성찰. 학습은 continuous_learning 재사용. "
                     "새 메모리 시스템 없음. 사람이 결정.")}
