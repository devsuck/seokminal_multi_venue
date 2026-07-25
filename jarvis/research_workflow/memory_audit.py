"""Research Memory Audit (P131) — 현재 메모리 시스템을 감사한다. **읽기 전용, 새 저장소 없음.**

매핑: Experiment·Failure·Lesson·Success·Strategy·Company·Market Event. 현재 역량과 누락 연결을 식별한다.
**재사용**: rmi_(memory intelligence)·memory_graph·recall·timeline·knowledge_graph. 새 DB/원장 없음.

원칙(문서 §Constitution, §P131): 통합·감사만. 결정적. 거래·집행 없음.
"""
from __future__ import annotations

# 기존 메모리 저장소(rmi_) + 파생 계층(감사 대상, 정적 참조)
MEMORY_STORES = (
    {"store": "rmi_lessons", "kind": "Lesson", "engine": "research_memory_intelligence",
     "reader": "read_lessons"},
    {"store": "rmi_successes", "kind": "Success", "engine": "research_memory_intelligence",
     "reader": "read_successes"},
    {"store": "rmi_failures", "kind": "Failure", "engine": "research_memory_intelligence",
     "reader": "read_failures"},
    {"store": "rmi_patterns", "kind": "Pattern", "engine": "research_memory_intelligence",
     "reader": "read_patterns"},
    {"store": "rmi_memories", "kind": "Memory(lifecycle)", "engine": "research_memory_intelligence",
     "reader": "read_memories"},
    {"store": "ring_ingestions", "kind": "Experiment/Backtest", "engine": "research_ingestion",
     "reader": "read_ingestions"},
    {"store": "expt_runs", "kind": "Experiment run", "engine": "experiment_tracking",
     "reader": "read_runs"},
    {"store": "ras_notes", "kind": "Advisory/DecisionMemo", "engine": "research_assistant",
     "reader": "read_notes"},
)
# 파생(읽기전용) 지식 계층 — 저장소가 아니라 재구성
DERIVED_LAYERS = (
    {"layer": "recall", "source": "research_assistant.recall", "produces": "topic hits/tried_before"},
    {"layer": "memory_graph", "source": "research_assistant.memory_graph",
     "produces": "Experiment→Failure→Lesson graph"},
    {"layer": "knowledge_graph", "source": "research_workflow.build_knowledge_graph",
     "produces": "multi-entity graph(nodes/edges)"},
    {"layer": "timeline", "source": "research_workflow.build_timeline",
     "produces": "chronological research history"},
    {"layer": "failure_intelligence", "source": "research_assistant.failure_intelligence",
     "produces": "failure taxonomy/lessons"},
)
# 매핑 대상 엔티티(문서 §P131)
ENTITY_TYPES = ("Experiment", "Failure", "Lesson", "Success", "Strategy", "Company", "Market Event")


def _read(mod, fn):
    try:
        m = __import__(mod, fromlist=[fn])
        return list(getattr(m, fn)() or [])
    except Exception:  # noqa: BLE001
        return None


def audit_memory() -> dict:
    """현재 메모리 시스템 감사(읽기전용) — 저장소 카운트·파생계층·현재역량·누락연결."""
    stores = []
    counts: dict = {}
    for s in MEMORY_STORES:
        rows = _read(f"jarvis.{s['engine']}.ledger", s["reader"])
        n = len(rows) if rows is not None else None
        counts[s["kind"]] = (counts.get(s["kind"], 0) or 0) + (n or 0)
        stores.append({**s, "count": n, "available": rows is not None})

    # 현재 역량 — 어떤 엔티티가 커버되는가
    covered = {"Experiment": True, "Failure": True, "Lesson": True, "Success": True,
               "Strategy": True, "Company": None, "Market Event": None}
    # Company/Market Event 는 knowledge_graph 의 Sector/MacroEvent + 이벤트 어댑터로 부분 커버
    try:
        kg = __import__("jarvis.research_workflow.knowledge_graph", fromlist=["build_knowledge_graph"]) \
            .build_knowledge_graph(limit=40)
        ntypes = kg.get("node_types", {})
        covered["Company"] = bool(ntypes.get("Sector") or ntypes.get("MacroEvent"))
        covered["Market Event"] = bool(ntypes.get("MacroEvent"))
    except Exception:  # noqa: BLE001
        pass

    # 누락 연결(문서 §P131) — 이 계층(P132-140)이 채운다
    missing_connections = [
        {"gap": "Research Question → Hypothesis 노드 없음", "filled_by": "P132 knowledge_graph_upgrade"},
        {"gap": "질문 시 자동 컨텍스트 회수 없음", "filled_by": "P133 semantic_recall"},
        {"gap": "연구/전략/기업 유사도 미측정", "filled_by": "P134 research_similarity"},
        {"gap": "모순 결론(works vs fails) 미탐지", "filled_by": "P135 conflict_detection"},
        {"gap": "결과→조직 교훈 자동 변환 없음", "filled_by": "P136 learning_engine"},
        {"gap": "에이전트↔지식 계층 연결 없음", "filled_by": "P137 agent_memory"},
        {"gap": "지식 품질(중복/노후/모순) 감시 없음", "filled_by": "P139 knowledge_quality"},
    ]
    return {"memory_stores": stores, "derived_layers": list(DERIVED_LAYERS),
            "entity_types": list(ENTITY_TYPES), "entity_counts": counts,
            "current_capabilities": covered, "missing_connections": missing_connections,
            "is_advisory": True, "is_decision": False,
            "note": ("메모리 감사(읽기전용) — rmi_/memory_graph/recall/timeline/knowledge_graph. "
                     "새 DB/원장/메모리 없음. 누락 연결은 P132-140 지식 계층이 채움.")}
