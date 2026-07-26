"""Investment Committee Workflow (P161) — 기관 연구 검토 프로세스. **읽기 전용, 결정은 사람.**

워크플로: Research Report → Evidence Review → Risk Review → Opposing View → Committee Summary → Human Decision.
**재사용**: decision_center.committee_packet(P65/P93)·report_automation(P145)·debate_engine(P162). 출력:
CommitteePacket {research_summary, supporting_evidence, risk_summary, alternative_views, confidence,
limitations, questions_for_human, requires_human_review=True}. **BUY/SELL/EXECUTE/ALLOCATE 절대 출력 안 함.**

원칙(문서 §Constitution, §P161): 통합·조율만. 결정적. 거래·집행 없음. 사람 결정.
"""
from __future__ import annotations


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def build_committee_packet(question: str, *, spec: dict | None = None, metrics: dict | None = None,
                           assistant=None) -> dict:
    """연구 질문 → CommitteePacket(요약·증거·리스크·반대시각·신뢰도·한계·사람질문). 결정적·읽기전용.

    Evidence Review·Risk Review·Opposing View 를 기존 엔진으로 조율. 결정·이유는 사람이 입력(record_decision).
    """
    q = (question or "").strip()

    # 기반 위원회 패킷(논지·증거·반론·리스크·과거·포트폴리오·신뢰도·이력) — decision_center 재사용
    packet = _safe(lambda: __import__("jarvis.research_workflow.decision_center",
                                      fromlist=["committee_packet"])
                   .committee_packet(q, metrics=metrics, assistant=assistant), {})

    # Opposing View — debate_engine(P162) 재사용
    debate = _safe(lambda: __import__("jarvis.research_workflow.debate_engine", fromlist=["build_debate"])
                   .build_debate(q, spec=spec, metrics=metrics, assistant=assistant), {})

    # 사람 질문(결정적) — 남은 미지 + 반대 근거에서 파생
    questions = _questions(packet, debate)

    stages = [
        {"stage": "Research Report", "ok": True},
        {"stage": "Evidence Review", "ok": bool(packet.get("evidence") or packet.get("supporting_arguments"))},
        {"stage": "Risk Review", "ok": bool(packet.get("risk_summary"))},
        {"stage": "Opposing View", "ok": bool(debate.get("bear_case"))},
        {"stage": "Committee Summary", "ok": True},
        {"stage": "Human Decision", "ok": None, "note": "사람 입력 대기(engine 은 결정하지 않음)"},
    ]
    return {"question": q, "workflow_stages": stages,
            "research_summary": packet.get("thesis") or packet.get("rationale") or q,
            "supporting_evidence": {"evidence": packet.get("evidence", {}),
                                    "arguments": packet.get("supporting_arguments", []),
                                    "bull_case": debate.get("bull_case", {})},
            "risk_summary": {"risk": packet.get("risk_summary", {}),
                             "bear_case": debate.get("bear_case", {}),
                             "risk_case": debate.get("risk_case", {})},
            "alternative_views": {"counter_arguments": packet.get("counter_arguments", []),
                                  "alternative_explanation": debate.get("alternative_explanation", {}),
                                  "council": packet.get("council", {}),
                                  "historical_counterexamples": debate.get("historical_counterexamples", [])},
            "confidence": packet.get("confidence"),
            "confidence_breakdown": packet.get("confidence_breakdown", {}),
            "limitations": (debate.get("missing_evidence", []) +
                            packet.get("remaining_unknowns", []))[:8] or ["근거 축적 초기 — 사람 검토 필수"],
            "questions_for_human": questions,
            "decision_history": packet.get("decision_history", []),
            "requires_human_review": True, "requires_human_decision": True,
            "is_advisory": True, "is_decision": False,
            "note": ("CommitteePacket(읽기전용) — 요약·증거·리스크·반대시각·신뢰도·한계·사람질문. "
                     "BUY/SELL/EXECUTE/ALLOCATE 출력 없음. 결정·이유는 사람이 입력. 새 저장소 없음.")}


def _questions(packet, debate) -> list:
    qs = []
    for u in (packet.get("remaining_unknowns") or [])[:3]:
        qs.append(f"미지: {u} — 추가 근거가 필요한가?")
    for m in (debate.get("missing_evidence") or [])[:2]:
        qs.append(f"누락 증거: {m} — 확보 가능한가?")
    if debate.get("historical_counterexamples"):
        qs.append("역사적 반례가 존재한다 — 현재 조건이 어떻게 다른가?")
    return qs or ["이 연구를 진행할 만한 근거가 충분한가? (사람 판단)"]
