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


# ══════════════════════════════════════════════════════════════════════
# 콘솔 확장 엔드포인트 (Strategy DNA · Validation · AI Council · Knowledge ·
# Research · Market · Portfolio OS · Execution). 모두 read-only·방어적.
# ══════════════════════════════════════════════════════════════════════

# ── Strategy DNA (레지스트리) ────────────────────────────────────
_FACTOR_HINT = {
    "tsmom": "Momentum", "momentum": "Momentum", "orb": "Breakout", "vwap": "Mean-Reversion",
    "buyback": "Event", "dart": "Event", "insider": "Event", "macro": "Macro",
    "pairs": "Stat-Arb", "vrp": "Volatility", "ict": "Price-Action", "funding": "Carry",
    "gex": "Flow", "orderflow": "Flow", "skew": "Volatility", "liquidity": "Flow",
}


def _factor_of(sid: str) -> str:
    s = (sid or "").lower()
    for k, v in _FACTOR_HINT.items():
        if k in s:
            return v
    return "Unclassified"


@router.get("/strategies")
def strategies() -> dict:
    """전략 DNA 목록 — 레지스트리 all_current + 팩터/상태 분류."""
    def _reg():
        from jarvis.registry import StrategyRegistry
        return StrategyRegistry().all_current()
    rows = _safe(_reg, []) or []
    out = []
    for r in rows:
        sid = r.get("strategy_id", "")
        out.append({
            "strategy_id": sid, "name": r.get("name", sid), "status": r.get("status", "?"),
            "factor": _factor_of(sid), "frozen": r.get("frozen", False),
            "config_hash": (r.get("config_hash", "") or "")[:16],
            "created_at": r.get("created_at", r.get("first_seen", "")),
            "updated_at": r.get("updated_at", r.get("last_event", "")),
        })
    out.sort(key=lambda x: (x["status"], x["strategy_id"]))
    return {"strategies": out, "total": len(out), "by_status": _count_by(rows, "status"),
            "by_factor": _count_by(out, "factor")}


@router.get("/strategies/{sid}")
def strategy_detail(sid: str) -> dict:
    """단일 전략 DNA + 관련 실험 이력 + 생애주기 이벤트."""
    def _reg():
        from jarvis.registry import StrategyRegistry
        reg = StrategyRegistry()
        st = reg.state(sid)
        events = []
        try:
            events = reg.history(sid)  # type: ignore
        except Exception:  # noqa: BLE001
            events = []
        return st, events
    st, events = _safe(_reg, (None, [])) or (None, [])

    def _exps():
        from research.agents.experiment_registry import load_all
        rows = [e for e in load_all() if e.get("hypothesis_id") == sid]
        return rows[-40:]
    exps = _safe(_exps, []) or []
    return {"strategy_id": sid, "state": st, "factor": _factor_of(sid),
            "lifecycle": events[-40:] if events else [], "experiments": exps,
            "experiment_count": len(exps)}


# ── Experiments / Hypothesis / Backtests ─────────────────────────
@router.get("/experiments")
def experiments(limit: int = 60) -> dict:
    """검증 실험 — hypothesis별 최신 상태 + 카운트 + 최근."""
    def _all():
        from research.agents.experiment_registry import load_all
        return load_all()
    rows = _safe(_all, []) or []
    latest: dict = {}
    for e in rows:
        hid = e.get("hypothesis_id")
        if hid:
            latest[hid] = e
    latest_rows = list(latest.values())
    counts = _count_by(latest_rows, "status")
    return {"latest": latest_rows[:limit], "counts": counts, "total_experiments": len(rows),
            "unique_hypotheses": len(latest_rows), "recent": rows[-limit:]}


# ── Validation Report (redteam + 실험 상태) ──────────────────────
@router.get("/validation")
def validation() -> dict:
    """검증 리포트 — redteam 감사(사람 vs 레드팀 판정) + 실험 상태 분포."""
    def _audit():
        from jarvis.redteam.review import audit_registry
        return audit_registry()
    audit = _safe(_audit, {"n": 0, "rows": []}) or {"n": 0, "rows": []}

    def _exp_counts():
        from research.agents.experiment_registry import load_all
        latest: dict = {}
        for e in load_all():
            hid = e.get("hypothesis_id")
            if hid:
                latest[hid] = e
        return _count_by(list(latest.values()), "status")
    exp_counts = _safe(_exp_counts, {}) or {}
    return {"redteam": audit, "experiment_status": exp_counts,
            "gates": ["walk_forward", "monte_carlo", "bh_fdr", "cost_stress", "redteam"]}


# ── AI Council 조직도 (실 서브시스템 상태 기반) ──────────────────
@router.get("/agents")
def agents() -> dict:
    """AI Council 조직도 — 실제 거버넌스/집행 서브시스템 상태로 구성. 정직한 status."""
    import jarvis
    from jarvis.config import AUTONOMY_LEVEL, live_execution_enabled
    js = _safe(jarvis.status, {}) or {}

    def _reg_counts():
        from jarvis.registry import StrategyRegistry
        rows = StrategyRegistry().all_current()
        return _count_by(rows, "status"), len(rows)
    reg_counts, reg_total = _safe(_reg_counts, ({}, 0)) or ({}, 0)

    def _profiles():
        import api_server.agent_store as ags
        return list(ags.AGENT_PROFILES.keys()) if isinstance(ags.AGENT_PROFILES, dict) else []
    profiles = _safe(_profiles, []) or []

    def _pipeline_active():
        return pipeline()
    pipe = _safe(_pipeline_active, {"stages": []}) or {"stages": []}
    pipe_by = {s["key"]: s["count"] for s in pipe.get("stages", [])}

    active = "active"
    dry = "dry-run"
    gated = "gated"
    closed = "closed"

    tree = {
        "id": "cio", "role": "CIO", "name": "JARVIS Governance",
        "status": active if js.get("initialized") else gated,
        "detail": f"Autonomy L{AUTONOMY_LEVEL} · {js.get('autonomy_name','')}",
        "children": [
            {"id": "research", "role": "Research", "name": "Alpha Research Division", "status": active,
             "children": [
                 {"id": "planner", "name": "Planner (P5)", "status": active, "detail": "coverage optimizer"},
                 {"id": "knowledge", "name": "Knowledge Graph (P4)", "status": active, "detail": "market memory"},
                 {"id": "fusion", "name": "Signal Fusion (P1)", "status": active, "detail": "weighted voting"},
                 {"id": "registry", "name": "Strategy Registry", "status": active,
                  "detail": f"{reg_total} strategies", "meta": reg_counts},
             ]},
            {"id": "risk", "role": "Risk", "name": "Risk & Governance Division",
             "status": dry,
             "children": [
                 {"id": "governor", "name": "Risk Governor", "status": dry, "detail": js.get("risk_governor", "")},
                 {"id": "redteam", "name": "Red Team", "status": active, "detail": "adversarial audit"},
                 {"id": "exec_risk", "name": "Execution Risk (P8.5)", "status": gated,
                  "detail": f"{pipe_by.get('risk',0)} reports"},
                 {"id": "audit", "name": "Execution Audit (P8.6)", "status": gated,
                  "detail": f"{pipe_by.get('audit',0)} certs"},
             ]},
            {"id": "execution", "role": "Execution", "name": "Execution Division",
             "status": closed if not live_execution_enabled() else active,
             "children": [
                 {"id": "control", "name": "Execution Control (P7.4)", "status": gated,
                  "detail": f"{pipe_by.get('control',0)} decisions"},
                 {"id": "adapter", "name": "Live Adapter (P8.1)", "status": closed,
                  "detail": "broker write · human-gated"},
                 {"id": "recon", "name": "Fill Reconciliation (P8.3)", "status": gated,
                  "detail": f"{pipe_by.get('reconciliation',0)} events"},
                 {"id": "tca", "name": "Post-Trade Analytics (P8.7)", "status": gated,
                  "detail": f"{pipe_by.get('tca',0)} reports"},
             ]},
        ],
    }
    return {"council": tree, "archetypes": profiles,
            "live_execution_enabled": live_execution_enabled()}


@router.get("/logs")
def logs(limit: int = 60) -> dict:
    """거버넌스 감사 로그 tail (원시)."""
    def _tail():
        from jarvis.audit import tail
        return tail(limit)
    rows = _safe(_tail, []) or []
    return {"logs": rows[-limit:], "count": len(rows)}


# ── Knowledge Graph (레지스트리·실험에서 실 그래프 도출) ─────────
_ACTIVE_STATUS = {"paper_active", "live_candidate", "micro_live", "constrained_live", "live"}


def _registry_rows() -> list:
    def _reg():
        from jarvis.registry import StrategyRegistry
        return StrategyRegistry().all_current()
    return _safe(_reg, []) or []


@router.get("/knowledge")
def knowledge() -> dict:
    """지식 그래프 — 전략·팩터·상태의 실제 관계를 노드-엣지로 도출(레지스트리 기반).

    정식 KG projection DB가 있으면 failed_strategies도 첨부. 없어도 실데이터 그래프 제공.
    """
    rows = _registry_rows()
    nodes: list = []
    edges: list = []
    factors: dict = {}
    statuses: dict = {}
    for r in rows:
        sid = r.get("strategy_id", "")
        if not sid:
            continue
        fac = _factor_of(sid)
        st = r.get("status", "?")
        factors[fac] = factors.get(fac, 0) + 1
        statuses[st] = statuses.get(st, 0) + 1
        nodes.append({"id": f"S:{sid}", "label": r.get("name", sid), "type": "strategy",
                      "factor": fac, "status": st})
        edges.append({"source": f"S:{sid}", "target": f"F:{fac}", "kind": "factor"})
    for fac, n in factors.items():
        nodes.append({"id": f"F:{fac}", "label": fac, "type": "factor", "count": n})

    def _kg_failed():
        from jarvis.knowledge.query import find_failed_strategies
        return find_failed_strategies()
    failed = _safe(_kg_failed, []) or []

    return {"built": bool(nodes), "derived": True,
            "nodes": nodes, "edges": edges,
            "factors": factors, "statuses": statuses,
            "failed_strategies": failed,
            "note": f"레지스트리 {len(rows)}전략에서 도출한 실 관계 그래프"}


# ── Research (Planner 제안 + 커버리지 갭 도출) ────────────────────
@router.get("/research")
def research() -> dict:
    """리서치 — planner 제안(있으면) + 팩터×상태 커버리지 갭 도출."""
    def _plan():
        from jarvis.planner.query import latest_proposals
        return latest_proposals()
    props = _safe(_plan, []) or []

    # 커버리지 갭: 팩터별 활성(paper_active+) 전략 유무
    rows = _registry_rows()
    fac_active: dict = {}
    fac_total: dict = {}
    for r in rows:
        sid = r.get("strategy_id", "")
        fac = _factor_of(sid)
        fac_total[fac] = fac_total.get(fac, 0) + 1
        if r.get("status") in _ACTIVE_STATUS:
            fac_active[fac] = fac_active.get(fac, 0) + 1
    gaps = []
    for fac, total in sorted(fac_total.items(), key=lambda x: -x[1]):
        active = fac_active.get(fac, 0)
        if active == 0:
            gaps.append({"factor": fac, "total": total, "active": 0,
                         "gap": "활성 전략 없음 — 검증 통과 후보 필요",
                         "severity": "high" if total >= 3 else "medium"})
    return {"proposals": props, "count": len(props), "coverage_gaps": gaps,
            "factor_coverage": {f: {"total": fac_total[f], "active": fac_active.get(f, 0)}
                                for f in fac_total}}


# ── Market Intelligence (팩터 성과 기반 posture 도출) ─────────────
@router.get("/market")
def market() -> dict:
    """마켓 인텔리전스 — 레짐 + 팩터별 활성/성과 posture 도출."""
    rows = _registry_rows()
    fac: dict = {}
    for r in rows:
        f = _factor_of(r.get("strategy_id", ""))
        d = fac.setdefault(f, {"total": 0, "active": 0, "rejected": 0})
        d["total"] += 1
        if r.get("status") in _ACTIVE_STATUS:
            d["active"] += 1
        if r.get("status") == "rejected":
            d["rejected"] += 1
    # posture: 활성 비중이 높은 팩터 = 시장에서 '먹히는' 것으로 해석
    posture = sorted(
        ({"factor": f, **d, "conviction": round(d["active"] / d["total"], 3) if d["total"] else 0.0}
         for f, d in fac.items()),
        key=lambda x: (-x["conviction"], -x["total"]))
    return {"regime": regime(), "posture": posture,
            "note": "팩터별 활성 전략 비중 기반 시장 posture(레지스트리 도출)"}


# ── Portfolio OS ─────────────────────────────────────────────────
@router.get("/allocation")
def allocation() -> dict:
    """포트폴리오 배분 — 원장(있으면) + 활성 전략 기반 파생 제안."""
    def _alloc():
        from jarvis.portfolio.allocation_ledger import read_latest
        return read_latest(20)
    def _journal():
        from jarvis.portfolio.journal import read_latest
        return read_latest(20)
    allocs = _safe(_alloc, []) or []
    journal = _safe(_journal, []) or []

    # 파생 제안: 활성(paper_active+) 전략 동일비중(제안 전용·미집행)
    rows = _registry_rows()
    active = [r for r in rows if r.get("status") in _ACTIVE_STATUS]
    derived = []
    if active:
        w = round(1.0 / len(active), 4)
        for r in active:
            sid = r.get("strategy_id", "")
            derived.append({"strategy_id": sid, "name": r.get("name", sid),
                            "factor": _factor_of(sid), "status": r.get("status"),
                            "target_weight": w})
    return {"allocations": allocs, "decisions": journal, "rebalances": [],
            "derived_proposal": derived, "derived_note": "활성 전략 동일비중 파생(제안 전용·미집행)",
            "note": "" if allocs else "포트폴리오 오케스트레이터 원장 없음 — 활성 전략 기반 파생 제안 표시"}


@router.get("/positions")
def positions() -> dict:
    """포지션 — 페이퍼 원장 현재 포지션."""
    def _pos():
        from jarvis.paper_execution.ledger import current_positions
        return list(current_positions().values())
    pos = _safe(_pos, []) or []
    return {"positions": pos, "count": len(pos),
            "note": "" if pos else "오픈 포지션 없음"}


@router.get("/risk")
def risk() -> dict:
    """리스크 — 거버너 상태 + 한도 + 노출 + 집행 리스크 원장."""
    from jarvis.config import AUTONOMY_LEVEL, MIN_LIVE_LEVEL, live_execution_enabled
    def _limits():
        from jarvis.risk.governor import RiskLimits
        rl = RiskLimits()
        return {"max_notional": rl.max_notional, "max_order_qty": rl.max_order_qty,
                "max_leverage": rl.max_leverage, "kill_switch": rl.kill_switch,
                "require_human_approval": rl.require_human_approval}
    limits = _safe(_limits, {}) or {}
    cap = status()["capital"]
    def _xrisk():
        from jarvis.execution_risk.ledger import read_events
        return read_events()
    xrisk = _safe(_xrisk, []) or []
    return {"governor": "active (dry-run)", "limits": limits, "capital": cap,
            "autonomy": {"level": AUTONOMY_LEVEL, "min_live": MIN_LIVE_LEVEL,
                         "live_execution_enabled": live_execution_enabled()},
            "execution_risk_events": len(xrisk),
            "by_status": _count_by(xrisk, "overall_status")}


# ── Execution ────────────────────────────────────────────────────
@router.get("/orders")
def orders() -> dict:
    """주문 — 라이브 집행 요청/응답 + 생애주기(있으면). 정직한 CLOSED."""
    def _req():
        from jarvis.live_execution.ledger import read_requests, read_responses
        return read_requests(), read_responses()
    reqs, resps = _safe(_req, ([], [])) or ([], [])
    def _lc():
        from jarvis.order_lifecycle.ledger import read_events
        return read_events()
    lc = _safe(_lc, []) or []
    return {"requests": reqs, "responses": resps, "lifecycle_events": len(lc),
            "note": "" if reqs else "라이브 주문 없음 (자본 경계 CLOSED)"}


@router.get("/broker")
def broker() -> dict:
    """브로커 — read-only health + 집행 어댑터 상태(mock/ib/kis)."""
    def _health():
        from jarvis.broker_readonly.adapters import IBReadOnlyProvider, KISReadOnlyProvider
        ib = IBReadOnlyProvider("now").health_check()
        kis = KISReadOnlyProvider("now").health_check()
        return {"ib": ib.to_dict() if hasattr(ib, "to_dict") else ib,
                "kis": kis.to_dict() if hasattr(kis, "to_dict") else kis}
    ro = _safe(_health, {}) or {}
    def _exec_adapters():
        from jarvis.live_execution.adapters import (
            IBExecutionAdapter, KISExecutionAdapter, MockExecutionAdapter)
        return {"mock": MockExecutionAdapter().health_check(),
                "ib": IBExecutionAdapter().health_check(),
                "kis": KISExecutionAdapter().health_check()}
    ex = _safe(_exec_adapters, {}) or {}
    return {"read_only": ro, "execution_adapters": ex}


@router.get("/monitor")
def monitor() -> dict:
    """집행 모니터 — P8 파이프라인 상세 + 최근 이벤트."""
    p = pipeline()
    return {**p, "capital": status()["capital"]}
