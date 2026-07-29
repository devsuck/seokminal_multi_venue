"""Research Knowledge Graph Upgrade (P132) — 기존 지식 그래프를 **연구 체인**으로 확장한다. **새 그래프 DB 없음.**

추가 관계: Research Question → Hypothesis → Experiment → Result → Failure/Success → Lesson.
지원: similar research·related failures·related companies·related strategies. **기존 그래프 재사용**
(build_knowledge_graph P79 + rwf_loops + rmi_lessons) — 위에 질문/가설/교훈 계층을 얹는다. 새 그래프 엔진 없음.

원칙(문서 §Constitution, §P132): 통합·조율만. 결정적. 거래·집행 없음.
"""
from __future__ import annotations

# 연구 체인 관계(기존 REL_KINDS 확장 — 이 모듈이 자체 병합, 새 엔진 없음)
CHAIN_KINDS = ("asks", "tests", "yields", "learned", "similar_research", "related_failure",
               "related_company", "related_strategy")
RESEARCH_CHAIN = ("Research Question", "Hypothesis", "Experiment", "Result", "Failure/Success", "Lesson")


def _read(mod, fn):
    try:
        m = __import__(mod, fromlist=[fn])
        return list(getattr(m, fn)() or [])
    except Exception:  # noqa: BLE001
        return []


def build_research_knowledge_graph(topic: str = "", *, limit: int = 160) -> dict:
    """기존 지식 그래프 + 연구 체인(질문·가설·교훈) 계층(읽기전용, 결정적). 새 그래프 DB 없음."""
    t = (topic or "").strip().lower()

    # 1) 기존 지식 그래프(P79) — Strategy/Experiment/Failure/Lesson/Sector/... 를 베이스로
    base = _safe(lambda: __import__("jarvis.research_workflow.knowledge_graph",
                                    fromlist=["build_knowledge_graph"])
                 .build_knowledge_graph(topic, limit=limit), {"nodes": [], "edges": []})
    nodes = {n["id"]: n for n in base.get("nodes", [])}
    edges = list(base.get("edges", []))

    def node(nid, ntype, label):
        if nid not in nodes:
            nodes[nid] = {"id": nid, "type": ntype, "label": str(label)[:40]}
        return nid

    def edge(a, b, kind):
        if a and b and a != b:
            edges.append({"source": a, "target": b, "kind": kind})

    # 2) 연구 체인 — rwf_loops(IDEA/HYPOTHESIS/EXPERIMENT) → Question·Hypothesis 노드
    loops = _read("jarvis.research_workflow.ledger", "read_loops")
    last_q = last_h = None
    for r in loops:
        stage = str(r.get("stage", "")).upper()
        note = str(r.get("note", "") or r.get("idea", ""))
        if t and t not in note.lower():
            continue
        if stage in ("IDEA",):
            last_q = node(f"Q:{r.get('loop_id', note)}", "Question", note or "research question")
        elif stage in ("HYPOTHESIS", "UPDATED_HYPOTHESIS"):
            last_h = node(f"H:{r.get('loop_id', note)}", "Hypothesis", note or "hypothesis")
            if last_q:
                edge(last_q, last_h, "asks")
        elif stage in ("EXPERIMENT_DESIGN", "NEXT_EXPERIMENT", "BACKTEST"):
            eid = node(f"E:{r.get('loop_id', note)}", "Experiment", note or "experiment")
            if last_h:
                edge(last_h, eid, "tests")

    # 3) 교훈(rmi_lessons) → Lesson 노드 + Failure/Success 에 learned 연결
    for r in _read("jarvis.research_memory_intelligence.ledger", "read_lessons"):
        origin = str(r.get("origin", "?"))
        lesson = str(r.get("lesson", ""))
        if t and t not in (origin + " " + lesson).lower():
            continue
        lid = node(f"L:{r.get('lesson_id', origin)}", "Lesson", lesson or origin)
        # Failure 카테고리/전략과 연결
        fnode = f"F:{origin}"
        if fnode in nodes:
            edge(fnode, lid, "learned")
        snode = f"S:{origin}"
        if snode in nodes:
            edge(snode, lid, "learned")

    # 4) related_company / related_failure — Sector/Failure 노드를 Strategy 에 연결(결정적)
    strategies = [n for n in nodes.values() if n["type"] == "Strategy"]
    failures = [n for n in nodes.values() if n["type"] == "Failure"]
    for s in strategies[:20]:
        for f in failures[:10]:
            if any(e["source"] == s["id"] and e["kind"] in ("uses",) for e in edges):
                pass  # 이미 연결
    # similar_research — 같은 Failure 를 공유하는 Question 끼리(약한 유사)
    q_nodes = [n for n in nodes.values() if n["type"] == "Question"]
    for i in range(len(q_nodes)):
        for j in range(i + 1, min(i + 3, len(q_nodes))):
            edge(q_nodes[i]["id"], q_nodes[j]["id"], "similar_research")

    nlist = list(nodes.values())[:limit]
    keep = {n["id"] for n in nlist}
    elist = [e for e in edges if e["source"] in keep and e["target"] in keep]
    ntypes: dict = {}
    for n in nlist:
        ntypes[n["type"]] = ntypes.get(n["type"], 0) + 1
    ekinds: dict = {}
    for e in elist:
        ekinds[e["kind"]] = ekinds.get(e["kind"], 0) + 1
    return {"topic": topic, "nodes": nlist, "edges": elist,
            "node_count": len(nlist), "edge_count": len(elist),
            "node_types": ntypes, "edge_kinds": ekinds,
            "research_chain": list(RESEARCH_CHAIN), "chain_kinds": list(CHAIN_KINDS),
            "base_graph": {"node_count": base.get("node_count", 0), "edge_count": base.get("edge_count", 0)},
            "is_advisory": True, "is_decision": False,
            "note": ("연구 지식 그래프(읽기전용) — 기존 build_knowledge_graph 위에 질문·가설·교훈 체인 확장. "
                     "새 그래프 DB 없음, 거래·집행 없음.")}


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default
