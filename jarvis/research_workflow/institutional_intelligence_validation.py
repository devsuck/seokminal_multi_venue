"""Institutional Intelligence Validation (P160) — 기관 인텔리전스 계층을 검증한다. **읽기 전용, 실행 없음.**

검증: (1)데이터소스 연결 (2)섹터 컨텍스트 (3)매크로 컨텍스트 (4)기업 그래프 (5)연구 컨텍스트 결합
(6)품질 스코어링 (7)중복 시스템 없음. + 안전(금지 동작/브로커/새 원장 없음).

원칙(문서 §Constitution, §P160): 통합·검증만. 결정적. 거래·집행 없음.
"""
from __future__ import annotations

_MODULES = ("data_production.py", "sector_intelligence.py", "macro_intelligence.py",
            "company_intelligence.py", "research_context_engine.py", "cross_asset_intelligence.py",
            "institutional_memory_expansion.py", "intelligence_quality.py",
            "institutional_intelligence_validation.py")


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def validate_intelligence() -> dict:
    """기관 인텔리전스 7개 확인 + 안전(결정적·읽기전용)."""
    checks = []

    # (1) 데이터 소스 연결
    dp = _safe(lambda: __import__("jarvis.research_workflow.data_production",
                                  fromlist=["build_data_production"]).build_data_production())
    checks.append({"check": "data_sources_connect", "ok": bool(dp and dp.get("count", 0) > 0),
                   "detail": f"providers={dp.get('count') if dp else 0}"})

    # (2) 섹터 컨텍스트
    sec = _safe(lambda: __import__("jarvis.research_workflow.sector_intelligence",
                                   fromlist=["analyze_sector"]).analyze_sector("semiconductor"))
    checks.append({"check": "sector_context_generated",
                   "ok": bool(sec and sec.get("key_entities") and "research_questions" in sec),
                   "detail": f"entities={len(sec.get('key_entities', [])) if sec else 0}"})

    # (3) 매크로 컨텍스트
    mac = _safe(lambda: __import__("jarvis.research_workflow.macro_intelligence",
                                   fromlist=["build_macro_context"])
                .build_macro_context(indicators={"fed_funds": 5.0, "cpi": 3.5}))
    checks.append({"check": "macro_context_generated",
                   "ok": bool(mac and mac.get("macro_state") and "indicators" in mac),
                   "detail": f"state={mac.get('macro_state') if mac else None}"})

    # (4) 기업 그래프
    co = _safe(lambda: __import__("jarvis.research_workflow.company_intelligence",
                                  fromlist=["analyze_company"]).analyze_company("TSMC"))
    checks.append({"check": "company_graph_works",
                   "ok": bool(co and "relationships" in co and co.get("is_trade_signal") is False),
                   "detail": f"rels={list(co.get('relationships', {})) if co else []}"})

    # (5) 연구 컨텍스트 결합
    ctx = _safe(lambda: __import__("jarvis.research_workflow.research_context_engine",
                                   fromlist=["build_research_context"])
                .build_research_context("Does momentum work in semiconductor?", sector="semiconductor",
                                        entity="TSMC"))
    checks.append({"check": "research_context_combines",
                   "ok": bool(ctx and ctx.get("is_context_package") and len(ctx.get("package", {})) == 8),
                   "detail": f"sections={len(ctx.get('package', {})) if ctx else 0}"})

    # (6) 품질 스코어링
    iq = _safe(lambda: __import__("jarvis.research_workflow.intelligence_quality",
                                  fromlist=["score_intelligence"]).score_intelligence(topic="momentum"))
    checks.append({"check": "quality_scoring_works",
                   "ok": bool(iq and iq.get("confidence") in ("HIGH", "MEDIUM", "LOW")
                              and len(iq.get("dimensions", {})) == 5),
                   "detail": f"confidence={iq.get('confidence') if iq else None}"})

    # (7) 중복 시스템 없음 — 원장 3개 + 직접 원장 쓰기 없음
    from jarvis.research_workflow import ledger as wl
    no_dup = len(wl.ALL_LEDGERS) == 3 and _no_direct_ledger()
    checks.append({"check": "no_duplicate_systems", "ok": no_dup,
                   "detail": f"rwf_ledgers={len(wl.ALL_LEDGERS)}"})

    safety = intelligence_safety()
    all_ok = all(c["ok"] for c in checks) and safety["safe"]
    return {"layer": "Institutional Intelligence Platform (P151-160)",
            "checks": checks, "validated": all_ok, "safety": safety,
            "capabilities": ["Understand market environment", "Understand sectors", "Understand companies",
                             "Connect macro conditions", "Retrieve historical knowledge",
                             "Build complete research context", "Evaluate information quality"],
            "is_advisory": True, "is_decision": False,
            "note": ("기관 인텔리전스 검증(읽기전용) — 데이터·섹터·매크로·기업·컨텍스트·품질·무중복. "
                     "새 DB/원장/메모리/엔진 없음. 거래·집행 없음.")}


def _no_direct_ledger() -> bool:
    import ast
    import pathlib
    here = pathlib.Path(__file__).resolve().parent
    for f in _MODULES:
        for node in ast.walk(ast.parse((here / f).read_text())):
            if isinstance(node, ast.Call):
                fn = node.func
                if (isinstance(fn, ast.Name) and fn.id == "state_path") or \
                   (isinstance(fn, ast.Attribute) and fn.attr == "state_path"):
                    return False
    return True


def intelligence_safety() -> dict:
    """안전(결정적) — 인텔리전스 모듈에 금지 동작/브로커/새 원장 없음을 AST 로 확인."""
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
        for node in ast.walk(ast.parse(p.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module and \
                    any(node.module.startswith(b) for b in forbidden_imports):
                violations.append({"file": f, "kind": "import", "detail": node.module})
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in forbidden_defs:
                violations.append({"file": f, "kind": "def", "detail": node.name})
    from jarvis.research_workflow import ledger as wl
    return {"safe": not violations and len(wl.ALL_LEDGERS) == 3, "violations": violations,
            "no_new_ledger": len(wl.ALL_LEDGERS) == 3,
            "checks": ["no new database/ledger/vector db/memory store/execution engine",
                       "no execute/trade/place_order/allocate/approve", "no broker/capital deployment",
                       "advisory only, requires_human_review"],
            "is_advisory": True, "is_decision": False}


# ── P206 Deprecated (삭제 아님, ≥1 릴리스 유지) — 외부 직접 호출 대신 governance.validate(domain="research") ──
__deprecated__ = {"since": "P206", "use": "governance.validate(domain='research')", "domain": "research"}
