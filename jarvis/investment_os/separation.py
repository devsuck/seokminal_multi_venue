"""Architectural Separation Validation — Research OS / Investment OS / Execution 완전 분리 검증. **읽기 전용.**

검증(AST + 불변식):
  ① Research OS 는 Investment OS 를 import 하지 않는다(연구는 투자를 모른다).
  ② Investment OS 는 Research OS 원장에 쓰지 않는다(읽기전용 소비만 — Research 무변경).
  ③ Research OS 는 거래를 실행하지 않는다(실행 def/브로커 import 없음).
  ④ Investment OS 도 실제 주문을 라우팅하지 않는다(execute/place_order/trade def 없음).
  ⑤ AUTO_EXECUTION은 승인 아티팩트 없이는 False로 취급(존재해도 사람 승인 기록
     없으면 invariant 실패) · 사람 승인 필수 · 4 게이트 우회 불가.
"""
from __future__ import annotations

import ast
import pathlib

_IOS_DIR = pathlib.Path(__file__).resolve().parent
_RESEARCH_DIR = _IOS_DIR.parent / "research_workflow"
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"
_EXEC_DEFS = ("execute", "trade", "place_order", "route_order", "send_order", "submit_order",
              "allocate", "deploy_strategy")
_BROKER_PREFIX = ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
                  "jarvis.live_trading", "jarvis.portfolio_execution")
# Research OS 원장 쓰기 함수(Investment OS 가 호출하면 위반)
_RESEARCH_WRITE = ("append_lesson", "append_ingestion", "append_run", "record_lesson",
                   "record_failure", "record_success", "record_run")


def _py_files(d: pathlib.Path):
    return sorted(p for p in d.glob("*.py") if p.name != "__init__.py") if d.exists() else []


def _imports(tree) -> set:
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "__import__":
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    mods.add(arg.value)
    return mods


def _calls(tree) -> set:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute):
                names.add(f.attr)
            elif isinstance(f, ast.Name):
                names.add(f.id)
    return names


def _defs(tree) -> set:
    return {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def validate_separation() -> dict:
    """3계층 분리 + 실행 불변식 검증(결정적·읽기전용)."""
    violations = []

    # ① Research OS 는 investment_os 를 import 하지 않는다
    for p in _py_files(_RESEARCH_DIR):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        if any("investment_os" in m for m in _imports(tree)):
            violations.append(f"research::{p.name} imports investment_os (연구가 투자를 알면 안 됨)")

    # ②④⑤ Investment OS 검사
    ios_files = _py_files(_IOS_DIR)
    for p in ios_files:
        src = p.read_text(encoding="utf-8")
        if MODEL_LEAK_TOKEN in src.lower():
            violations.append(f"investment::{p.name} 모델 식별자 누출")
        tree = ast.parse(src)
        # ② Research 원장 쓰기 호출 금지
        for w in (_calls(tree) & set(_RESEARCH_WRITE)):
            violations.append(f"investment::{p.name} calls research write '{w}' (Research 변경 금지)")
        # ④ 실제 주문/실행 def 금지
        for d in (_defs(tree) & set(_EXEC_DEFS)):
            violations.append(f"investment::{p.name} defines execution '{d}'")
        # 브로커/실행 import 금지
        for m in _imports(tree):
            if any(str(m).startswith(b) for b in _BROKER_PREFIX):
                violations.append(f"investment::{p.name} imports broker '{m}'")

    # ⑤ 실행 불변식
    import os as _os
    from jarvis.config import state_path as _state_path
    from jarvis.investment_os import AUTO_EXECUTION_ENABLED, HUMAN_APPROVAL_MANDATORY, MANDATORY_GATES
    # 승인 아티팩트 존재 여부만 확인(파일 존재 체크) — jarvis.execution import는
    # _BROKER_PREFIX가 investment_os/*.py에서 금지하므로 여기선 절대 안 쓴다.
    # 기록은 jarvis.execution.arm.record_auto_execution_approval()(사람 ADMIN 전용)만 한다.
    _auto_exec_approved = _os.path.exists(_state_path("auto_execution_approval.json"))
    invariants = [
        {"check": "auto_execution_disabled_or_human_approved",
         "ok": AUTO_EXECUTION_ENABLED is False or _auto_exec_approved},
        {"check": "human_approval_mandatory", "ok": HUMAN_APPROVAL_MANDATORY is True},
        {"check": "four_mandatory_gates", "ok": set(MANDATORY_GATES) == {"risk", "compliance", "portfolio", "kill_switch"}},
        {"check": "research_never_imports_investment",
         "ok": not any("imports investment_os" in v for v in violations)},
        {"check": "investment_never_writes_research",
         "ok": not any("research write" in v for v in violations)},
        {"check": "no_execution_defs_or_brokers",
         "ok": not any("execution" in v or "broker" in v for v in violations)},
    ]
    separated = not violations and all(i["ok"] for i in invariants)
    return {"separated": separated, "violations": violations, "invariants": invariants,
            "layers": ["Research OS (지식 생산)", "Investment OS (지식 소비·추천)", "Execution (영구 비활성)"],
            "auto_execution_enabled": AUTO_EXECUTION_ENABLED,
            "auto_execution_approved": _auto_exec_approved,
            "investment_files_scanned": len(ios_files),
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Architectural Separation(읽기전용) — Research/Investment/Execution 완전 분리. "
                     "연구는 투자를 모름, 투자는 연구를 안 바꿈, 둘 다 실행 안 함. "
                     "Investment OS엔 execute() 자체가 없어 AUTO_EXECUTION_ENABLED는 실질 게이트 아님 — "
                     "진짜 실행 게이트는 jarvis.config.AUTONOMY_LEVEL/MIN_LIVE_LEVEL.")}
