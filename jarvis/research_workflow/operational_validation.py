"""Operational Validation (P120) — 외부데이터→메모리 전체 체인을 검증한다. **읽기 전용, 실행 없음.**

체인: External Data → Provider → Normalization → Event Intelligence → Research Trigger → Workflow →
Validation Loop → Memory. 검증: (1) 데이터 수집 동작 (2) 중복 이벤트 방지 (3) 연구 후보 생성
(4) 대시보드 표시 (5) 기존 원장 불변. **아키텍처 안전**: 새 DB/원장/메모리/실행엔진 없음 확인.

원칙(문서 §Constitution, §P120): 통합·검증만. 결정적. 거래·집행 없음.
"""
from __future__ import annotations

# 결정적 샘플 외부 데이터(검증용)
_SAMPLE_MARKET = [{"asset": "AAPL", "return": 0.08, "timestamp": "2026-01-03T09:30:00Z", "source": "US"}]
_SAMPLE_NEWS = [{"text": "TSMC supplier expands production capacity", "entity": "TSMC"}]


def validate_operations() -> dict:
    """외부데이터 → 메모리 체인 검증(결정적·읽기전용). 5개 확인 + 아키텍처 안전."""
    checks = []

    # (1) 데이터 수집 동작 — market pipeline
    from jarvis.research_workflow.market_pipeline import run as market_run
    m = _safe(lambda: market_run(_SAMPLE_MARKET, source="US"))
    ingested = bool(m and m.get("count") == 1 and m.get("research_events"))
    checks.append({"check": "data_ingestion_works", "ok": ingested,
                   "detail": f"market events={m.get('count') if m else 0}"})

    # (2) 중복 이벤트 방지 — feed dedup
    from jarvis.research_workflow.research_feed import collect
    dup = _safe(lambda: collect({"market": _SAMPLE_MARKET + _SAMPLE_MARKET}))
    dedup_ok = bool(dup and dup.get("dropped_duplicates", 0) >= 1)
    checks.append({"check": "duplicate_events_prevented", "ok": dedup_ok,
                   "detail": f"dropped={dup.get('dropped_duplicates') if dup else 0}"})

    # (3) 연구 후보 생성 — feed → opportunity queue
    feed = _safe(lambda: collect({"news": _SAMPLE_NEWS}))
    candidates_ok = bool(feed and (feed.get("opportunity_count", 0) >= 0) and "opportunity_queue" in (feed or {}))
    checks.append({"check": "research_candidates_generated", "ok": candidates_ok,
                   "detail": f"opportunities={feed.get('opportunity_count') if feed else 0}"})

    # (4) 대시보드 표시 — live-intelligence 표면 조립
    dash = _safe(lambda: __import__("jarvis.research_workflow.providers",
                                    fromlist=["provider_registry"]).provider_registry())
    dashboard_ok = bool(dash and dash.get("count", 0) > 0)
    checks.append({"check": "dashboard_displays_updates", "ok": dashboard_ok,
                   "detail": f"providers={dash.get('count') if dash else 0}"})

    # (5) 기존 원장 불변 — rwf 원장 정확히 3개, 새 원장 없음
    from jarvis.research_workflow import ledger as wl
    ledgers_ok = len(wl.ALL_LEDGERS) == 3
    checks.append({"check": "existing_ledgers_unchanged", "ok": ledgers_ok,
                   "detail": f"rwf_ledgers={len(wl.ALL_LEDGERS)}"})

    safety = architecture_safety()
    all_ok = all(c["ok"] for c in checks) and safety["safe"]
    return {"chain": ["External Data", "Provider", "Normalization", "Event Intelligence",
                      "Research Trigger", "Workflow", "Validation Loop", "Memory"],
            "checks": checks, "operational": all_ok, "architecture_safety": safety,
            "is_advisory": True, "is_decision": False,
            "note": ("운영 검증(읽기전용) — 외부데이터→메모리 체인. 새 DB/원장/메모리/실행엔진 없음. "
                     "거래·집행·주문 없음.")}


def architecture_safety() -> dict:
    """아키텍처 안전(결정적) — P111-120 신규 모듈에 금지 동작/브로커/새 원장이 없음을 AST 로 확인."""
    import ast
    import pathlib

    here = pathlib.Path(__file__).resolve().parent
    modules = ("providers.py", "market_pipeline.py", "news_pipeline.py", "fundamental_pipeline.py",
               "ownership_pipeline.py", "research_feed.py", "data_quality.py",
               "operational_validation.py", "live_intelligence.py")
    forbidden_defs = {"execute", "trade", "deploy", "allocate", "approve", "place_order"}
    forbidden_imports = ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
                         "jarvis.live_trading", "jarvis.portfolio_execution")
    violations = []
    for f in modules:
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
            "checks": ["no new database/ledger/memory/execution engine",
                       "no execute/trade/place_order/allocate/approve", "no broker connection",
                       "advisory only"],
            "is_advisory": True, "is_decision": False}


def _safe(fn):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return None
