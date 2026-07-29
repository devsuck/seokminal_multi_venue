"""Knowledge Consumer — Research OS → Investment OS **읽기전용 다리**. **소비만, Research 변경 없음.**

Investment OS 가 Research OS 지식을 소비하는 **유일한 진입점**. Research OS 산출(paper candidate 전략,
evidence 등급, validation score)을 **읽기만** 한다. Research 원장에 절대 쓰지 않는다.

원칙: 연구는 지식 생산, 투자는 지식 소비. Investment OS ≠ Research OS(완전 분리). 실행 없음.
"""
from __future__ import annotations

# 투자 후보로 소비할 연구 상태(검증 통과 근처)
_CONSUMABLE_STATES = ("paper_active", "paper_candidate", "watchlist")


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _evidence_grade(strategy_id: str) -> str:
    """Research OS 의 research_selection 근거 등급(읽기전용). 없으면 UNKNOWN."""
    sel = _safe(lambda: __import__("jarvis.research_workflow.research_selection",
                                   fromlist=["evaluate_research"]).evaluate_research(
                                       {"strategy_name": strategy_id, "metrics": {}}), {}) or {}
    return str(sel.get("evidence_grade", "UNKNOWN"))


def consume_research(*, limit: int = 50) -> dict:
    """Research OS 에서 투자 후보 지식을 **읽기전용** 소비 — paper candidate 전략 + 근거. Research 무변경.

    반환: {candidates:[{strategy_id, status, family, evidence_grade, edge_score_status}], ...}.
    Investment OS 는 이 지식을 소비만 하고, Research OS 원장/상태를 절대 바꾸지 않는다.
    """
    reg = _safe(lambda: __import__("jarvis.registry", fromlist=["StrategyRegistry"]
                                   ).StrategyRegistry().all_current(), []) or []
    # research accountability edge score(읽기전용) — 현재 PROVISIONAL 가능
    acct = _safe(lambda: __import__("jarvis.research_workflow.research_accountability",
                                    fromlist=["accountability_report"]).accountability_report(), {}) or {}
    edge_status = (acct.get("edge_score") or {}).get("status", "UNKNOWN")

    candidates = []
    for s in reg:
        if str(s.get("status")) not in _CONSUMABLE_STATES:
            continue
        sid = s.get("strategy_id", "")
        candidates.append({"strategy_id": sid, "status": s.get("status"),
                           "family": s.get("family", ""), "asset_class": s.get("asset_class", ""),
                           "evidence_grade": _evidence_grade(sid),
                           "edge_score_status": edge_status})
        if len(candidates) >= limit:
            break
    return {"candidates": candidates, "count": len(candidates),
            "consumed_from": "research_os (read-only)",
            "research_os_modified": False,   # ★ 절대 Research 변경 없음
            "edge_score_status": edge_status,
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Knowledge Consumer(읽기전용) — Research OS paper candidate 지식 소비. "
                     "Research OS 무변경. 연구=생산, 투자=소비. 실행 없음.")}
