"""Human Decision Center (P165) — 사람을 위한 중앙 워크스페이스. **투자 승인·집행·배분 없음.**

기능: Committee Packet·Comments·Decision Log·Review History·Follow-up Research·Research Archive.
액션: review·comment·request_followup·archive(모두 비구속 자문 기록 — ras_/rwf_). **금지: approve_trade·
execute·allocate.** **재사용**: investment_committee(P161)·decision_center.record_decision(기존 감사)·
research_workspace(P146). 새 저장소 없음.

원칙(문서 §Constitution, §P165): 통합·조율만. 결정적. 거래·집행·승인 없음. 사람 결정.
"""
from __future__ import annotations

# 허용 액션(비구속) + 금지 액션(엔진이 절대 수행 안 함)
DECISION_ACTIONS = ("review", "comment", "request_followup", "archive")
FORBIDDEN_ACTIONS = ("approve_trade", "execute", "allocate", "approve_investment", "place_order")


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def build_decision_center(question: str = "", *, topic: str = "") -> dict:
    """사람 결정 센터 표면(읽기전용) — committee packet·decision log·review history·follow-up·archive."""
    q = (question or topic or "").strip()

    # Committee Packet — investment_committee(P161)
    packet = {}
    if q:
        packet = _safe(lambda: __import__("jarvis.research_workflow.investment_committee",
                                          fromlist=["build_committee_packet"])
                       .build_committee_packet(q), {})

    # Decision Log / Review History — 기존 감사(rwf_runs HUMAN_DECISION) 재사용
    decision_log = _safe(lambda: _decision_log(), [])
    # Follow-up Research + Review Queue — ops_events(P107)
    ops = _safe(lambda: __import__("jarvis.research_workflow.ops_events", fromlist=["ops_events"])
                .ops_events(), {"review_queue": []})
    # Research Archive — timeline(P78) Archive 스테이지
    archive = _safe(lambda: [e for e in __import__("jarvis.research_workflow.timeline",
                                                   fromlist=["build_timeline"]).build_timeline(q)
                             .get("entries", []) if e.get("stage") == "Archive"], [])

    return {"question": q, "committee_packet": packet,
            "comments": [],  # 세션 코멘트는 act()로 기록(ras_)
            "decision_log": decision_log,
            "review_history": decision_log[-10:],
            "follow_up_research": [{"task": e.get("label"), "source": e.get("source")}
                                   for e in ops.get("review_queue", [])[:10]],
            "research_archive": archive[:15],
            "available_actions": list(DECISION_ACTIONS),
            "forbidden_actions": list(FORBIDDEN_ACTIONS),
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Human Decision Center(읽기전용) — committee packet·decision log·history·follow-up·archive. "
                     "투자 승인·거래·배분 없음. 결정은 사람이 record_decision 으로. 새 저장소 없음.")}


def act(action: str, target: str, *, comment: str = "", reviewer: str = "", run_id: str = "",
        assistant=None, now: str = "", commit: bool = False) -> dict:
    """결정 센터 액션(비구속) — review/comment/request_followup/archive. **approve_trade/execute/allocate 금지.**

    comment/request_followup/archive → ras_notes 자문 기록. review 는 표시만. 사람 결정 기록은 별도
    record_decision(reviewer 필수). 엔진은 승인/집행/배분을 절대 수행하지 않는다.
    """
    a = (action or "").lower()
    if a in FORBIDDEN_ACTIONS:
        return {"error": f"금지된 액션 — 엔진은 {a} 를 수행하지 않는다. 투자 결정은 사람만.",
                "is_decision": False, "is_advisory": True, "requires_human_review": True}
    if a not in DECISION_ACTIONS:
        return {"error": f"허용되지 않은 액션 — {DECISION_ACTIONS}", "is_decision": False, "is_advisory": True}
    recorded = None
    if a in ("comment", "request_followup", "archive"):
        try:
            if assistant is None:
                from jarvis.research_assistant.engine import ResearchAssistantEngine
                assistant = ResearchAssistantEngine()
            note = assistant.record_advisory(area=f"decision-center:{a}:{target}",
                                             rationale=comment or a, now=now, commit=commit)
            recorded = note.note_id if hasattr(note, "note_id") else None
        except Exception as e:  # noqa: BLE001
            recorded = f"error:{e}"
    return {"action": a, "target": target, "comment": comment, "recorded_note": recorded,
            "committed": commit, "is_binding": False,
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": "결정 센터 액션(비구속 자문) — ras_notes 기록. 투자 승인·거래·배분 없음, 새 저장소 없음."}


def _decision_log() -> list:
    """기존 감사(rwf_runs HUMAN_DECISION)에서 결정 이력(읽기전용)."""
    out = []
    try:
        from jarvis.research_workflow import ledger as wl
        for e in wl.read_runs():
            if e.get("stage") == "HUMAN_DECISION":
                out.append({"run_id": e.get("run_id"), "note": e.get("note", ""),
                            "status": e.get("status"), "at": e.get("occurred_at", "")})
    except Exception:  # noqa: BLE001
        pass
    return out[-20:]
