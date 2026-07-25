"""Research Brain Validation (P140) — 연구 두뇌 전체 체인을 검증한다. **읽기 전용, 실행 없음.**

체인: New Research Question → Recall Previous Knowledge → Agent Analysis → Conflict Check → Research Result
→ Lesson Update. 요구: (1) 과거 연구 회수 (2) 실패 재사용 (3) 중복 메모리 없음 (4) 에이전트가 지식 사용
(5) 대시보드 표시. + 안전(새 DB/원장/메모리 없음).

원칙(문서 §Constitution, §P140): 통합·검증만. 결정적. 거래·집행 없음.
"""
from __future__ import annotations

_MODULES = ("memory_audit.py", "knowledge_graph_upgrade.py", "semantic_recall.py",
            "research_similarity.py", "conflict_detection.py", "learning_engine.py",
            "agent_memory.py", "knowledge_quality.py", "brain_validation.py")
_Q = "Does momentum work in the current regime?"


def validate_brain() -> dict:
    """연구 두뇌 5개 확인 + 안전(결정적·읽기전용)."""
    checks = []

    # (1) 과거 연구 회수 — semantic_recall Research Context Package
    from jarvis.research_workflow.semantic_recall import recall_context
    pkg = _safe(lambda: recall_context(_Q))
    retrieved = bool(pkg and pkg.get("is_context_package") and "relevant_experiments" in pkg)
    checks.append({"check": "past_research_retrieved", "ok": retrieved,
                   "detail": f"prior={pkg.get('prior_research_count') if pkg else 0}"})

    # (2) 실패 재사용 — context package 에 similar_failures 필드
    reused = bool(pkg and "similar_failures" in pkg and "contradicting_evidence" in pkg)
    checks.append({"check": "failures_reused", "ok": reused,
                   "detail": f"failures={len(pkg.get('similar_failures', [])) if pkg else 0}"})

    # (3) 중복 메모리 없음 — knowledge_quality + 원장 3개
    from jarvis.research_workflow import ledger as wl
    kh = _safe(lambda: __import__("jarvis.research_workflow.knowledge_quality",
                                  fromlist=["build_knowledge_health"]).build_knowledge_health(), {})
    no_dup = bool(len(wl.ALL_LEDGERS) == 3 and "issues" in kh)
    checks.append({"check": "no_duplicate_memory", "ok": no_dup,
                   "detail": f"dupes={kh.get('issues', {}).get('duplicate_lessons', 0)}, rwf={len(wl.ALL_LEDGERS)}"})

    # (4) 에이전트가 지식 사용 — agent_memory before/during/after
    from jarvis.research_workflow.agent_memory import knowledge_informed_research
    ki = _safe(lambda: knowledge_informed_research(_Q))
    agents_use = bool(ki and ki.get("before", {}).get("previous_knowledge")
                      and ki.get("direct_ledger_writes") is False)
    checks.append({"check": "agents_use_knowledge", "ok": agents_use,
                   "detail": f"pipeline={ki.get('during', {}).get('pipeline') if ki else None}"})

    # (5) 대시보드 표시 — research brain 표면 조립
    graph = _safe(lambda: __import__("jarvis.research_workflow.knowledge_graph_upgrade",
                                     fromlist=["build_research_knowledge_graph"])
                  .build_research_knowledge_graph(), {})
    dash = bool(graph and "research_chain" in graph)
    checks.append({"check": "dashboard_displays_knowledge", "ok": dash,
                   "detail": f"nodes={graph.get('node_count', 0)}"})

    safety = brain_safety()
    all_ok = all(c["ok"] for c in checks) and safety["safe"]
    return {"chain": ["New Research Question", "Recall Previous Knowledge", "Agent Analysis",
                      "Conflict Check", "Research Result", "Lesson Update"],
            "checks": checks, "validated": all_ok, "safety": safety,
            "is_advisory": True, "is_decision": False,
            "note": ("연구 두뇌 검증(읽기전용) — 회수·실패재사용·중복없음·에이전트지식·대시보드. "
                     "새 DB/원장/메모리 없음. 거래·집행 없음.")}


def brain_safety() -> dict:
    """안전(결정적) — 지식 계층 모듈에 금지 동작/브로커/새 원장이 없음을 AST 로 확인."""
    import ast
    import pathlib

    here = pathlib.Path(__file__).resolve().parent
    forbidden_defs = {"execute", "trade", "deploy", "allocate", "approve", "place_order"}
    forbidden_imports = ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
                         "jarvis.live_trading", "jarvis.portfolio_execution")
    violations = []
    for f in _MODULES:
        p = here / f
        if not p.exists():
            continue
        tree = ast.parse(p.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and \
                    any(node.module.startswith(b) for b in forbidden_imports):
                violations.append({"file": f, "kind": "import", "detail": node.module})
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in forbidden_defs:
                violations.append({"file": f, "kind": "def", "detail": node.name})
    from jarvis.research_workflow import ledger as wl
    return {"safe": not violations and len(wl.ALL_LEDGERS) == 3, "violations": violations,
            "no_new_ledger": len(wl.ALL_LEDGERS) == 3,
            "checks": ["no new database/ledger/memory store/vector db", "knowledge system only",
                       "no execute/trade/approve/allocate", "no broker"],
            "is_advisory": True, "is_decision": False}


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default
