"""Semantic Research Recall (P133) — 질문을 받으면 관련 지식을 자동 회수한다. **읽기 전용.**

질문 → Research Context Package: relevant experiments·similar failures·past conclusions·contradicting
evidence. **재사용**: research_assistant.recall·mistake_check·perspectives·failure_intelligence +
research_memory_intelligence.retrieve_context(rmi_). 새 벡터 DB/저장소 없음 — 기존 메모리 회수.

원칙(문서 §Constitution, §P133): 통합·조율만. 결정적. 거래·집행 없음.
"""
from __future__ import annotations


def _topic(question: str) -> str:
    from jarvis.research_assistant.models import extract_topic
    return extract_topic(question) or (question or "").strip()


def recall_context(question: str, *, assistant=None, top_k: int = 5) -> dict:
    """질문 → Research Context Package(경험·유사실패·과거결론·모순증거). 결정적·읽기전용."""
    q = (question or "").strip()
    topic = _topic(q)
    if assistant is None:
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        assistant = ResearchAssistantEngine()

    # 1) 관련 경험/실험 — recall(주제별 히트: expt_/rmi_/ring_)
    recall = _safe(lambda: assistant.recall(topic, limit=top_k))
    relevant_experiments, past_conclusions = [], []
    if recall is not None:
        sh = getattr(recall, "source_hits", {}) or {}
        for src, hits in sh.items():
            for h in hits[:top_k]:
                item = {"source": src, "ref": h.get("ref"), "text": h.get("text", "")[:160]}
                (relevant_experiments if src.startswith(("expt", "ring")) else past_conclusions).append(item)

    # 2) 유사 실패 — mistake_check + failure_intelligence
    mistake = _safe(lambda: assistant.mistake_check(topic), {}) or {}
    fi = _safe(lambda: assistant.failure_intelligence(), None)
    similar_failures = []
    if fi is not None:
        recs = getattr(fi, "records", []) or []
        for r in recs:
            if topic.lower() in str(r.get("text", "")).lower() or topic.lower() in str(r.get("ref", "")).lower():
                similar_failures.append({"category": r.get("category"), "ref": r.get("ref"),
                                         "text": str(r.get("text", ""))[:160]})
        similar_failures = similar_failures[:top_k] or [{"category": c, "count": n}
                            for c, n in list((mistake.get("by_category") or {}).items())[:top_k]]

    # 3) 모순 증거 — perspectives(conflicting lenses)
    persp = _safe(lambda: assistant.perspectives(topic), {}) or {}
    contradicting = []
    if persp.get("conflicting"):
        for lens in persp.get("lenses", []):
            contradicting.append({"lens": lens.get("lens"), "stance": lens.get("stance"),
                                  "rationale": lens.get("rationale")})

    # 4) rmi_ 메모리 회수(scored) — retrieve_context(비구속, 커밋 없음)
    rmi_refs = []
    ret = _safe(lambda: _retrieve(topic, top_k))
    if ret is not None:
        rmi_refs = ret.get("memory_refs", [])[:top_k]

    return {"question": q, "topic": topic,
            "relevant_experiments": relevant_experiments[:top_k],
            "similar_failures": similar_failures,
            "past_conclusions": past_conclusions[:top_k],
            "contradicting_evidence": contradicting,
            "memory_refs": rmi_refs,
            "prior_research_count": int(getattr(recall, "total_hits", 0) or 0),
            "tried_before": bool(getattr(recall, "tried_before", False)),
            "made_this_mistake": mistake.get("made_this_mistake", False),
            "is_context_package": True, "requires_human_review": True,
            "is_advisory": True, "is_decision": False,
            "note": ("Research Context Package(읽기전용) — 경험·유사실패·과거결론·모순증거. "
                     "recall/mistake_check/perspectives/failure_intelligence/retrieve_context 재사용. "
                     "새 벡터 DB 없음.")}


def _retrieve(topic, top_k):
    from jarvis.research_memory_intelligence.engine import ResearchMemoryIntelligenceEngine
    rec = ResearchMemoryIntelligenceEngine().retrieve_context(topic, top_k=top_k, commit=False)
    return rec.to_dict() if hasattr(rec, "to_dict") else dict(rec)


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default
