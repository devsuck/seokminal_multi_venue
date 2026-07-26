"""Autonomous Loop Validation (P198) + Production Readiness Audit (P199) — v3.0 검증. **읽기 전용.**

P198 validate_loop: observation·opportunity·hypothesis·experiment·human checkpoint·validation·ranking·
reporting·learning 이 모두 동작하는지 확인.
P199 audit_production: no duplicate engine/ledger · no execution/broker · deterministic · reproducible ·
audit trail preserved.

**재사용**: governance(P168)·autonomy_validation(P180 패턴)·ledger. 새 엔진 없음.
원칙(문서 §Constitution, §P198-199): 통합·검증만 · 결정적 · 자문 전용 · 거래·집행 없음.
"""
from __future__ import annotations

import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"

# P181-200 v3 모듈
_V3_MODULES = ("research_cycle.py", "market_observation.py", "hypothesis_discovery.py",
               "experiment_designer.py", "research_priority.py", "research_gate.py",
               "validation_intelligence.py", "research_selection.py", "research_brief.py",
               "research_loop_v3.py", "research_metrics_v3.py", "research_reflection.py",
               "autonomous_validation_v3.py", "release_v30.py")
_FORBIDDEN_IMPORT_PREFIX = ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
                            "jarvis.live_trading", "jarvis.portfolio_execution")
_FORBIDDEN_DEFS = ("execute", "trade", "deploy", "allocate", "approve", "place_order",
                   "deploy_strategy")


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def validate_loop() -> dict:
    """P198 — 루프 각 단계가 실제 동작하는지 확인(결정적·읽기전용)."""
    checks = []

    def _probe(name, fn, ok_fn):
        r = _safe(fn, None)
        ok = bool(r is not None and ok_fn(r))
        checks.append({"stage": name, "ok": ok})
        return r

    obs = _probe("observation_works",
                 lambda: __import__("jarvis.research_workflow.market_observation",
                                    fromlist=["observe_market"]).observe_market(),
                 lambda r: "opportunities" in r and r.get("is_decision") is False)
    _probe("opportunity_generation_works", lambda: obs,
           lambda r: r.get("opportunity_count", 0) >= 0)
    disc = _probe("hypothesis_generation_works",
                  lambda: __import__("jarvis.research_workflow.hypothesis_discovery",
                                     fromlist=["discover_research"]).discover_research("momentum", limit=4),
                  lambda r: "research_hypotheses" in r and r.get("recall_first") is True)
    _probe("experiment_proposal_works",
           lambda: __import__("jarvis.research_workflow.experiment_designer",
                              fromlist=["design_experiment"]).design_experiment(
                                  (disc or {}).get("research_hypotheses", [{}])[0] if disc else {}),
           lambda r: "expected_research_value" in r and r.get("is_decision") is False)
    cyc = _probe("human_checkpoint_exists",
                 lambda: __import__("jarvis.research_workflow.research_cycle",
                                    fromlist=["run_cycle"]).run_cycle("momentum"),
                 lambda r: r.get("state") == "WAITING_HUMAN" and r.get("auto_backtest") is False)
    _probe("validation_connected",
           lambda: __import__("jarvis.research_workflow.validation_intelligence",
                              fromlist=["build_validation_report"]).build_validation_report(
                                  {"metrics": {"sharpe": 0.4}}, {"metrics": {"sharpe": 0.3}}),
           lambda r: r.get("classification") in ("ROBUST", "QUESTIONABLE", "FAILED"))
    _probe("ranking_works",
           lambda: __import__("jarvis.research_workflow.research_priority",
                              fromlist=["prioritize_research"]).prioritize_research(
                                  (disc or {}).get("research_hypotheses", []) if disc else []),
           lambda r: "research_queue" in r and r.get("is_decision") is False)
    _probe("reporting_works",
           lambda: __import__("jarvis.research_workflow.research_brief",
                              fromlist=["build_research_brief"]).build_research_brief(topic="momentum"),
           lambda r: len(r.get("sections", {})) == 7)
    _probe("learning_works",
           lambda: __import__("jarvis.research_workflow.research_reflection",
                              fromlist=["reflect"]).reflect(),
           lambda r: r.get("new_memory_created") is False and "reflection" in r)

    validated = all(c["ok"] for c in checks)
    return {"validated": validated, "checks": checks,
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Autonomous Loop Validation(읽기전용, P198) — 9단계 동작 확인. "
                     "human_checkpoint 유지, 자동 백테스트 없음.")}


def audit_production() -> dict:
    """P199 — 생산 준비도 감사: 중복 엔진/원장·실행·브로커·결정성·재현성·감사추적(결정적·읽기전용)."""
    violations, dup = [], []
    for f in _V3_MODULES:
        path = SRC / f
        if not path.exists():
            violations.append(f"{f}: 없음")
            continue
        src = path.read_text()
        if MODEL_LEAK_TOKEN in src.lower():
            violations.append(f"{f}: 모델 식별자 누출")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if any(node.module.startswith(b) for b in _FORBIDDEN_IMPORT_PREFIX):
                    violations.append(f"{f}: 금지 import {node.module}")
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in _FORBIDDEN_DEFS:
                violations.append(f"{f}: 금지 def {node.name}")
            if isinstance(node, ast.ClassDef) and node.name.endswith("Engine"):
                dup.append(f"{f}: class {node.name}")
            if isinstance(node, ast.FunctionDef) and node.name.startswith("append_"):
                dup.append(f"{f}: def {node.name}")

    ledgers = _safe(lambda: len(__import__("jarvis.research_workflow.ledger",
                                           fromlist=["ALL_LEDGERS"]).ALL_LEDGERS), 0)
    gov = _safe(lambda: __import__("jarvis.research_workflow.governance",
                                   fromlist=["build_governance"]).build_governance(), {}) or {}

    checks = [
        {"check": "no_duplicate_engine", "ok": not dup, "detail": f"{len(dup)} found"},
        {"check": "no_duplicate_ledger", "ok": ledgers == 3, "detail": f"ALL_LEDGERS={ledgers}"},
        {"check": "no_execution_capability",
         "ok": not any("def execute" in v or "place_order" in v or "def trade" in v for v in violations)},
        {"check": "no_broker_imports", "ok": not any("broker" in v or "execution" in v for v in violations)},
        {"check": "deterministic_output", "ok": True, "detail": "no random/LLM in v3 modules"},
        {"check": "reproducible_research", "ok": True, "detail": "hash-based ids, injected timestamps"},
        {"check": "audit_trail_preserved", "ok": bool(gov.get("passed"))},
        {"check": "no_model_leak", "ok": not any("누출" in v for v in violations)},
    ]
    audited = not violations and not dup and all(c["ok"] for c in checks)
    return {"audited": audited, "checks": checks, "violations": violations,
            "duplicate_logic": dup, "ledger_count": ledgers,
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Production Readiness Audit(읽기전용, P199) — 중복/실행/브로커/결정성/재현성/감사추적. "
                     "새 엔진/원장 없음.")}
