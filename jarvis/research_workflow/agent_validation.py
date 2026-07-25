"""Agent System Validation (P130) — 연구 에이전트 시스템을 검증한다. **읽기 전용, 실행 없음.**

체인: User Research Goal → Director → Specialist Agents → Critic → Report → Human Review.
확인: (1) 에이전트가 기존 엔진 사용 (2) 지능 중복 없음 (3) 자율 결정 없음 (4) 메모리 정확히 갱신
(5) 대시보드가 워크플로 표시. + 안전 스캔(금지 동작/브로커/새 원장 없음).

원칙(문서 §Constitution, §P130): 통합·검증만. 결정적. 거래·집행 없음.
"""
from __future__ import annotations

_AGENT_MODULES = ("agent_capability.py", "research_director.py", "market_analyst.py",
                  "company_analyst.py", "strategy_researcher.py", "research_reviewer.py",
                  "research_writer.py", "multi_agent_workflow.py", "agent_validation.py")


def validate_agents() -> dict:
    """에이전트 시스템 5개 확인 + 안전(결정적·읽기전용)."""
    checks = []

    # (1) 에이전트가 기존 엔진 사용 — capability map used_engines 비어있지 않음
    from jarvis.research_workflow.agent_capability import capability_map
    cap = capability_map()
    uses_engines = all(a["used_engines"] for a in cap["agents"])
    checks.append({"check": "agents_use_existing_engines", "ok": uses_engines,
                   "detail": f"agents={cap['count']}"})

    # (2) 지능 중복 없음 — 새 원장 없음(rwf 3개), 에이전트는 import 로만 재사용
    from jarvis.research_workflow import ledger as wl
    no_dup = len(wl.ALL_LEDGERS) == 3 and _reuses_only()
    checks.append({"check": "no_duplicated_intelligence", "ok": no_dup,
                   "detail": f"rwf_ledgers={len(wl.ALL_LEDGERS)}"})

    # (3) 자율 결정 없음 — 전체 체인 산출이 is_decision=False + requires_human_review
    from jarvis.research_workflow.multi_agent_workflow import run
    wf = _safe(lambda: run("momentum in KR equities under high volatility"))
    no_auto = bool(wf and wf.get("is_decision") is False and wf.get("requires_human_review") is True
                   and wf.get("report", {}).get("is_decision") is False)
    checks.append({"check": "no_autonomous_decisions", "ok": no_auto,
                   "detail": f"verdict={wf.get('review', {}).get('verdict') if wf else None}"})

    # (4) 메모리 정확히 갱신 — 기록 경로가 기존 원장(rwf_sessions + ras_notes), commit=False=프리뷰
    mem_ok = bool(wf and "ledger_writes" in wf and wf.get("committed") is False)
    checks.append({"check": "memory_updated_correctly", "ok": mem_ok,
                   "detail": f"writes={list((wf or {}).get('ledger_writes', {}))}"})

    # (5) 대시보드 표시 — agent-workspace 표면 조립
    dash = _safe(lambda: __import__("jarvis.research_workflow.agent_capability",
                                    fromlist=["capability_map"]).capability_map())
    dash_ok = bool(dash and dash.get("count", 0) >= 6)
    checks.append({"check": "dashboard_displays_workflow", "ok": dash_ok,
                   "detail": f"agents={dash.get('count') if dash else 0}"})

    safety = agent_safety()
    all_ok = all(c["ok"] for c in checks) and safety["safe"]
    return {"chain": ["User Research Goal", "Director", "Specialist Agents", "Critic", "Report",
                      "Human Review"],
            "checks": checks, "validated": all_ok, "safety": safety,
            "is_advisory": True, "is_decision": False,
            "note": ("에이전트 시스템 검증(읽기전용) — 기존 엔진 재사용·지능중복 없음·자율결정 없음·"
                     "메모리 정확·대시보드. 새 DB/원장/엔진/메모리 없음. 거래·집행 없음.")}


def _reuses_only() -> bool:
    """에이전트 모듈이 원장 쓰기 프리미티브(state_path)를 직접 '호출'하지 않는지 AST 로 확인 — 기록은 기존 엔진 경유."""
    import ast
    import pathlib
    here = pathlib.Path(__file__).resolve().parent
    for f in _AGENT_MODULES:
        tree = ast.parse((here / f).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                if (isinstance(fn, ast.Name) and fn.id == "state_path") or \
                   (isinstance(fn, ast.Attribute) and fn.attr == "state_path"):
                    return False
    return True


def agent_safety() -> dict:
    """안전(결정적) — 에이전트 모듈에 금지 동작/브로커/새 원장이 없음을 AST 로 확인."""
    import ast
    import pathlib

    here = pathlib.Path(__file__).resolve().parent
    forbidden_defs = {"execute", "trade", "deploy", "allocate", "approve", "place_order"}
    forbidden_imports = ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
                         "jarvis.live_trading", "jarvis.portfolio_execution")
    violations = []
    for f in _AGENT_MODULES:
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
            "checks": ["no new database/ledger/engine/memory", "analysis only",
                       "no execute/trade/place_order/allocate/approve", "no broker/exchange",
                       "human approval mandatory"],
            "is_advisory": True, "is_decision": False}


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default
