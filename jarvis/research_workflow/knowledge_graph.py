"""Research Knowledge Graph (P79) — 기존 그래프 인프라를 **재사용**해 연구 지식을 연결한다. **읽기 전용, 새 저장소 없음.**

research_assistant.memory_graph(Experiment→Failure→Lesson) + event_intelligence.relationship_graph
(공급망/기업/섹터) + ring_ 수집(Strategy/Backtest) 를 하나의 다개체 그래프로 합친다.
개체: Experiment·Strategy·Failure·Lesson·Portfolio·MacroEvent·Sector·Risk·DecisionMemo·PaperResult.
관계: uses·affects·failed·supports·contradicts·validated_by·similar_to·tested_after·caused_by.

원칙(문서 §Constitution, §P79): 통합·시각화만 — 새 그래프 엔진 없음. 결정적. 거래·집행 없음.
"""
from __future__ import annotations

REL_KINDS = ("uses", "affects", "failed", "supports", "contradicts", "validated_by",
             "similar_to", "tested_after", "caused_by")


def _read(mod_name, fn_name):
    try:
        mod = __import__(mod_name, fromlist=[fn_name])
        return list(getattr(mod, fn_name)() or [])
    except Exception:  # noqa: BLE001
        return []


def build_knowledge_graph(topic: str = "", *, limit: int = 120) -> dict:
    """다개체 지식 그래프 재구성(읽기 전용). 기존 memory_graph + relationship_graph + ring_ 결합."""
    t = (topic or "").strip().lower()
    nodes: dict = {}
    edges: list = []

    def node(nid, ntype, label):
        if nid not in nodes:
            nodes[nid] = {"id": nid, "type": ntype, "label": str(label)[:40]}
        return nid

    def edge(a, b, kind):
        if a and b and kind in REL_KINDS:
            edges.append({"source": a, "target": b, "kind": kind})

    # 1) 재사용: research_assistant.memory_graph (Experiment→Failure Category→Lesson)
    try:
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        mg = ResearchAssistantEngine().memory_graph(limit=limit)
        typemap = {"EXPERIMENT": "Experiment", "CATEGORY": "Failure", "KNOWLEDGE": "Lesson"}
        for n in mg.get("nodes", []):
            node(n["id"], typemap.get(n.get("type"), n.get("type", "Lesson")), n.get("label", ""))
        for e in mg.get("edges", []):
            edge(e["source"], e["target"], "failed" if e.get("kind") == "failed_as" else "caused_by")
    except Exception:  # noqa: BLE001
        pass

    # 2) 재사용: event_intelligence.relationship_graph (MacroEvent/Sector/기업 — affects)
    try:
        from jarvis.research_assistant.event_intelligence import MarketEventIntelligence
        rg = MarketEventIntelligence().relationship_graph()
        for n in rg.get("nodes", []):
            nid = f"EV:{n['id']}"
            node(nid, "Sector" if n["id"].isupper() and len(n["id"]) <= 4 else "MacroEvent", n["id"])
        for e in rg.get("edges", []):
            edge(f"EV:{e['source']}", f"EV:{e['target']}", "affects")
    except Exception:  # noqa: BLE001
        pass

    # 3) ring_ 수집 → Strategy·Backtest·PaperResult·Failure/Validation (uses/tested_after/failed/validated_by)
    ring = _read("jarvis.research_ingestion.ledger", "read_ingestions")
    by_strategy: dict = {}
    for r in ring:
        name = str(r.get("strategy_name", "?"))
        if t and t not in name.lower():
            continue
        sid = node(f"S:{name}", "Strategy", name)
        eid = node(f"E:{r.get('experiment_id', name)}", "Experiment", r.get("experiment_id", name))
        edge(sid, eid, "uses")
        outcome = r.get("outcome")
        if outcome == "FAILURE":
            fid = node(f"F:{r.get('failure_category', 'UNCLASSIFIED')}", "Failure",
                       r.get("failure_category", "UNCLASSIFIED"))
            edge(eid, fid, "failed")
        elif outcome == "SUCCESS":
            vid = node(f"V:{name}", "Risk", f"validated:{name}")
            edge(eid, vid, "validated_by")
        if r.get("source_type") == "revalidation":
            edge(eid, node(f"E:{r.get('experiment_id')}", "Experiment", ""), "tested_after")
        by_strategy.setdefault(name, []).append(r)

    # 4) similar_to — 같은 유형(리스크 프로파일) 전략끼리
    try:
        from jarvis.research_risk_intelligence.failure_reasoning import _profile
        by_type: dict = {}
        for name in by_strategy:
            by_type.setdefault(_profile(name)["type"], []).append(name)
        for names in by_type.values():
            for i in range(len(names)):
                for j in range(i + 1, len(names)):
                    edge(f"S:{names[i]}", f"S:{names[j]}", "similar_to")
    except Exception:  # noqa: BLE001
        pass

    # 5) DecisionMemo (ras_ notes) — supports
    for r in _read("jarvis.research_assistant.ledger", "read_notes"):
        area = str(r.get("area", ""))
        if area.startswith(("decision:", "council:")):
            if t and t not in area.lower():
                continue
            dm = node(f"DM:{area}", "DecisionMemo", area.split(":", 1)[-1])
            edges.append({"source": dm, "target": dm, "kind": "supports"})

    nlist = list(nodes.values())[:limit]
    keep = {n["id"] for n in nlist}
    elist = [e for e in edges if e["source"] in keep and e["target"] in keep]
    ntypes: dict = {}
    for n in nlist:
        ntypes[n["type"]] = ntypes.get(n["type"], 0) + 1
    ekinds: dict = {}
    for e in elist:
        ekinds[e["kind"]] = ekinds.get(e["kind"], 0) + 1
    return {"topic": topic, "nodes": nlist, "edges": elist, "node_count": len(nlist),
            "edge_count": len(elist), "node_types": ntypes, "edge_kinds": ekinds,
            "relationship_kinds": list(REL_KINDS), "is_advisory": True, "is_decision": False,
            "note": "기존 그래프(memory_graph/relationship_graph)+원장 결합 — 읽기전용, 새 그래프 엔진 없음."}
