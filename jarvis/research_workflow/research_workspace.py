"""Human Research Workspace (P146) — 사람 연구자 컨트롤 센터. **분석/기록만, 투자 승인·거래 없음.**

기능: Research Inbox·Review Queue·Agent Outputs·Comments·Follow-up Tasks·Research History.
액션: review·comment·request_revision·archive(모두 비구속 자문 기록 — ras_notes). **투자 승인·거래 집행 없음.**
**재사용**: ops_events(P107)·timeline(P78)·agent_capability(P121)·record_advisory(ras_).

원칙(문서 §Constitution, §P146): 통합·조율만. 결정적. 거래·집행·투자승인 없음. 사람 결정.
"""
from __future__ import annotations

# 허용 액션(비구속) — 투자 승인/거래는 없음
WORKSPACE_ACTIONS = ("review", "comment", "request_revision", "archive")


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def build_workspace(*, topic: str = "") -> dict:
    """사람 연구 워크스페이스 표면(읽기전용) — inbox·review queue·agent outputs·history. 결정적."""
    # Review Queue + Research Inbox — ops_events(운영 이벤트 + 사람검토 큐)
    ops = _safe(lambda: __import__("jarvis.research_workflow.ops_events", fromlist=["ops_events"])
                .ops_events(), {"events": [], "review_queue": []})
    # Agent Outputs — agent capability map(에이전트 조직)
    agents = _safe(lambda: __import__("jarvis.research_workflow.agent_capability",
                                      fromlist=["capability_map"]).capability_map(), {"agents": []})
    # Research History — timeline(기존 원장 재구성)
    history = _safe(lambda: __import__("jarvis.research_workflow.timeline", fromlist=["build_timeline"])
                    .build_timeline(topic, limit=30), {"entries": []})

    return {"research_inbox": ops.get("events", [])[:20],
            "review_queue": ops.get("review_queue", []),
            "agent_outputs": [{"agent": a["agent"], "role": a["role"], "output": a["output"]}
                              for a in agents.get("agents", [])],
            "follow_up_tasks": [{"task": e.get("label"), "source": e.get("source"),
                                 "requires_human_review": True}
                                for e in ops.get("review_queue", [])[:10]],
            "research_history": history.get("entries", []),
            "available_actions": list(WORKSPACE_ACTIONS),
            "forbidden_actions": ["approve_investment", "execute_trade", "allocate_capital"],
            "is_advisory": True, "is_decision": False,
            "note": ("연구 워크스페이스(읽기전용) — inbox·review queue·agent outputs·history. "
                     "액션은 비구속 자문(review/comment/request_revision/archive). 투자 승인·거래 없음.")}


def act(action: str, target: str, *, comment: str = "", assistant=None, now: str = "",
        commit: bool = False) -> dict:
    """워크스페이스 액션(비구속) — comment/request_revision/archive 는 ras_notes 자문 기록. 투자 승인·거래 불가.

    review 는 표시만. 실제 기록은 기존 record_advisory(ras_, is_binding=False) 경유. 새 원장 없음.
    """
    a = (action or "").lower()
    if a not in WORKSPACE_ACTIONS:
        return {"error": f"허용되지 않은 액션 — {WORKSPACE_ACTIONS}", "is_decision": False,
                "is_advisory": True}
    recorded = None
    if a in ("comment", "request_revision", "archive"):
        try:
            if assistant is None:
                from jarvis.research_assistant.engine import ResearchAssistantEngine
                assistant = ResearchAssistantEngine()
            note = assistant.record_advisory(area=f"workspace:{a}:{target}",
                                             rationale=comment or a, now=now, commit=commit)
            recorded = note.note_id if hasattr(note, "note_id") else None
        except Exception as e:  # noqa: BLE001
            recorded = f"error:{e}"
    return {"action": a, "target": target, "comment": comment, "recorded_note": recorded,
            "committed": commit, "is_binding": False,
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("워크스페이스 액션(비구속 자문) — ras_notes 기록. 투자 승인·거래 집행 없음, 새 원장 없음.")}
