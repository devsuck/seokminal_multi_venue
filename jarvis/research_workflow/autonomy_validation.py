"""Autonomous Research Validation (P180) — P171-180 지능 강화가 안전·재사용 규칙을 지켰는지 검증한다. **읽기 전용.**

검증: 실행엔진 없음 · 브로커 import 없음 · trade 함수 없음 · 자본배분 없음 · 자율 승인 없음 ·
새 DB/원장 없음 · 중복 엔진 없음 · 기존 아키텍처 재사용 · 자문 전용 · 사람 체크포인트 보존.
산출: 정확한 재사용 분석 · 확장된 모듈 · 중복 로직(0이어야 함) · 아키텍처 영향 · 남은 한계.

**재사용**: governance(P168)·ledger(원장 수). 새 엔진/저장소 없음.
원칙(문서 §Constitution, §P180): 통합·검증만 · 결정적 · 자문 전용 · 거래·집행 없음.
"""
from __future__ import annotations

import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"

# P171-180 강화 모듈
_MODULES = ("creative_hypothesis.py", "research_search.py", "continuous_queue.py",
            "experiment_prioritization.py", "research_expansion.py", "self_reflection.py",
            "research_planning.py", "collaborative_research.py", "productivity_optimization.py",
            "autonomy_validation.py")
_FORBIDDEN_IMPORT_PREFIX = ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
                            "jarvis.live_trading", "jarvis.portfolio_execution")
_FORBIDDEN_DEFS = ("execute", "trade", "deploy", "allocate", "approve", "place_order",
                   "deploy_strategy")
# 재사용해야 할 기존 모듈(존재 확인용 — 조율 대상)
_EXISTING = ("hypothesis_generator", "research_prioritizer", "research_similarity",
             "semantic_recall", "conflict_detection", "opportunity_discovery", "regime",
             "macro_intelligence", "sector_intelligence", "knowledge_graph_upgrade",
             "research_scheduler", "multi_agent_workflow", "learning_engine",
             "research_ingestion", "knowledge_quality", "operational_metrics", "research_search",
             "continuous_queue", "experiment_prioritization")


def _reused_modules(tree) -> set:
    """AST — ImportFrom + __import__("...") 문자열에서 참조하는 기존 모듈명 수집(재사용 증거)."""
    reused = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            reused.add(node.module.split(".")[-1])
            if "research_ingestion" in node.module:
                reused.add("research_ingestion")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "__import__":
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    reused.add(arg.value.split(".")[-1])
                    if "research_ingestion" in arg.value:
                        reused.add("research_ingestion")
    return reused


def _defines_new_ledger_or_engine(tree) -> list:
    """중복 로직 탐지 — 새 원장 append 또는 새 *Engine 클래스 정의(있으면 중복)."""
    dup = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name.endswith("Engine"):
            dup.append(f"class {node.name}")
        if isinstance(node, ast.FunctionDef) and node.name.startswith("append_"):
            dup.append(f"def {node.name}")
    return dup


def autonomy_safety() -> dict:
    """P171-180 모듈 AST 안전 스캔 — 금지 import/def, 모델 누출, 중복 엔진/원장. 결정적."""
    violations, reuse_by_module, dup_logic = [], {}, []
    for f in _MODULES:
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
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in _FORBIDDEN_DEFS:
                    violations.append(f"{f}: 금지 def {node.name}")
        reuse_by_module[f] = sorted(_reused_modules(tree) & set(_EXISTING))
        dup_logic += [f"{f}: {d}" for d in _defines_new_ledger_or_engine(tree)]
    return {"passed": not violations and not dup_logic,
            "violations": violations, "duplicated_logic": dup_logic,
            "reuse_by_module": reuse_by_module,
            "is_advisory": True, "is_decision": False}


def _ledger_count() -> int:
    from jarvis.research_workflow import ledger as wl
    return len(wl.ALL_LEDGERS)


def _governance():
    try:
        from jarvis.research_workflow.governance import build_governance
        return build_governance()
    except Exception:  # noqa: BLE001
        return {"passed": False, "governance": "UNKNOWN"}


def _capability_smoke() -> list:
    """각 강화 능력이 자문 계약(is_decision=False)을 지키는지 스모크(결정적·읽기전용)."""
    checks = []
    probes = [
        ("P171 creative_hypothesis", lambda: __import__(
            "jarvis.research_workflow.creative_hypothesis", fromlist=["discover_hypotheses"]
        ).discover_hypotheses("momentum", limit=4)),
        ("P172 research_search", lambda: __import__(
            "jarvis.research_workflow.research_search", fromlist=["build_search_space"]
        ).build_search_space("momentum edge", top_k=5)),
        ("P173 continuous_queue", lambda: __import__(
            "jarvis.research_workflow.continuous_queue", fromlist=["build_continuous_queue"]
        ).build_continuous_queue(topic="momentum")),
        ("P174 experiment_prioritization", lambda: __import__(
            "jarvis.research_workflow.experiment_prioritization", fromlist=["prioritize_experiments"]
        ).prioritize_experiments(topic="momentum", limit=4)),
        ("P175 research_expansion", lambda: __import__(
            "jarvis.research_workflow.research_expansion", fromlist=["expand_research"]
        ).expand_research("momentum edge", top_k=6)),
        ("P176 self_reflection", lambda: __import__(
            "jarvis.research_workflow.self_reflection", fromlist=["reflect_on_cycle"]
        ).reflect_on_cycle()),
        ("P177 research_planning", lambda: __import__(
            "jarvis.research_workflow.research_planning", fromlist=["build_research_plan"]
        ).build_research_plan(topic="momentum")),
        ("P178 collaborative_research", lambda: __import__(
            "jarvis.research_workflow.collaborative_research", fromlist=["run_collaborative_research"]
        ).run_collaborative_research("Does momentum work?")),
        ("P179 productivity_optimization", lambda: __import__(
            "jarvis.research_workflow.productivity_optimization", fromlist=["build_productivity_report"]
        ).build_productivity_report()),
    ]
    for name, fn in probes:
        try:
            r = fn()
            ok = isinstance(r, dict) and r.get("is_decision") is False and r.get("is_advisory") is True
            checks.append({"capability": name, "ok": bool(ok),
                           "advisory": r.get("is_advisory"), "is_decision": r.get("is_decision")})
        except Exception as e:  # noqa: BLE001
            checks.append({"capability": name, "ok": False, "error": str(e)[:80]})
    return checks


def validate_autonomy() -> dict:
    """P171-180 종합 검증 — 안전 스캔 + 재사용 감사 + 거버넌스 + 원장수 + 능력 스모크. 결정적·읽기전용."""
    safety = autonomy_safety()
    gov = _governance()
    ledgers = _ledger_count()
    caps = _capability_smoke()

    all_reused = sorted({m for mods in safety["reuse_by_module"].values() for m in mods})
    checks = [
        {"check": "no_execution_engine", "ok": not any("execution" in v for v in safety["violations"])},
        {"check": "no_broker_imports", "ok": not any("broker" in v for v in safety["violations"])},
        {"check": "no_trade_functions", "ok": not any("def trade" in v or "def execute" in v
                                                      or "place_order" in v for v in safety["violations"])},
        {"check": "no_capital_allocation", "ok": not any("allocate" in v for v in safety["violations"])},
        {"check": "no_autonomous_approval", "ok": not any("approve" in v for v in safety["violations"])},
        {"check": "no_new_ledger", "ok": ledgers == 3, "detail": f"ALL_LEDGERS={ledgers}"},
        {"check": "no_duplicated_logic", "ok": not safety["duplicated_logic"],
         "detail": f"{len(safety['duplicated_logic'])} found"},
        {"check": "existing_architecture_reused", "ok": len(all_reused) >= 10,
         "detail": f"{len(all_reused)} existing modules composed"},
        {"check": "advisory_only", "ok": all(c["ok"] for c in caps)},
        {"check": "governance_compliant", "ok": bool(gov.get("passed"))},
        {"check": "no_model_leak", "ok": not any("누출" in v for v in safety["violations"])},
    ]
    validated = safety["passed"] and all(c["ok"] for c in checks)

    return {"validated": validated, "checks": checks,
            "safety": safety,
            "reuse_analysis": {"existing_modules_reused": all_reused,
                               "reuse_count": len(all_reused),
                               "by_module": safety["reuse_by_module"]},
            "modules_extended": ["hypothesis_generator", "research_prioritizer", "research_scheduler",
                                 "multi_agent_workflow", "research_similarity", "learning_engine"],
            "duplicated_logic": safety["duplicated_logic"],
            "architecture_impact": ("동결 아키텍처 유지 — 새 패키지/엔진/원장/DB 없음. "
                                    "10개 강화 모듈은 기존 엔진 조율만."),
            "capability_smoke": caps,
            "remaining_limitations": [
                "가설 생성은 결정론적 다중원 조합 — LLM 창발 아님(재현성 우선).",
                "연구 자동 실행 없음 — 백테스트는 사람 체크포인트에서만.",
                "커버리지/갭 지표는 축적된 지식그래프에 의존.",
                "매크로/레짐 라벨은 주입 값 없으면 UNKNOWN(정직).",
            ],
            "future_recommendations": [
                "데이터 소스 확대로 커버리지·갭 정확도 향상.",
                "완전 검증 세트(cost/vol/stability) 백필로 판정 품질 상향.",
                "협업 액션을 사람 검토 결과와 대조해 우선순위 가중 보정.",
            ],
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Autonomous Research Validation(읽기전용) — P171-180 안전·재사용 검증. "
                     "새 아키텍처 없음, 자문 전용, 사람 체크포인트 보존. 모든 결정은 사람.")}


# ── P206 Deprecated (삭제 아님, ≥1 릴리스 유지) — 외부 직접 호출 대신 governance.validate(domain="safety") ──
__deprecated__ = {"since": "P206", "use": "governance.validate(domain='safety')", "domain": "safety"}
