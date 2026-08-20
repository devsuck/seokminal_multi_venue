"""Historical Candidate Bridge (P204→P29) — recall_first 결과를 research_strategy_generation 원장에 로깅.

recall_first(hypothesis_discovery, "과거 실패 유사 시 왜 다른지" 근거)를 유일한 소스로 삼아
statement 로 정리해 research_strategy_generation 의 기존 원장(rsg_)에 append-only 로 기록한다.
**새 지능/저장소 없음 — 기존 원장에만 씀.** 조율만, 선택·승인·배포·거래 없음. 결정적.
"""
from __future__ import annotations

from datetime import datetime, timezone


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _statement(h: dict) -> str:
    return str(h.get("question") or h.get("statement") or "").strip()


def _source_refs(h: dict) -> list:
    refs = [h.get("hypothesis_id")] if h.get("hypothesis_id") else []
    refs += [e for e in (h.get("supporting_evidence") or []) if e]
    return refs


def propose(topic: str, limit: int = 5) -> dict:
    """recall_first 후보 → research_strategy_generation 세션/후보 원장에 로깅(append-only). 결정적.

    hypothesis_discovery(P183)를 직접 호출(research_discovery 파사드를 되돌아 호출하지 않음 —
    파사드는 "밖에서는 이것만 호출" 계약이라 내부 모듈끼리는 서로 직접 호출).
    generate()(mode=historical) 에서 바로 합류 가능하도록 다른 3 모드와 동일한 shape 반환
    (stage/mode/topic/count/hypotheses/...).
    """
    gen = _safe(lambda: __import__(
        "jarvis.research_workflow.hypothesis_discovery", fromlist=["discover_research"]
    ).discover_research(topic, limit=limit), {}) or {}
    hyps = gen.get("research_hypotheses", [])

    from jarvis.research_strategy_generation.engine import ResearchStrategyGenerationEngine

    engine = ResearchStrategyGenerationEngine()
    now = _now()
    sess = engine.create_session(f"historical:{topic}", now, commit=True).session_id
    engine.start_generating(sess, now=now, commit=True)

    items = []
    for h in hyps:
        statement = _statement(h)
        if not statement:
            continue
        # ponytail: 카테고리 분류기 없이 ALPHA 고정 — 세분화 필요해지면 category 매핑 추가
        cand = engine.generate_candidate(sess, "ALPHA", statement, source_refs=_source_refs(h),
                                         now=now, commit=True)
        items.append({**h, "candidate_id": cand.candidate_id, "session_id": sess})

    return {"stage": "generate", "mode": "historical", "topic": gen.get("topic") or topic,
            "count": len(items), "hypotheses": items, "session_id": sess,
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Historical Candidate Bridge(읽기전용 조율) — recall_first 후보를 "
                     "research_strategy_generation 원장(rsg_)에 로깅. 새 저장소 없음. "
                     "GENERATED ≠ SELECTED. 제안만, 사람이 결정.")}
