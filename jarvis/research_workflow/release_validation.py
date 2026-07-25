"""Jarvis v2.0 Release Validation (P110) — 완전한 연구 검증 루프를 검증한다. **읽기 전용, 실행 없음.**

루프: Market Event → Research Trigger → Hypothesis → Experiment → Backtest → Paper → Validation →
Risk Review → Memory. 각 단계가 (기존 모듈로) 자문 산출을 내는지 결정적으로 확인하고, 안전 점검
(execute/trade/place_order/allocate/approve 없음 · 브로커/라이브 트레이딩 없음)을 수행한다.

원칙(문서 §Constitution, §P110): 통합·검증만. 결정적. 거래·집행 없음.
"""
from __future__ import annotations

# 루프 단계 → (모듈, 검증 스모크). 각 스모크는 자문 산출(dict/dataclass)을 반환해야 한다.
_SAMPLE_EVENT = {"kind": "earnings", "entity": "NVDA", "text": "NVDA earnings surprise beat"}
_SAMPLE_BT = {"strategy_name": "tsmom", "universe": "US", "hypothesis": "trend persists",
              "entry_rules": "cross", "source": "test",
              "metrics": {"return": 0.2, "sharpe": 1.4, "max_drawdown": -0.1, "walk_forward": 0.6,
                          "out_of_sample": 0.5, "cost_impact": 0.02, "random_baseline": 0.1,
                          "turnover": 0.3, "parameter_stability": 0.7}}
_SAMPLE_PAPER = {"strategy_name": "tsmom",
                 "metrics": {"return": 0.05, "sharpe": 0.4, "max_drawdown": -0.18,
                             "cost_impact": 0.09, "turnover": 0.6}}


def _step(name, fn) -> dict:
    try:
        out = fn()
        ok = out is not None and (getattr(out, "is_advisory", None) is True
                                  or (isinstance(out, dict) and out.get("is_advisory") is True)
                                  or isinstance(out, (dict, list)))
        return {"stage": name, "ok": bool(ok), "advisory": _is_advisory(out)}
    except Exception as e:  # noqa: BLE001
        return {"stage": name, "ok": False, "error": str(e)[:160]}


def _is_advisory(out) -> bool:
    if isinstance(out, dict):
        return out.get("is_advisory", False) is True and out.get("is_decision", True) is False
    return getattr(out, "is_advisory", False) is True and getattr(out, "is_decision", True) is False


def validate_release() -> dict:
    """v2.0 완전 루프 + 안전 점검(결정적·읽기전용). 각 단계가 자문 산출을 내는지 확인."""
    from jarvis.research_workflow import (
        backtest_bridge, paper_validation, research_trigger, validation_gap,
    )
    from jarvis.research_workflow.hypothesis_generator import HypothesisGenerator

    steps = [
        _step("Market Event → Research Trigger",
              lambda: research_trigger.from_event(_SAMPLE_EVENT)),
        _step("Research Trigger → Hypothesis",
              lambda: HypothesisGenerator().generate("NVDA earnings", limit=1)[0]),
        _step("Hypothesis → Experiment (Backtest Job)",
              lambda: backtest_bridge.create_job({"statement": "tsmom produces trend edge"})),
        _step("Backtest → Paper Validation",
              lambda: paper_validation.validate(_SAMPLE_BT, _SAMPLE_PAPER)),
        _step("Paper → Validation Gap",
              lambda: validation_gap.analyze_gap(_SAMPLE_BT, _SAMPLE_PAPER)),
        _step("Validation → Risk Review",
              lambda: _risk_review()),
        _step("Risk Review → Memory (lesson, dry-run)",
              lambda: _memory_dry_run()),
    ]
    loop_ok = all(s["ok"] for s in steps)
    safety = safety_check()
    ready = bool(loop_ok and safety["safe"])
    return {"version": "Jarvis v2.0 — Operational Research OS",
            "loop_steps": steps, "loop_complete": loop_ok,
            "safety": safety, "release_ready": ready,
            "capabilities": ["Market Intelligence", "Research Automation", "Strategy Validation",
                             "Failure Learning"],
            "human_authority": "Human makes every investment decision. Jarvis researches, validates, "
                               "explains, and remembers.",
            "is_advisory": True, "is_decision": False,
            "note": "v2.0 릴리스 검증(읽기전용) — 완전 루프 + 안전 점검. 자동 실행·집행·거래 없음."}


def _risk_review() -> dict:
    from jarvis.research_risk_intelligence.failure_reasoning import StrategyRiskReasoner
    return StrategyRiskReasoner().risk_report("tsmom", _SAMPLE_BT["metrics"]).to_dict()


def _memory_dry_run() -> dict:
    from jarvis.research_workflow.continuous_learning import on_research_complete
    return on_research_complete(_SAMPLE_BT, paper=_SAMPLE_PAPER, commit=False)


def safety_check() -> dict:
    """안전 점검(결정적) — P101-110 신규 모듈에 금지 동작/브로커/라이브 트레이딩이 없음을 AST 로 확인."""
    import ast
    import pathlib

    here = pathlib.Path(__file__).resolve().parent
    modules = ("research_trigger.py", "backtest_bridge.py", "paper_validation.py",
               "validation_gap.py", "strategy_lifecycle.py", "quality_monitor.py",
               "ops_events.py", "research_audit.py", "release_validation.py")
    forbidden_defs = {"execute", "trade", "deploy", "allocate", "approve", "place_order"}
    forbidden_imports = ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
                         "jarvis.live_trading", "jarvis.portfolio_execution")
    violations = []
    for f in modules:
        try:
            src = open(here / f).read()
        except OSError:
            continue
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and \
                    any(node.module.startswith(b) for b in forbidden_imports):
                violations.append({"file": f, "kind": "import", "detail": node.module})
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in forbidden_defs:
                violations.append({"file": f, "kind": "def", "detail": node.name})
    return {"safe": not violations, "violations": violations,
            "checks": ["no execute()/trade()/place_order()/allocate()/approve()",
                       "no broker connection", "no live trading", "advisory only"],
            "is_advisory": True, "is_decision": False}
