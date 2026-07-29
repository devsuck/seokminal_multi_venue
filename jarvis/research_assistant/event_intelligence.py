"""Market Event Intelligence — 이벤트 영향 분석으로 연구 후보 생성. **분석·제안만, 결정·집행 없음.**

뉴스·매크로·공급망·기업 관계를 연결해 하나의 이벤트가 어디까지 파급되는지 결정적으로 추적한다.
예: Taiwan earthquake → TSMC → NVIDIA → Semiconductor ETF. 파급된 개체에서 연구 후보를 도출해
Research Queue(P58) 에 공급한다.

원칙(문서 §Constitution, §Market Event Intelligence):
  · **새 DB 없음.** 공급망/기업 관계는 정적 참조 그래프(작고 확장 가능) — 원장이 아니다.
  · 결정적 그래프 전파(LLM/랜덤 없음). 출력은 연구 후보(자문) — 사람 승인 필요.
  · 거래·집행·브로커·자본배분 없음.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field

LOW, MEDIUM, HIGH = "LOW", "MEDIUM", "HIGH"

# 정적 관계 참조 그래프(source → target, kind). 확장 가능하나 결정적.
# 공급망/기업/ETF 관계 — 이벤트 파급 추적용(참조 데이터, 저장소 아님).
DEFAULT_RELATIONSHIPS = (
    ("Taiwan", "TSMC", "hosts"),
    ("Taiwan", "Foxconn", "hosts"),
    ("TSMC", "NVIDIA", "fab_supplier"),
    ("TSMC", "AMD", "fab_supplier"),
    ("TSMC", "Apple", "fab_supplier"),
    ("ASML", "TSMC", "equipment_supplier"),
    ("Foxconn", "Apple", "assembler"),
    ("NVIDIA", "SOXX", "etf_member"),
    ("NVIDIA", "SMH", "etf_member"),
    ("AMD", "SOXX", "etf_member"),
    ("Apple", "SMH", "etf_member"),
    ("Nikkei", "TSMC", "correlated_with"),
    ("USD_liquidity", "NVIDIA", "macro_driver"),
)


def _candidate_id(name: str) -> str:
    return "EVC:" + hashlib.sha1(name.strip().lower().encode()).hexdigest()[:12]


@dataclass(frozen=True)
class EventCandidate:
    candidate_id: str
    name: str
    entity: str
    distance: int
    reason: str
    confidence: str
    path: list = field(default_factory=list)   # origin → … → entity

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EventImpact:
    event: str
    origin: str
    affected_entities: list
    impact_chain: dict                     # {nodes, edges}
    candidates: list = field(default_factory=list)
    requires_human_review: bool = True
    is_advisory: bool = True
    is_decision: bool = False
    note: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["candidates"] = [c.to_dict() if isinstance(c, EventCandidate) else c
                           for c in self.candidates]
        return d


class MarketEventIntelligence:
    """이벤트 → 공급망/관계 전파 → 연구 후보. 정적 관계 그래프 기반. 실행 권한 없음."""

    def __init__(self, relationships=None) -> None:
        self._rels = list(relationships if relationships is not None else DEFAULT_RELATIONSHIPS)
        self._adj: dict = {}
        self._nodes: set = set()
        for s, t, kind in self._rels:
            self._adj.setdefault(s, []).append((t, kind))
            self._nodes.add(s)
            self._nodes.add(t)

    def add_relationship(self, source, target, kind) -> None:
        """관계 확장(참조 그래프에만 추가 — 원장 아님)."""
        self._rels.append((source, target, kind))
        self._adj.setdefault(source, []).append((target, kind))
        self._nodes.update({source, target})

    def _detect_origin(self, event) -> str:
        if isinstance(event, dict):
            for k in ("origin", "entity", "source"):
                v = str(event.get(k, "")).strip()
                if v:
                    return v
            text = str(event.get("text") or event.get("name") or event.get("event") or "")
        else:
            text = str(event or "")
        low = text.lower()
        # 알려진 개체를 텍스트에서 탐지(길이 긴 이름 우선 — 결정적)
        for node in sorted(self._nodes, key=lambda n: (-len(n), n)):
            if node.lower() in low:
                return node
        return ""

    def _propagate(self, origin: str, max_depth: int) -> tuple:
        """origin 에서 하류로 BFS 전파. (순서화된 affected[(entity,dist,path)], edges) 반환."""
        seen = {origin: 0}
        order = []
        edges = []
        frontier = [(origin, [origin])]
        depth = 0
        while frontier and depth < max_depth:
            depth += 1
            nxt = []
            for node, path in frontier:
                for tgt, kind in sorted(self._adj.get(node, [])):
                    edges.append({"source": node, "target": tgt, "kind": kind})
                    if tgt not in seen:
                        seen[tgt] = depth
                        npath = path + [tgt]
                        order.append((tgt, depth, npath))
                        nxt.append((tgt, npath))
            frontier = nxt
        return order, edges

    def analyze_event(self, event, *, max_depth: int = 3) -> EventImpact:
        """이벤트 영향 분석 — 파급 개체·영향 체인·연구 후보. 결정적. 사람 검토 필요."""
        label = (event.get("text") or event.get("name") or event.get("event") or str(event)
                 if isinstance(event, dict) else str(event))
        origin = self._detect_origin(event)
        if not origin:
            return EventImpact(event=str(label), origin="", affected_entities=[],
                               impact_chain={"nodes": [], "edges": []}, candidates=[],
                               note="알려진 개체를 이벤트에서 찾지 못함 — 관계 그래프 확장 필요.")
        order, edges = self._propagate(origin, max_depth)
        affected = [e for e, _, _ in order]
        node_ids = [origin] + affected
        nodes = [{"id": n, "label": n} for n in node_ids]
        cands = []
        for entity, dist, path in order:
            conf = HIGH if dist <= 1 else MEDIUM if dist == 2 else LOW
            name = f"{entity} exposure to {origin} shock"
            cands.append(EventCandidate(
                candidate_id=_candidate_id(name), name=name, entity=entity, distance=dist,
                reason=f"{' → '.join(path)} 경로 노출 — '{origin}' 이벤트 파급.",
                confidence=conf, path=path))
        return EventImpact(
            event=str(label), origin=origin, affected_entities=affected,
            impact_chain={"nodes": nodes, "edges": edges}, candidates=cands,
            note=f"'{origin}' → {len(affected)}개 개체 파급(정적 관계 그래프, 읽기 전용).")

    def generate_candidates(self, event, *, max_depth: int = 3) -> list:
        """이벤트 → Research Queue(P58) 가 소비할 후보 리스트(dict)."""
        impact = self.analyze_event(event, max_depth=max_depth)
        return [{"name": c.name, "entity": c.entity, "reason": c.reason,
                 "confidence": c.confidence} for c in impact.candidates]

    def relationship_graph(self) -> dict:
        nodes = [{"id": n, "label": n} for n in sorted(self._nodes)]
        edges = [{"source": s, "target": t, "kind": k} for s, t, k in self._rels]
        return {"nodes": nodes, "edges": edges, "node_count": len(nodes),
                "edge_count": len(edges), "note": "Static supply-chain/company reference graph."}
