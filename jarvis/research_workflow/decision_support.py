"""Decision Support Engine (P65) — 기존 산출을 **하나의 Decision Memo** 로 통합한다. **결정하지 않는다.**

Risk Report·Portfolio Report·Council Memo·Validation·Paper Feedback 을 결정적으로 종합해 사람이 읽는
Decision Memo 를 만든다. **모든 권고는 스스로를 설명한다**(근거·찬반·미지·다음 연구). 결정/집행 없음 —
requires_human_review=True.

원칙: 새 지능/새 저장소 없음 — gather_evidence(읽기 전용) 조율. 결정적. 사람이 최종 결정.
"""
from __future__ import annotations

from jarvis.research_workflow import _evidence as EV
from jarvis.research_workflow.models import DecisionMemo, content_digest


class DecisionSupportEngine:
    """여러 서브시스템 산출 → 단일 Decision Memo. 조율만, 결정 권한 없음."""

    def __init__(self, assistant=None, reader=None) -> None:
        self._assistant = assistant
        self._reader = reader

    def build_memo(self, question, *, topic=None, metrics=None, new_strategy=None,
                   portfolio=None, strategies=None, backtest=None, evidence=None) -> DecisionMemo:
        """질문 → Decision Memo(모든 필수 섹션). 결정적. 사람 검토 필수."""
        t = topic or question
        ev = evidence or EV.gather_evidence(
            t, assistant=self._assistant, reader=self._reader, metrics=metrics,
            new_strategy=new_strategy, portfolio=portfolio, strategies=strategies,
            backtest=backtest)

        supporting, counter = EV._council_args(ev)
        cases = EV.historical_cases(ev)
        confidence, breakdown = EV.aggregate_confidence(ev)
        unknowns = EV.remaining_unknowns(ev)
        council = ev.get("council") or {}
        risk = ev.get("risk") or {}
        portfolio_impact = ev.get("portfolio") or {}
        next_research = [p.get("name") for p in (ev.get("queue") or {}).get("proposals", [])][:3]

        # 권고: 협의체 권고 + 신뢰도 기반(결정 아님 — 사람 검토 프레이밍)
        rec = council.get("recommendation", "INSUFFICIENT BASIS")
        rationale = (f"Confidence {confidence} · council={council.get('recommendation','?')} · "
                     f"main risk={risk.get('main_risk','?')}({risk.get('main_risk_label','')}) · "
                     f"historical cases={len(cases)} · unknowns={len(unknowns)}. "
                     "This memo organizes evidence; the human decides.")

        risk_summary = {"main_risk": risk.get("main_risk"), "label": risk.get("main_risk_label"),
                        "strength": risk.get("strength"), "weakness": risk.get("weakness"),
                        "confidence": risk.get("confidence"),
                        "category_flags": risk.get("category_flags", {})}

        return DecisionMemo(
            question=question, recommendation=rec, rationale=rationale,
            evidence={"digest": content_digest(ev), "sources": sorted(ev.keys())},
            supporting_arguments=supporting, counter_arguments=counter,
            historical_similar_cases=cases, portfolio_impact=portfolio_impact,
            risk_summary=risk_summary, confidence=confidence, confidence_breakdown=breakdown,
            remaining_unknowns=unknowns, suggested_next_research=next_research)

    def record_memo(self, memo: DecisionMemo, now="", *, commit=False):
        """Decision Memo 를 기존 자문 노트 원장(ras_)에 append(비구속). 새 저장소 없음. 사람 승인 필요."""
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        asst = self._assistant or ResearchAssistantEngine(self._reader)
        rec = asst.record_advisory(
            area=f"decision:{memo.question}", rationale=f"{memo.recommendation} | {memo.confidence}",
            evidence_count=len(memo.historical_similar_cases), now=now, commit=commit)
        return rec.to_dict() if hasattr(rec, "to_dict") else rec
