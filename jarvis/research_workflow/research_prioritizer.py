"""Research Prioritizer (P76) — 순위가 매겨진 연구 큐를 유지한다. **추천만, 결정 없음.**

7개 요인으로 결정적 스코어링: novelty·expected information gain·implementation cost·portfolio impact·
historical relevance·confidence·uncertainty. **재사용**: research_assistant.recall(novelty/historical
relevance), research_queue/HypothesisGenerator 후보. 다음에 무엇을 연구할지 일관되게 추천(동일 입력 → 동일 순위).

원칙(문서 §Constitution, §P76): 새 지능/새 저장소 없음 — 조율. 결정적. 거래·집행 없음. 사람 결정.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

_CONF = {"HIGH": 0.9, "MEDIUM": 0.6, "LOW": 0.3}
_EDGE = {"HIGH": 0.9, "MEDIUM": 0.6, "LOW": 0.3}
# source(kind) → 구현 비용(낮을수록 저렴) · 포트폴리오 영향
_IMPL_COST = {"queue:FAILURE_FIX": 0.3, "queue:REGIME": 0.4, "queue:COMBINATION": 0.5,
              "queue:EVENT": 0.6, "supply_chain": 0.6, "portfolio": 0.4}
_PORT_IMPACT = {"portfolio": 0.9, "queue:COMBINATION": 0.6, "supply_chain": 0.5,
                "queue:EVENT": 0.5, "queue:FAILURE_FIX": 0.4, "queue:REGIME": 0.4}
# 합성 가중치(결정적)
_W = {"novelty": 0.22, "info_gain": 0.20, "impl": 0.13, "portfolio": 0.15,
      "historical": 0.10, "confidence": 0.20}


@dataclass(frozen=True)
class PriorityItem:
    hypothesis_id: str
    statement: str
    score: float
    rank: int
    scores: dict                 # 7개 요인
    source: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RankedQueue:
    items: list
    recommended: dict            # 최상위(다음 연구 추천)
    count: int
    requires_human_review: bool = True
    is_advisory: bool = True
    is_decision: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["items"] = [i.to_dict() if isinstance(i, PriorityItem) else i for i in self.items]
        return d


class ResearchPrioritizer:
    """연구 후보 순위화 — 7요인 결정적 스코어. recall 재사용. 실행 권한 없음."""

    def __init__(self, assistant=None, reader=None) -> None:
        if assistant is None:
            from jarvis.research_assistant.engine import ResearchAssistantEngine
            assistant = ResearchAssistantEngine(reader)
        self._asst = assistant

    def _hits(self, statement) -> int:
        from jarvis.research_assistant.models import extract_topic
        topic = extract_topic(statement) or statement
        try:
            return int(self._asst.recall(topic).total_hits)
        except Exception:  # noqa: BLE001
            return 0

    def _score(self, cand: dict) -> tuple:
        stmt = str(cand.get("statement", ""))
        source = str(cand.get("source", "queue:COMBINATION"))
        conf = _CONF.get(str(cand.get("confidence", "MEDIUM")).upper(), 0.6)
        edge = _EDGE.get(str(cand.get("expected_edge", "MEDIUM")).upper(), 0.6)
        hits = self._hits(stmt)
        novelty = round(1 - min(1.0, hits / 5.0), 4)
        historical = round(min(1.0, hits / 5.0), 4)
        info_gain = round(0.5 * novelty + 0.5 * edge, 4)
        impl_cost = _IMPL_COST.get(source, 0.5)
        impl_score = round(1 - impl_cost, 4)
        port = _PORT_IMPACT.get(source, 0.5)
        uncertainty = round(1 - conf, 4)
        composite = round(
            _W["novelty"] * novelty + _W["info_gain"] * info_gain + _W["impl"] * impl_score
            + _W["portfolio"] * port + _W["historical"] * historical + _W["confidence"] * conf, 4)
        scores = {"novelty": novelty, "expected_information_gain": info_gain,
                  "implementation_cost": impl_cost, "portfolio_impact": port,
                  "historical_relevance": historical, "confidence": conf,
                  "uncertainty": uncertainty}
        return composite, scores

    def prioritize(self, candidates) -> RankedQueue:
        """후보 리스트 → 순위 큐(결정적). 동일 입력 → 동일 순위(타이브레이크: hypothesis_id)."""
        cands = [c.to_dict() if hasattr(c, "to_dict") else dict(c) for c in (candidates or [])]
        scored = []
        for c in cands:
            comp, scores = self._score(c)
            scored.append((comp, c, scores))
        # 내림차순 + 결정적 타이브레이크
        scored.sort(key=lambda x: (-x[0], x[1].get("hypothesis_id", ""), x[1].get("statement", "")))
        items = []
        for rank, (comp, c, scores) in enumerate(scored, start=1):
            items.append(PriorityItem(
                hypothesis_id=str(c.get("hypothesis_id", "")), statement=str(c.get("statement", "")),
                score=comp, rank=rank, scores=scores, source=str(c.get("source", ""))))
        recommended = items[0].to_dict() if items else {}
        return RankedQueue(items=items, recommended=recommended, count=len(items))

    def recommend_next(self, candidates) -> dict:
        """다음에 무엇을 연구할지 — 최상위 후보(자문). 사람 승인 필요."""
        q = self.prioritize(candidates)
        return q.recommended
