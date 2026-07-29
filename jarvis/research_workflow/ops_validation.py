"""Jarvis Research OS v1.5 Validation (P150) — 운영 연구 조직 전체 루프를 검증한다. **읽기 전용, 실행 없음.**

루프: External Data → Research Opportunity → Agent Research → Experiment → Validation → Knowledge Update →
Future Research Improvement. 7개 확인: scheduler·agents·reports·knowledge·human review·no duplicate·safety.
(P120 operational_validation 와 별개 — 운영 조직 계층 검증.)

원칙(문서 §Constitution, §P150): 통합·검증만. 결정적. 거래·집행 없음.
"""
from __future__ import annotations

# P141-150 운영 계층 모듈(안전 스캔 대상)
_OPS_MODULES = ("research_scheduler.py", "morning_briefing.py", "company_monitor.py",
                "strategy_health.py", "report_automation.py", "research_workspace.py",
                "research_outcome_tracker.py", "agent_performance.py", "ops_validation.py")


def validate_research_ops() -> dict:
    """v1.5 운영 조직 검증 — 7개 확인 + 완전 루프(결정적·읽기전용)."""
    checks = []

    # (1) 스케줄러 동작
    sched = _safe(lambda: __import__("jarvis.research_workflow.research_scheduler",
                                     fromlist=["plan_cycle"]).plan_cycle("daily"))
    checks.append({"check": "scheduler_works",
                   "ok": bool(sched and sched.get("tasks") and sched.get("auto_execution") is False),
                   "detail": f"tasks={len(sched.get('tasks', [])) if sched else 0}"})

    # (2) 에이전트가 연구 태스크 완료
    wf = _safe(lambda: __import__("jarvis.research_workflow.multi_agent_workflow", fromlist=["run"])
               .run("momentum in KR equities"))
    checks.append({"check": "agents_complete_research_tasks",
                   "ok": bool(wf and len(wf.get("stages", [])) >= 5 and wf.get("report")),
                   "detail": f"stages={len(wf.get('stages', [])) if wf else 0}"})

    # (3) 리포트 생성
    rep = _safe(lambda: __import__("jarvis.research_workflow.report_automation", fromlist=["generate"])
                .generate("daily_report", "Does momentum work?",
                          review=(wf or {}).get("review")))
    checks.append({"check": "reports_generated",
                   "ok": bool(rep and len(rep.get("report", {})) == 8 and rep.get("confidence")),
                   "detail": f"sections={len(rep.get('report', {})) if rep else 0}"})

    # (4) 지식 정확히 갱신 — learning_engine 프리뷰(기존 rmi_)
    learn = _safe(lambda: __import__("jarvis.research_workflow.learning_engine", fromlist=["learn"])
                  .learn(backtest={"strategy_name": "tsmom", "metrics": {"return": 0.1}}))
    checks.append({"check": "knowledge_updates_correctly",
                   "ok": bool(learn and learn.get("stored", {}).get("ledger") == "rmi_lessons"
                              and learn.get("committed") is False),
                   "detail": f"ledger={learn.get('stored', {}).get('ledger') if learn else None}"})

    # (5) 사람 검토 필수 유지 — ResearchOperationPlan 은 human_review_required, 그 외는 requires_human_review
    def _needs_human(x):
        return bool(x) and x.get("is_decision") is False and (
            x.get("requires_human_review") is True or x.get("human_review_required") is True)
    human_ok = all(_needs_human(x) for x in (sched, wf, rep))
    checks.append({"check": "human_review_required", "ok": human_ok, "detail": "human review flag set"})

    # (6) 중복 시스템 없음 — 원장 3개 + 운영 모듈이 원장에 직접 쓰지 않음
    from jarvis.research_workflow import ledger as wl
    no_dup = len(wl.ALL_LEDGERS) == 3 and _no_direct_ledger()
    checks.append({"check": "no_duplicate_systems", "ok": no_dup,
                   "detail": f"rwf_ledgers={len(wl.ALL_LEDGERS)}"})

    # (7) 안전 규칙 통과
    safety = ops_safety()
    checks.append({"check": "safety_rules_pass", "ok": safety["safe"], "detail": "AST scan"})

    all_ok = all(c["ok"] for c in checks)
    return {"version": "Jarvis Research OS v1.5 — Operational Research Firm",
            "loop": ["External Data", "Research Opportunity", "Agent Research", "Experiment",
                     "Validation", "Knowledge Update", "Future Research Improvement"],
            "checks": checks, "operational": all_ok, "safety": safety,
            "capabilities": ["Observe markets", "Monitor companies", "Track strategies",
                             "Assign research tasks", "Generate reports", "Measure research quality",
                             "Improve institutional knowledge"],
            "human_authority": "Human remains the only decision maker.",
            "is_advisory": True, "is_decision": False,
            "note": ("v1.5 운영 검증(읽기전용) — 스케줄러·에이전트·리포트·지식·사람검토·무중복·안전. "
                     "새 DB/원장/메모리/실행엔진 없음. 거래·집행·자본배분 없음.")}


def _no_direct_ledger() -> bool:
    """운영 모듈이 원장 쓰기 프리미티브(state_path)를 직접 호출하지 않는지 AST 확인."""
    import ast
    import pathlib
    here = pathlib.Path(__file__).resolve().parent
    for f in _OPS_MODULES:
        for node in ast.walk(ast.parse((here / f).read_text())):
            if isinstance(node, ast.Call):
                fn = node.func
                if (isinstance(fn, ast.Name) and fn.id == "state_path") or \
                   (isinstance(fn, ast.Attribute) and fn.attr == "state_path"):
                    return False
    return True


def ops_safety() -> dict:
    """안전(결정적) — 운영 모듈에 금지 동작/브로커/새 원장 없음을 AST 로 확인."""
    import ast
    import pathlib

    here = pathlib.Path(__file__).resolve().parent
    forbidden_defs = {"execute", "trade", "deploy", "allocate", "approve", "place_order"}
    forbidden_imports = ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
                         "jarvis.live_trading", "jarvis.portfolio_execution")
    violations = []
    for f in _OPS_MODULES:
        p = here / f
        if not p.exists():
            continue
        for node in ast.walk(ast.parse(p.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module and \
                    any(node.module.startswith(b) for b in forbidden_imports):
                violations.append({"file": f, "kind": "import", "detail": node.module})
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in forbidden_defs:
                violations.append({"file": f, "kind": "def", "detail": node.name})
    from jarvis.research_workflow import ledger as wl
    return {"safe": not violations and len(wl.ALL_LEDGERS) == 3, "violations": violations,
            "no_new_ledger": len(wl.ALL_LEDGERS) == 3,
            "checks": ["no new database/ledger/memory store/execution engine",
                       "no execute/trade/place_order/allocate/approve", "no broker/capital management",
                       "advisory only"],
            "is_advisory": True, "is_decision": False}


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


# ── P206 Deprecated (삭제 아님, ≥1 릴리스 유지) — 외부 직접 호출 대신 governance.validate(domain="operations") ──
__deprecated__ = {"since": "P206", "use": "governance.validate(domain='operations')", "domain": "operations"}
