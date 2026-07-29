"""Explainability Layer (P67) — 모든 결론에 **증거 사슬**을 부여한다. **블랙박스 결정 금지.**

Experiment → Validation → Failure Lessons → Historical Memory → Council Opinions → Portfolio →
Risk → Final Recommendation 을 결정적으로 연결하고, 신뢰도 분해·왜 이 결론·왜 틀릴 수 있는지·대안 해석·
누락 근거를 제시한다. 새 지능/새 저장소 없음 — gather_evidence(읽기 전용) 조율. 사람이 최종 결정.
"""
from __future__ import annotations

from jarvis.research_workflow import _evidence as EV
from jarvis.research_workflow.models import EvidenceChain

# 증거 사슬의 고정 순서(문서 파이프라인)
_CHAIN_ORDER = ("Experiment", "Validation", "Failure Lessons", "Historical Memory",
                "Council Opinions", "Portfolio Analysis", "Risk Analysis", "Final Recommendation")


class ExplainabilityEngine:
    """결론의 증거 사슬·신뢰도 분해·반증·대안·누락 근거. 조율만, 결정 권한 없음."""

    def __init__(self, assistant=None, reader=None) -> None:
        self._assistant = assistant
        self._reader = reader

    def evidence_chain(self, topic, *, metrics=None, new_strategy=None, portfolio=None,
                       strategies=None, backtest=None, evidence=None) -> EvidenceChain:
        """주제 결론의 증거 사슬 + 신뢰도 분해 + 반증/대안/누락. 결정적. 사람 검토 필수."""
        ev = evidence or EV.gather_evidence(
            topic, assistant=self._assistant, reader=self._reader, metrics=metrics,
            new_strategy=new_strategy, portfolio=portfolio, strategies=strategies,
            backtest=backtest)

        cases = EV.historical_cases(ev)
        exp_refs = [c["ref"] for c in cases if c["source"] in ("experiments", "experiment_runs")]
        confidence, breakdown = EV.aggregate_confidence(ev)
        supporting, counter = EV._council_args(ev)
        council = ev.get("council") or {}
        risk = ev.get("risk") or {}
        fi = ev.get("failure_intelligence") or {}
        val = ev.get("validation") or {}

        # 노드: 각 단계의 실제 근거 요약
        nodes = [
            {"stage": "Experiment", "label": f"{len(cases)} recalled records",
             "refs": [c["ref"] for c in cases][:6]},
            {"stage": "Validation",
             "label": ("complete" if val.get("validation_complete") else
                       f"incomplete: missing {len(val.get('missing_validations', []))}"
                       if val else "not provided")},
            {"stage": "Failure Lessons", "label": f"{fi.get('total_failures', 0)} failures · top {fi.get('top_category', '—')}"},
            {"stage": "Historical Memory", "label": (ev.get('recall') or {}).get('headline', '')},
            {"stage": "Council Opinions",
             "label": f"{len(supporting)} support / {len(counter)} caution · {council.get('recommendation', '')}"},
            {"stage": "Portfolio Analysis",
             "label": (ev.get('portfolio') or {}).get('verdict', 'not provided')},
            {"stage": "Risk Analysis",
             "label": f"main {risk.get('main_risk', '—')} ({risk.get('main_risk_label', '')})"},
            {"stage": "Final Recommendation",
             "label": f"{council.get('recommendation', '?')} · confidence {confidence}"},
        ]
        edges = [{"from": _CHAIN_ORDER[i], "to": _CHAIN_ORDER[i + 1], "kind": "supports"}
                 for i in range(len(_CHAIN_ORDER) - 1)]

        why = (f"Recommendation follows from {len(cases)} historical records, "
               f"{len(supporting)} supporting perspectives, risk profile "
               f"'{risk.get('main_risk_label', '')}', and confidence {confidence}.")
        may_be_wrong = [c["rationale"] for c in counter]
        if risk.get("main_risk"):
            may_be_wrong.append(f"Primary risk: {risk.get('main_risk_label')} ({risk.get('main_risk')})")
        if (ev.get("mistake_check") or {}).get("made_this_mistake"):
            may_be_wrong.append(f"Past failures on this topic: {ev['mistake_check'].get('failure_count')}")
        missing = EV.remaining_unknowns(ev)

        return EvidenceChain(
            topic=topic, chain=nodes, edges=edges, confidence=confidence,
            confidence_breakdown=breakdown, why_this_conclusion=why,
            why_it_may_be_wrong=may_be_wrong or ["No counter-evidence surfaced — treat as unverified"],
            alternative_interpretations=EV._alternatives(ev) or ["No conflicting perspectives"],
            missing_evidence=missing, references_experiments=exp_refs)
