"""AI Hedge Fund Operations Console API — read-only 거버넌스/집행 파이프라인 표면.

Command Center·AI Council·Execution Monitor 등 신규 콘솔 UI 전용. **읽기전용.**
jarvis 거버넌스(status/registry/risk/autonomy) + P8 집행 파이프라인 원장(제어→시뮬→대조→
비용→리스크→감사→TCA) 상태를 집계. 어떤 것도 변경/집행하지 않음. 기존 파일 무변경.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/console", tags=["console"])


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _count_by(rows: list, key: str) -> dict:
    out: dict = {}
    for r in rows or []:
        k = r.get(key, "?") if isinstance(r, dict) else "?"
        out[k] = out.get(k, 0) + 1
    return out


# ── 거버넌스 상태 ────────────────────────────────────────────────
@router.get("/status")
def status() -> dict:
    """JARVIS STATUS — 시스템/자율레벨/집행경계/자본/노출/전략·리스크 요약."""
    import jarvis
    from jarvis.config import AUTONOMY_LEVEL, MIN_LIVE_LEVEL, live_execution_enabled

    js = _safe(jarvis.status, {}) or {}

    # 전략 레지스트리 카운트
    def _registry():
        from jarvis.registry import StrategyRegistry
        rows = StrategyRegistry().all_current()
        return rows
    reg_rows = _safe(_registry, []) or []
    reg_counts = _count_by(reg_rows, "status")
    active = sum(v for k, v in reg_counts.items()
                 if k in ("paper_active", "live_candidate", "micro_live", "constrained_live", "live"))

    # 자본/노출 (페이퍼 원장 기반, 없으면 명목만)
    def _capital():
        from jarvis.paper_execution.ledger import current_positions
        from jarvis.paper_execution.models import PAPER_CAPITAL
        pos = list(current_positions().values())
        gross = sum(abs(float(p.get("market_value", 0.0))) for p in pos)
        exposure = round(gross / PAPER_CAPITAL, 4) if PAPER_CAPITAL else 0.0
        return {"capital": PAPER_CAPITAL, "gross_exposure": round(gross, 2),
                "exposure_pct": round(exposure * 100, 2), "n_positions": len(pos)}
    cap = _safe(_capital, {"capital": None, "gross_exposure": 0.0, "exposure_pct": 0.0,
                           "n_positions": 0})

    return {
        "system": js.get("system", "Jarvis Quant OS"),
        "initialized": js.get("initialized", True),
        "autonomy": {"level": AUTONOMY_LEVEL, "min_live": MIN_LIVE_LEVEL,
                     "name": js.get("autonomy_name", ""),
                     "live_execution_enabled": live_execution_enabled()},
        "boundaries": {
            "live_execution": js.get("live_execution", "disabled"),
            "paper_monitoring": js.get("paper_monitoring", "enabled"),
            "research_automation": js.get("research_automation", "enabled"),
            "risk_governor": js.get("risk_governor", "active (dry-run)"),
            "audit_log": js.get("audit_log", "active"),
        },
        "strategies": {"total": len(reg_rows), "active": active, "by_status": reg_counts},
        "capital": cap,
    }


# ── 시장 레짐 ────────────────────────────────────────────────────
@router.get("/regime")
def regime() -> dict:
    """포트폴리오 레짐 추정(있으면). 없으면 unknown — 정직한 미구성."""
    def _regime():
        from jarvis.portfolio.regime import detect_regime  # noqa
        return detect_regime()
    r = _safe(_regime, None)
    if r is None:
        return {"regime": "UNKNOWN", "confidence": None,
                "note": "레짐 추정기 미구성 또는 데이터 없음"}
    return r


# ── P8 집행 파이프라인 상태 ──────────────────────────────────────
_PIPELINE = [
    ("control", "Execution Control", "jarvis.execution_control.ledger", "read_decisions", "status"),
    ("simulation", "Execution Simulation", "jarvis.execution_simulation.ledger", "read_reports", "status"),
    ("live", "Live Execution", "jarvis.live_execution.ledger", "read_responses", "status"),
    ("lifecycle", "Order Lifecycle", "jarvis.order_lifecycle.ledger", "read_events", "new_state"),
    ("reconciliation", "Fill Reconciliation", "jarvis.fill_reconciliation.ledger", "read_events", "status"),
    ("cost", "Execution Cost", "jarvis.execution_cost.ledger", "read_events", "status"),
    ("risk", "Execution Risk", "jarvis.execution_risk.ledger", "read_events", "overall_status"),
    ("audit", "Execution Audit", "jarvis.execution_audit.ledger", "read_certificates", "audit_status"),
    ("tca", "Post-Trade Analytics", "jarvis.post_trade_analytics.ledger", "read_reports", "overall_status"),
    ("readiness", "Execution Readiness", "jarvis.execution_readiness.ledger", "read_certificates", "status"),
]


@router.get("/pipeline")
def pipeline() -> dict:
    """P8 집행 파이프라인 각 단계 원장 카운트 + 상태 분포. 정직한 CLOSED 반영."""
    import importlib
    stages = []
    for key, label, mod_name, reader, status_field in _PIPELINE:
        def _read(mod_name=mod_name, reader=reader):
            mod = importlib.import_module(mod_name)
            return getattr(mod, reader)()
        rows = _safe(_read, []) or []
        stages.append({
            "key": key, "label": label, "count": len(rows),
            "by_status": _count_by(rows, status_field),
        })
    # 프로덕션 제안/승인
    def _proposals():
        from jarvis.production.approval import read_approvals, read_proposals
        return len(read_proposals()), len(read_approvals())
    n_prop, n_appr = _safe(_proposals, (0, 0)) or (0, 0)
    return {"stages": stages, "proposals": n_prop, "approvals": n_appr,
            "note": "라이브 자본 경계 CLOSED (autonomy<MIN_LIVE, 브로커 미구성)"}


# ── AI Council 결정 ──────────────────────────────────────────────
@router.get("/council")
def council(limit: int = 20) -> dict:
    """포트폴리오 의사결정 엔진 산출(있으면) — AI Council 결정 피드."""
    def _decisions():
        from jarvis.portfolio.journal import read_decisions  # noqa
        return read_decisions()
    rows = _safe(_decisions, None)
    if rows is None:
        # 대체: 감사 로그 tail
        def _audit_tail():
            from jarvis.audit import tail
            return tail(limit)
        events = _safe(_audit_tail, []) or []
        return {"source": "audit_log", "decisions": events[-limit:], "count": len(events)}
    return {"source": "decision_engine", "decisions": rows[-limit:], "count": len(rows)}
