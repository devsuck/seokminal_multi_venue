"""Hypothesis Generator (P73) — 후보 가설을 결정적으로 생성한다. **제안만, 실행/결정 없음.**

기존 서브시스템을 재사용: research_queue(미탐색 조합·실패 강건화·레짐·이벤트) + failure_intelligence + memory
graph(recall) + event_intelligence(공급망) + 포트폴리오/레짐 컨텍스트. 각 가설은 rationale·expected edge·
assumptions·invalidation conditions 를 포함하고, **기존 메모리 인프라(rmi_)** 로 저장된다(recall 가능).

원칙(문서 §Constitution, §P73): 새 지능/새 저장소 없음 — 조율. 결정적. 거래·집행·자본배분 없음.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from jarvis.research_workflow import models as M

# 소스(제안 kind) → 가정/무효화 조건 템플릿 (결정적)
_TEMPLATES = {
    "COMBINATION": {
        "assumptions": ["개별 신호가 각자 엣지를 유지한다", "조합 효과가 단순 합 이상이다"],
        "invalidation": ["조합 sharpe ≤ 개별 최대", "두 신호 상관이 높아 중복"],
    },
    "FAILURE_FIX": {
        "assumptions": ["실패 원인이 교정 가능하다", "교정이 엣지를 제거하지 않는다"],
        "invalidation": ["walk-forward 에서 동일 실패 재발", "교정 후 sharpe 가 baseline 미만"],
    },
    "REGIME": {
        "assumptions": ["테스트 기간 동안 현 레짐 유지", "신호가 레짐 조건부다"],
        "invalidation": ["레짐 밖에서 엣지 소멸", "레짐 오분류"],
    },
    "EVENT": {
        "assumptions": ["이벤트 파급이 성립한다", "영향 개체가 충분히 유동적이다"],
        "invalidation": ["측정 가능한 영향 없음", "이미 가격에 반영됨"],
    },
    "SUPPLY_CHAIN": {
        "assumptions": ["공급망 링크가 수익률로 전파된다", "리드-래그가 존재한다"],
        "invalidation": ["교차상관 유의성 없음", "동시성으로 알파 없음"],
    },
    "PORTFOLIO": {
        "assumptions": ["신규 전략이 기존과 낮은 상관", "분산이 리스크조정 수익을 개선"],
        "invalidation": ["상관 상승으로 분산 소멸", "집중 리스크 증가"],
    },
}
_EDGE = {"HIGH": "HIGH", "MEDIUM": "MEDIUM", "LOW": "LOW"}


@dataclass(frozen=True)
class Hypothesis:
    hypothesis_id: str
    statement: str
    rationale: str
    expected_edge: str            # LOW | MEDIUM | HIGH
    assumptions: list
    invalidation_conditions: list
    source: str
    confidence: str
    requires_human_review: bool = True
    is_advisory: bool = True
    is_decision: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class HypothesisGenerator:
    """후보 가설 생성기 — 기존 큐/실패/이벤트/메모리 조율. 실행 권한 없음."""

    def __init__(self, assistant=None, reader=None, memory_engine=None) -> None:
        if assistant is None:
            from jarvis.research_assistant.engine import ResearchAssistantEngine
            assistant = ResearchAssistantEngine(reader)
        self._asst = assistant
        self._mem = memory_engine

    def _memory(self):
        if self._mem is None:
            from jarvis.research_memory_intelligence.engine import ResearchMemoryIntelligenceEngine
            self._mem = ResearchMemoryIntelligenceEngine()
        return self._mem

    def _hyp(self, statement, rationale, edge, source, confidence, template_key) -> Hypothesis:
        t = _TEMPLATES.get(template_key, {"assumptions": [], "invalidation": []})
        return Hypothesis(
            hypothesis_id=M.hypothesis_id(statement), statement=statement, rationale=rationale,
            expected_edge=_EDGE.get(edge, "MEDIUM"), assumptions=list(t["assumptions"]),
            invalidation_conditions=list(t["invalidation"]), source=source, confidence=confidence)

    def _from_proposal(self, p) -> Hypothesis:
        return self._hyp(
            statement=f"{p.name} produces a persistent, cost-robust edge",
            rationale=p.reason, edge=p.expected_value, source=f"queue:{p.kind}",
            confidence=p.confidence, template_key=p.kind)

    def _supply_chain(self, limit) -> list:
        from jarvis.research_assistant.event_intelligence import MarketEventIntelligence
        rels = MarketEventIntelligence().relationship_graph()["edges"]
        out = []
        for e in sorted(rels, key=lambda x: (x["source"], x["target"]))[:limit]:
            s, t = e["source"], e["target"]
            out.append(self._hyp(
                statement=f"Shocks to {s} lead-lag propagate to {t} returns",
                rationale=f"{s} → {t} ({e['kind']}) supply-chain linkage — lead-lag alpha candidate.",
                edge="MEDIUM", source="supply_chain", confidence="MEDIUM",
                template_key="SUPPLY_CHAIN"))
        return out

    def _portfolio(self, portfolio) -> list:
        return [self._hyp(
            statement="A low-correlation strategy improves portfolio risk-adjusted return",
            rationale="포트폴리오 컨텍스트 — 낮은 상관 신규 전략은 분산 이점 후보.",
            edge="MEDIUM", source="portfolio", confidence="MEDIUM", template_key="PORTFOLIO")]

    def generate(self, topic=None, *, regime=None, portfolio=None, events=None, limit=8) -> list:
        """후보 가설 생성(결정적). 큐 재사용 + 공급망 + (선택)포트폴리오. 사람 검토 필요."""
        from jarvis.research_assistant.research_queue import ResearchQueueEngine
        q = ResearchQueueEngine(assistant=self._asst).generate(regime=regime, events=events, limit=limit)
        queue_hyps = [self._from_proposal(p) for p in q.proposals]
        extras = self._supply_chain(limit=2)          # 항상 포함(슬롯 예약)
        if portfolio is not None:
            extras += self._portfolio(portfolio)
        keep_q = max(1, limit - len(extras))
        hyps = queue_hyps[:keep_q] + extras
        seen, out = set(), []
        for h in hyps:
            if h.hypothesis_id not in seen:
                seen.add(h.hypothesis_id)
                out.append(h)
        return out[:limit]

    def store(self, hypothesis: Hypothesis, *, now="", commit=False):
        """가설을 기존 rmi_ 메모리에 교훈으로 저장(새 저장소 없음). recall 이 찾는다. 자문일 뿐."""
        les = (f"HYPOTHESIS [{hypothesis.source}] — {hypothesis.statement} "
               f"(edge={hypothesis.expected_edge}, confidence={hypothesis.confidence})")
        rec = self._memory().record_lesson(
            origin=hypothesis.hypothesis_id, lesson=les,
            evidence={"hypothesis": hypothesis.to_dict()}, impact="hypothesis",
            now=now, commit=commit)
        return rec.to_dict() if hasattr(rec, "to_dict") else rec
