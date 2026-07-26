"""Continuous Research Queue (P173) — 항상 늘어나는 연구 백로그. **큐만, 실행 없음.**

여러 소스에서 연구 후보를 결정적으로 모아 하나의 재우선순위화 백로그로 유지한다. 새 정보가 도착하면
(signals 로 주입) 큐가 스스로 재정렬된다.

소스(모두 **기존 모듈 재사용**): creative_hypothesis(P171, 신규 아이디어)·opportunity_discovery(P92)·
conflict_detection(P135, 모순)·semantic_recall(P133, 저확신 결론)·research_ingestion(미완/실패 결과).
우선순위화는 research_prioritizer(P76) 재사용.

원칙(문서 §Constitution, §P173): 통합·조율만 · 결정적 · 큐만(실행 없음) · 자문 전용 ·
거래·집행 없음 · 사람이 모든 결정.
"""
from __future__ import annotations


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _hid(statement):
    return _safe(lambda: __import__("jarvis.research_workflow.models",
                                    fromlist=["hypothesis_id"]).hypothesis_id(statement),
                 "HYP:" + str(abs(hash(statement)) % (10 ** 10)))


def _cand(statement, source, reason, *, edge="MEDIUM", confidence="MEDIUM"):
    return {"hypothesis_id": _hid(statement), "statement": statement, "source": source,
            "added_reason": reason, "expected_edge": edge, "confidence": confidence}


def _from_creative(topic, limit):
    def _go():
        from jarvis.research_workflow.creative_hypothesis import discover_hypotheses
        hs = discover_hypotheses(topic, limit=limit).get("hypotheses", [])
        return [_cand(h["statement"], "creative_hypothesis", "multi-source discovery",
                      edge=h.get("expected_edge", "MEDIUM"), confidence=h.get("confidence", "MEDIUM"))
                for h in hs]
    return _safe(_go, []) or []


def _from_opportunities(signals):
    def _go():
        from jarvis.research_workflow.opportunity_discovery import discover
        opps = discover(signals).get("opportunities", [])
        out = []
        for o in opps:
            stmt = str(o.get("statement") or o.get("title") or o.get("description")
                       or o.get("opportunity") or "")
            if stmt:
                out.append(_cand(stmt, "opportunity_discovery",
                                 str(o.get("type") or "opportunity")))
        return out
    return _safe(_go, []) or []


def _from_conflicts():
    def _go():
        from jarvis.research_workflow.conflict_detection import detect_conflicts
        conf = detect_conflicts().get("conflicts", [])
        out = []
        for c in conf[:8]:
            topic = str(c.get("topic") or c.get("subject") or "")
            stmt = f"Resolve conflicting evidence on {topic}" if topic else \
                "Resolve detected research contradiction"
            out.append(_cand(stmt, "conflict_detection", "contradiction detected",
                             edge="MEDIUM", confidence="LOW"))
        return out
    return _safe(_go, []) or []


def _from_incomplete_results():
    """수집된 미완/실패 실험 → 재검토 후보(기존 ring_/rmi_ 원장 재사용, 읽기전용)."""
    def _go():
        from jarvis.research_ingestion.engine import ResearchIngestionEngine
        s = ResearchIngestionEngine().summary()
        by = s.by_outcome or {}
        out = []
        if by.get("INCOMPLETE"):
            out.append(_cand("Complete validation for INCOMPLETE experiments (missing cost/vol/stability)",
                             "research_ingestion", f"{by['INCOMPLETE']} incomplete results",
                             edge="MEDIUM", confidence="LOW"))
        if by.get("FAILURE"):
            out.append(_cand("Revisit failed hypotheses for salvageable, regime-conditional edge",
                             "research_ingestion", f"{by['FAILURE']} historical failures",
                             edge="LOW", confidence="LOW"))
        return out
    return _safe(_go, []) or []


def build_continuous_queue(*, topic: str = "", signals=None, limit: int = 30) -> dict:
    """다중 소스 → 재우선순위화 연구 백로그. 결정적·읽기전용. 큐만(실행 없음).

    signals 주입 시 opportunity 소스가 반영 → 큐 재정렬(새 정보 도착 시 자기 재우선순위화).
    """
    candidates = []
    candidates += _from_creative(topic, limit=min(12, limit))
    candidates += _from_opportunities(signals)
    candidates += _from_conflicts()
    candidates += _from_incomplete_results()

    # 중복 제거(hypothesis_id)
    seen, uniq = set(), []
    for c in candidates:
        if c["hypothesis_id"] in seen:
            continue
        seen.add(c["hypothesis_id"])
        uniq.append(c)

    # 재우선순위화 — research_prioritizer 재사용
    def _prio():
        from jarvis.research_workflow.research_prioritizer import ResearchPrioritizer
        return ResearchPrioritizer().prioritize(uniq).to_dict()
    ranked = _safe(_prio, {"items": [], "recommended": {}})
    items = ranked.get("items", [])
    # 소스 라벨 다시 붙이기(prioritizer 는 source 를 보존)
    by_source: dict = {}
    for c in uniq:
        by_source[c["source"]] = by_source.get(c["source"], 0) + 1

    backlog = items[:limit]
    return {"topic": topic, "queue_size": len(backlog), "total_candidates": len(uniq),
            "by_source": dict(sorted(by_source.items())),
            "sources": ["creative_hypothesis", "opportunity_discovery", "conflict_detection",
                        "research_ingestion"],
            "backlog": backlog, "recommended_next": ranked.get("recommended", {}),
            "reprioritized_on_signals": signals is not None,
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Continuous Research Queue(읽기전용) — 다중 소스 백로그, 새 정보 시 자기 재우선순위화. "
                     "큐만(실행 없음), 새 원장 없음. 사람이 모든 결정.")}
