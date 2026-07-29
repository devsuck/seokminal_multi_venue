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


# ── 시장 레짐 + 포트폴리오 posture ───────────────────────────────
_POSTURE_BUCKETS = {
    "TREND-FOLLOWING": {"Momentum", "Breakout", "Price-Action"},
    "MEAN-REVERSION": {"Mean-Reversion", "Stat-Arb"},
    "CARRY & EVENT": {"Carry", "Event"},
    "FLOW-DRIVEN": {"Flow"},
}


def _derive_posture() -> dict:
    """실 레지스트리의 활성 전략 팩터 분포에서 '포트폴리오 posture' 도출.

    **시장 레짐 예측이 아님** — 펀드가 현재 어느 스타일에 포지셔닝됐는지의 정직한 파생 지표.
    """
    from jarvis.registry import StrategyRegistry
    rows = _safe(lambda: StrategyRegistry().all_current(), []) or []
    active_by_factor: dict = {}
    for r in rows:
        if r.get("status") in _ACTIVE_STATUS:
            f = _factor_of(r.get("strategy_id", ""))
            active_by_factor[f] = active_by_factor.get(f, 0) + 1
    total_active = sum(active_by_factor.values())
    bucket_active = {b: sum(active_by_factor.get(f, 0) for f in facs)
                     for b, facs in _POSTURE_BUCKETS.items()}
    if total_active == 0:
        return {"label": "DEFENSIVE / CASH", "confidence": 1.0, "total_active": 0,
                "breakdown": bucket_active, "basis": "활성 전략 없음"}
    dominant = max(bucket_active.items(), key=lambda x: x[1])
    return {"label": dominant[0] if dominant[1] > 0 else "DIVERSIFIED",
            "confidence": round(dominant[1] / total_active, 3),
            "total_active": total_active, "breakdown": bucket_active,
            "basis": "레지스트리 활성 전략 팩터 분포"}


@router.get("/regime")
def regime() -> dict:
    """시장 레짐(있으면) + 포트폴리오 posture(항상, 실데이터 파생).

    시장 레짐 감지기는 실 시장데이터/returns matrix 필요 — 없으면 UNKNOWN(정직).
    posture는 레지스트리 활성 전략에서 항상 도출(정직한 파생 지표).
    """
    def _regime():
        from jarvis.portfolio.regime import detect_regime  # noqa
        return detect_regime()
    r = _safe(_regime, None)
    posture = _safe(_derive_posture, None)
    if r is None:
        return {"regime": "UNKNOWN", "confidence": None,
                "note": "시장 레짐 감지기 미구성 (실 시장데이터 필요)",
                "posture": posture}
    return {**r, "posture": posture}


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


# ── Research OS (P41~P45 로컬 연구 환경 통합 — READ ONLY) ──────────
@router.get("/research-os")
def research_os() -> dict:
    """Research OS — Jarvis 로컬 연구 환경(P41~P45) 라이브 집계. **읽기전용, 결정/거래/집행 없음.**

    P41 integration_audit(감사) · P42 local_runtime(런타임/헬스) · P43 research_navigation(IA) ·
    P44 research_assistant(요약) · P45 local_automation(자동화) 엔진을 실행해 실데이터를 반환한다.
    어떤 것도 변경/집행하지 않으며, 실패한 하위 항목은 안전하게 비워둔다.
    """
    # P43 — 통합 네비게이션 IA(실측 모듈 수)
    def _nav():
        from jarvis.research_navigation.engine import NavigationEngine
        eng = NavigationEngine()
        man = eng.build_manifest("")
        sections = [{"section": s["section"], "moduleCount": s["module_count"],
                     "items": [{"item": i["item"], "moduleCount": i["module_count"],
                                "modules": i.get("modules", [])}
                               for i in s["items"]]}
                    for s in man.sections]
        workspaces = [{"workspace": w["workspace"], "description": w["description"],
                       "moduleCount": w["moduleCount"]} for w in eng.workspaces()]
        return {"sections": sections, "section_count": man.section_count,
                "item_count": man.item_count, "module_count": man.module_count,
                "coverage": man.coverage, "duplicate_page_count": man.duplicate_page_count,
                "digest": man.digest, "workspaces": workspaces}
    nav = _safe(_nav, {}) or {}

    # P41 — 섹션 단위 의존성 그래프(모듈 import 엣지를 섹션으로 집계). 노드-엣지.
    def _graph():
        from jarvis.integration_audit import scanner
        from jarvis.research_navigation.models import section_for
        root = scanner.default_root()
        edges = scanner.import_edges(root)
        agg: dict = {}
        for a, b in edges:
            key = (section_for(a), section_for(b))
            agg[key] = agg.get(key, 0) + 1
        counts: dict = {}
        for n in scanner.list_modules(root):
            s = section_for(n)
            counts[s] = counts.get(s, 0) + 1
        nodes = [{"id": s, "moduleCount": counts.get(s, 0),
                  "internal": agg.get((s, s), 0)} for s in sorted(counts)]
        graph_edges = [{"source": s, "target": t, "weight": w}
                       for (s, t), w in sorted(agg.items(), key=lambda x: -x[1])
                       if s != t]
        # 모듈 단위 엣지(섹션 태그 포함) — 프론트에서 섹션 확대(드릴) 시 사용
        module_edges = [{"source": a, "target": b,
                         "sourceSection": section_for(a), "targetSection": section_for(b)}
                        for a, b in edges]
        return {"nodes": nodes, "edges": graph_edges, "edge_total": len(edges),
                "module_edges": module_edges}
    graph = _safe(_graph, {}) or {}

    # P41 — 통합 감사
    def _audit():
        from jarvis.integration_audit.engine import IntegrationAuditEngine
        s = IntegrationAuditEngine().summary()
        return {"module_count": s["module_count"],
                "category_distribution": s["category_distribution"],
                "pattern_distribution": s["pattern_distribution"],
                "duplicate_cluster_count": s["duplicate_cluster_count"],
                "orphan_count": s["orphan_count"], "digest": s["digest"]}
    audit = _safe(_audit, {}) or {}

    # P42 — 로컬 런타임(환경/헬스/모듈 발견)
    def _runtime():
        from jarvis.local_runtime.engine import LocalRuntimeEngine
        eng = LocalRuntimeEngine()
        disc = eng.discover_modules()
        return {"env_status": eng.environment_status(),
                "health_status": eng.health_status(),
                "module_count": disc.module_count,
                "category_counts": disc.category_counts,
                "runtime_state": eng.runtime_state(),
                "checks": [c.to_dict() for c in eng.health_checks()]}
    runtime = _safe(_runtime, {}) or {}

    # P44 — 개인 연구 어시스턴트(기존 원장 READ ONLY 요약)
    def _assistant():
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        eng = ResearchAssistantEngine()
        daily = eng.daily_summary()
        fa = eng.failure_analysis()
        kn = eng.knowledge_recap()
        es = eng.experiment_summary()
        pa = eng.potential_areas()
        return {"total_records": daily.total_records, "active_sources": daily.active_sources,
                "source_counts": daily.source_counts, "failure_count": fa.failure_count,
                "knowledge_count": kn.memory_count + kn.lesson_count + kn.pattern_count,
                "experiment_run_count": es.run_count,
                "potential_areas": pa.areas[:6],
                "is_advisory": True, "is_decision": False}
    assistant = _safe(_assistant, {}) or {}

    # P45 — 로컬 자동화(잡/실행 집계)
    def _automation():
        from jarvis.local_automation.engine import LocalAutomationEngine
        eng = LocalAutomationEngine()
        rep = eng.generate_report("SYSTEM", "", commit=False)
        return {"job_count": rep.job_count, "enabled_job_count": rep.enabled_job_count,
                "run_count": rep.run_count, "success_count": rep.success_count,
                "failed_count": rep.failed_count, "schedule_count": rep.schedule_count,
                "kind_distribution": rep.kind_distribution}
    automation = _safe(_automation, {}) or {}

    capabilities = [
        {"phase": "P41", "name": "Integration Audit",
         "summary": "기존 아키텍처 결정적 감사 — 인벤토리·의존성·중복·미사용.",
         "metric": (f"{audit.get('module_count', 0)} modules · "
                    f"{audit.get('duplicate_cluster_count', 0)} dup families")},
        {"phase": "P42", "name": "Local Runtime",
         "summary": "로컬 단일 진입점 — 시작·모듈 발견·헬스 체크(클라우드 없음).",
         "metric": (f"health {runtime.get('health_status', '?')} · "
                    f"{runtime.get('module_count', 0)} modules")},
        {"phase": "P43", "name": "Unified Navigation",
         "summary": "기존 페이지를 Research/Knowledge/Agents/System 로 재배치.",
         "metric": (f"{nav.get('section_count', 0)} sections · "
                    f"{int(round(nav.get('coverage', 0) * 100))}% coverage")},
        {"phase": "P44", "name": "Research Assistant",
         "summary": "일일·실험·실패·지식 요약(분석만 · 결정/승인/집행 없음).",
         "metric": (f"{assistant.get('total_records', 0)} records · "
                    f"{assistant.get('failure_count', 0)} failures")},
        {"phase": "P45", "name": "Local Automation",
         "summary": "반복 연구 작업 워크플로 보조(자동 거래·배포·배분 없음).",
         "metric": (f"{automation.get('job_count', 0)} jobs · "
                    f"{automation.get('run_count', 0)} runs")},
    ]

    return {"meta": {"section_count": nav.get("section_count", 0),
                     "item_count": nav.get("item_count", 0),
                     "module_count": nav.get("module_count", 0),
                     "coverage": nav.get("coverage", 0.0),
                     "duplicate_families": audit.get("duplicate_cluster_count", 0),
                     "digest": nav.get("digest", "")},
            "sections": nav.get("sections", []),
            "workspaces": nav.get("workspaces", []),
            "graph": graph,
            "audit": audit, "runtime": runtime, "assistant": assistant,
            "automation": automation, "capabilities": capabilities,
            "disclaimer": ("Research OS — READ ONLY. 분석·추천·요약만 하며 자동 거래·자동 배포·자동 자본 배분·"
                           "전략 승인을 하지 않는다. P44 assistant analyzes · P45 automation = workflow assistance.")}


# ── Assistant (C3 — 대화형 질의, READ ONLY) ───────────────────────
@router.get("/assistant")
def assistant(q: str = "") -> dict:
    """Research Assistant — 자연어 질문 → 결정적 라우팅 → 기존 지식으로 응답. **분석·회상만, 결정/집행 없음.**

    헌장 "The Assistant Is The Primary Interface". q 없으면 예시 질문만 반환.
    """
    def _run():
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        eng = ResearchAssistantEngine()
        suggestions = eng.suggested_questions()
        if not (q or "").strip():
            return {"question": "", "intent": "idle", "answer": "무엇이든 물어보세요.",
                    "suggestions": suggestions, "is_advisory": True, "is_decision": False}
        ans = eng.ask(q)
        ans["suggestions"] = suggestions
        return ans
    return _safe(_run, {"intent": "error", "answer": "assistant 사용 불가", "suggestions": []}) or {}


# ── Failure Intelligence + Perspectives + Memory Graph (READ ONLY) ──
@router.get("/failure-intel")
def failure_intel(q: str = "") -> dict:
    """실패 지능(9종 분류) + 다관점 비평(Critic 포함) + 리서치 메모리 그래프. **분석만, 결정/집행 없음.**

    q 있으면 그 주제로 perspectives·mistake_check 도 포함. 기존 원장 READ ONLY.
    """
    def _run():
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        eng = ResearchAssistantEngine()
        out = {"failure_intelligence": eng.failure_intelligence().to_dict(),
               "memory_graph": eng.memory_graph(),
               "is_advisory": True, "is_decision": False}
        if (q or "").strip():
            out["perspectives"] = eng.perspectives(q)
            out["mistake_check"] = eng.mistake_check(q)
        return out
    return _safe(_run, {"failure_intelligence": {}, "memory_graph": {"nodes": [], "edges": []}}) or {}


# ══════════════ Research OS Dashboard (P68-71) — 조율 표면. READ ONLY (세션 관리 제외) ══════════════
def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@router.get("/research-workflow")
def research_workflow() -> dict:
    """P68 — 연구 워크플로/세션/큐 조율 상태(rwf_ 원장 폴드). **READ ONLY. 사람 결정 필수.**"""
    def _runs():
        from jarvis.research_workflow import ledger as wl
        from jarvis.research_workflow.orchestrator import WorkflowOrchestrator
        orch = WorkflowOrchestrator()
        seen, ids = set(), []
        for e in wl.read_runs():
            rid = e.get("run_id")
            if rid and rid not in seen:
                seen.add(rid)
                ids.append(rid)
        out = []
        for rid in ids[-25:]:
            st = orch.state(rid)
            out.append({"run_id": rid, "request": st.request, "current_stage": st.current_stage,
                        "completed_stages": st.completed_stages, "blocked_stage": st.blocked_stage,
                        "cancelled": st.cancelled,
                        "requires_human_decision": st.requires_human_decision,
                        "execution_log": st.execution_log})
        return out
    runs = _safe(_runs, []) or []

    def _sessions():
        from jarvis.research_workflow.session_manager import ResearchSessionManager
        return ResearchSessionManager().list_sessions()
    sessions = _safe(_sessions, []) or []

    def _queue():
        from jarvis.research_assistant.research_queue import ResearchQueueEngine
        return ResearchQueueEngine().generate(limit=8).to_dict()
    queue = _safe(_queue, {"proposals": [], "proposal_count": 0}) or {}

    from jarvis.research_workflow.models import STAGES
    return {"stages": list(STAGES), "runs": runs, "sessions": sessions, "queue": queue,
            "counts": {"runs": len(runs), "sessions": len(sessions),
                       "active_sessions": sum(1 for s in sessions if s.get("state") == "ACTIVE"),
                       "awaiting_human": sum(1 for r in runs if r.get("requires_human_decision")),
                       "proposals": queue.get("proposal_count", 0)},
            "is_advisory": True, "is_decision": False,
            "disclaimer": ("Research OS workflow — READ ONLY 조율 상태. Human Decision 은 사람만, "
                           "자동 거래·집행·자본배분 없음.")}


@router.get("/decision-memo")
def decision_memo(q: str = "") -> dict:
    """P65 — 주제에 대한 Decision Memo(모든 섹션 통합). **자문일 뿐, 결정 아님.**"""
    def _run():
        if not (q or "").strip():
            return {"question": "", "note": "주제를 입력하세요.", "is_advisory": True,
                    "is_decision": False}
        from jarvis.research_workflow.decision_support import DecisionSupportEngine
        return DecisionSupportEngine().build_memo(q, topic=q).to_dict()
    return _safe(_run, {"note": "decision memo 사용 불가", "is_decision": False}) or {}


@router.get("/explainability")
def explainability(q: str = "") -> dict:
    """P67/P71 — 결론의 증거 사슬(Experiment→…→Recommendation). **블랙박스 아님, 결정 아님.**"""
    def _run():
        if not (q or "").strip():
            return {"topic": "", "note": "주제를 입력하세요.", "chain": [], "edges": []}
        from jarvis.research_workflow.explainability import ExplainabilityEngine
        return ExplainabilityEngine().evidence_chain(q).to_dict()
    return _safe(_run, {"note": "explainability 사용 불가", "chain": [], "edges": []}) or {}


@router.get("/operating-console")
def operating_console() -> dict:
    """P70 — 헤지펀드 운영 콘솔(오늘의 연구/기회/리스크/이벤트/노출/페이퍼/세션/추천). **READ ONLY.**"""
    def _research():
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        eng = ResearchAssistantEngine()
        d = eng.daily_summary()
        es = eng.experiment_summary()
        return {"total_records": d.total_records, "active_sources": d.active_sources,
                "experiment_runs": es.run_count, "results": es.result_count}
    research = _safe(_research, {}) or {}

    def _opportunities():
        from jarvis.research_assistant.research_queue import ResearchQueueEngine
        q = ResearchQueueEngine().generate(limit=6)
        return [{"name": p.name, "kind": p.kind, "confidence": p.confidence,
                 "expected_value": p.expected_value, "reason": p.reason}
                for p in q.proposals]
    opportunities = _safe(_opportunities, []) or []

    def _risks():
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        fi = ResearchAssistantEngine().failure_intelligence()
        return {"total_failures": fi.total_failures, "top_category": fi.top_category,
                "by_category": fi.by_category, "lessons": fi.lessons[:5]}
    risks = _safe(_risks, {}) or {}

    def _events():
        from jarvis.research_assistant.event_intelligence import MarketEventIntelligence
        g = MarketEventIntelligence().relationship_graph()
        return {"node_count": g["node_count"], "edge_count": g["edge_count"],
                "note": "정적 공급망/기업 관계 참조 그래프 — 이벤트 발생 시 파급 추적."}
    events = _safe(_events, {}) or {}

    def _paper():
        from jarvis.paper_execution.engine import portfolio_status
        ps = portfolio_status()
        return {"portfolio_value": ps.get("portfolio_value"), "n_positions": ps.get("n_positions"),
                "pnl_summary": ps.get("pnl_summary")}
    paper = _safe(_paper, {}) or {}

    def _exposure():
        from jarvis.paper_execution.ledger import current_positions
        from jarvis.paper_execution.models import PAPER_CAPITAL
        pos = list(current_positions().values())
        gross = sum(abs(float(p.get("market_value", 0.0))) for p in pos)
        return {"capital": PAPER_CAPITAL, "gross_exposure": round(gross, 2),
                "exposure_pct": round(gross / PAPER_CAPITAL * 100, 2) if PAPER_CAPITAL else 0.0,
                "n_positions": len(pos)}
    exposure = _safe(_exposure, {}) or {}

    def _sessions():
        from jarvis.research_workflow.session_manager import ResearchSessionManager
        s = ResearchSessionManager().list_sessions()
        return {"count": len(s), "active": sum(1 for x in s if x.get("state") == "ACTIVE"),
                "items": s[:6]}
    sessions = _safe(_sessions, {"count": 0, "active": 0, "items": []}) or {}

    def _recommendations():
        # 상위 기회에 대한 협의체 권고(자문). 없으면 빈 목록.
        if not opportunities:
            return []
        from jarvis.research_assistant.council import ResearchCouncilEngine
        from jarvis.research_assistant.models import extract_topic
        eng = ResearchCouncilEngine()
        out = []
        for opp in opportunities[:2]:
            topic = extract_topic(opp["name"]) or opp["name"]
            memo = eng.deliberate(topic)
            out.append({"topic": topic, "recommendation": memo.recommendation,
                        "conflicts": len(memo.conflicts)})
        return out
    recommendations = _safe(_recommendations, []) or []

    return {"date": _now_iso()[:10], "research": research, "opportunities": opportunities,
            "risks": risks, "events": events, "paper": paper, "exposure": exposure,
            "sessions": sessions, "recommendations": recommendations,
            "is_advisory": True, "is_decision": False,
            "disclaimer": ("Operating Console — READ ONLY 요약. 분석·추천·요약만, 자동 거래·집행·"
                           "자본배분 없음. 모든 결정은 사람.")}


@router.post("/session/{action}")
def session_action(action: str, session_id: str = "", goal: str = "") -> dict:
    """P68 — 세션 관리(create/pause/resume/archive). **유일한 변경 작업 — rwf_sessions 원장에만 append.**

    거래·집행·자본배분 없음. append-only 이벤트 소싱. 사람 조작.
    """
    def _run():
        from jarvis.research_workflow.session_manager import ResearchSessionManager
        mgr = ResearchSessionManager()
        now = _now_iso()
        act = (action or "").lower()
        if act == "create":
            return mgr.create_session(goal or "untitled research", now=now, commit=True).to_dict()
        if not session_id:
            return {"error": "session_id required"}
        if act == "pause":
            return mgr.pause_session(session_id, now=now, commit=True).to_dict()
        if act == "resume":
            return mgr.resume_session(session_id, now=now, commit=True).to_dict()
        if act == "archive":
            return mgr.archive_session(session_id, now=now, commit=True).to_dict()
        return {"error": f"unknown action {action}"}
    return _safe(_run, {"error": "session action failed"}) or {}


# ══════════════ Autonomous Research Runtime (P72-76) — 조율 표면. READ ONLY ══════════════
@router.get("/autonomous-runtime")
def autonomous_runtime(q: str = "") -> dict:
    """P72-76 — 자율 연구 런타임(가설·플랜·비판·우선순위 + 루프 상태). **제안/비판/우선순위만, 실행/결정 없음.**

    q(주제) 있으면 해당 주제로 가설 생성→플랜→비판→우선순위 미리보기. rwf_loops 원장의 루프 상태도 집계.
    어떤 것도 변경/집행하지 않는다.
    """
    def _preview():
        if not (q or "").strip():
            return {}
        from jarvis.research_workflow.experiment_planner import ExperimentPlanner
        from jarvis.research_workflow.hypothesis_generator import HypothesisGenerator
        from jarvis.research_workflow.research_critic import ResearchCritic
        from jarvis.research_workflow.research_prioritizer import ResearchPrioritizer
        hyps = HypothesisGenerator().generate(topic=q, limit=6)
        ranked = ResearchPrioritizer().prioritize([h.to_dict() for h in hyps])
        top = next((h for h in hyps if h.hypothesis_id == ranked.recommended.get("hypothesis_id")),
                   hyps[0] if hyps else None)
        spec = ExperimentPlanner().plan(top).to_dict() if top else {}
        critique = ResearchCritic().critique(spec).to_dict() if spec else {}
        return {"hypotheses": [h.to_dict() for h in hyps],
                "ranked": ranked.to_dict(), "recommended_spec": spec, "critique": critique}
    preview = _safe(_preview, {}) or {}

    def _loops():
        from jarvis.research_workflow import ledger as wl
        from jarvis.research_workflow.autonomous_loop import AutonomousResearchLoop
        loop = AutonomousResearchLoop()
        seen, ids = set(), []
        for e in wl.read_loops():
            lid = e.get("loop_id")
            if lid and lid not in seen:
                seen.add(lid)
                ids.append(lid)
        out = []
        for lid in ids[-15:]:
            st = loop.state(lid)
            out.append({"loop_id": lid, "idea": st.idea, "current_stage": st.current_stage,
                        "completed_stages": st.completed_stages, "blocked_stage": st.blocked_stage,
                        "cancelled": st.cancelled, "paused": st.paused,
                        "requires_human_checkpoint": st.requires_human_checkpoint,
                        "audit_trail": st.audit_trail})
        return out
    loops = _safe(_loops, []) or []

    from jarvis.research_workflow.models import LOOP_STAGES
    return {"topic": q, "loop_stages": list(LOOP_STAGES), "preview": preview, "loops": loops,
            "counts": {"loops": len(loops),
                       "awaiting_checkpoint": sum(1 for lp in loops if lp.get("requires_human_checkpoint"))},
            "is_advisory": True, "is_decision": False,
            "disclaimer": ("Autonomous Research Runtime — 제안·비판·우선순위·학습만. 거래·집행·자본배분·"
                           "배포 승인 없음. 사람이 모든 투자 결정을 한다.")}


# ══════════════ Research OS Completion (P78-85) — 통합·시각화 표면. READ ONLY ══════════════
@router.get("/research-timeline")
def research_timeline(q: str = "", limit: int = 200) -> dict:
    """P78 — 기존 append-only 원장에서 재구성한 연구 타임라인. **새 히스토리 DB 없음, 읽기전용.**"""
    from jarvis.research_workflow.timeline import build_timeline
    return _safe(lambda: build_timeline(q, limit=limit), {"entries": [], "count": 0}) or {}


@router.get("/research-graph")
def research_graph(q: str = "", limit: int = 120) -> dict:
    """P79 — 다개체 연구 지식 그래프(기존 memory_graph/relationship_graph 결합). **읽기전용.**"""
    from jarvis.research_workflow.knowledge_graph import build_knowledge_graph
    return _safe(lambda: build_knowledge_graph(q, limit=limit),
                 {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0}) or {}


@router.get("/research-health")
def research_health() -> dict:
    """P81 — 결정적 운영 건강 지표(활성/대기/검증누락/지식성장/속도/커버리지/점수). **읽기전용.**"""
    from jarvis.research_workflow.health_monitor import build_health
    return _safe(build_health, {"overall_health_score": 0}) or {}


@router.get("/continuous-learning")
def continuous_learning() -> dict:
    """P82 — 지속 학습 커버리지(각 메모리 채널 축적량). **읽기전용, 새 저장소 없음.**"""
    from jarvis.research_workflow.continuous_learning import learning_status
    return _safe(learning_status, {"channels": {}, "total": 0}) or {}


def _strategy_metrics(name: str) -> dict:
    """실험 원장(expt_)에서 전략명 매칭 실행의 수치 지표 재구성(읽기전용)."""
    from jarvis.experiment_tracking import ledger as el
    low = (name or "").lower()
    exp_ids = {e["experiment_id"] for e in el.read_experiments()
               if low and low in str(e.get("name", "")).lower()}
    run_ids = {r["run_id"] for r in el.read_runs() if r.get("experiment_id") in exp_ids}
    metrics: dict = {}
    for res in el.read_results():
        if res.get("run_id") in run_ids:
            try:
                metrics[res.get("metric")] = float(res.get("value"))
            except (TypeError, ValueError):
                pass
    return metrics


@router.get("/research-quality")
def research_quality(q: str = "") -> dict:
    """P84 — 연구 품질 점수(결정적 다차원). q=전략명 → 실험 원장에서 지표 재구성해 채점. **읽기전용.**"""
    def _run():
        if not (q or "").strip():
            return {"note": "전략명(q)을 입력하세요.", "is_decision": False}
        from jarvis.research_workflow.quality_score import score_research
        metrics = _strategy_metrics(q)
        return score_research({"strategy_name": q, "metrics": metrics, "source": "ledger"})
    return _safe(_run, {"note": "quality 사용 불가"}) or {}


@router.get("/cross-strategy")
def cross_strategy() -> dict:
    """P83 — 전략 간 교차 지능(유사/상관/충돌/공유교훈·리스크). 원장의 전략을 쌍별 비교. **읽기전용.**"""
    def _run():
        from jarvis.research_ingestion.ledger import read_ingestions
        from jarvis.research_workflow.cross_strategy import compare_all
        names = []
        for r in read_ingestions():
            n = r.get("strategy_name")
            if n and n not in names:
                names.append(n)
        strategies = [{"name": n, "metrics": _strategy_metrics(n)} for n in names[:6]]
        return compare_all(strategies)
    return _safe(_run, {"pairs": [], "count": 0}) or {}


@router.get("/cockpit")
def cockpit() -> dict:
    """P85 — Executive Research Cockpit(모든 역량 통합 홈). **READ ONLY. 사람이 모든 결정.**"""
    from jarvis.research_workflow.cockpit import build_cockpit
    return _safe(build_cockpit, {"health_score": 0}) or {}


# ══════════════ Market Intelligence & Investment Research OS (P86-95) — READ ONLY ══════════════
@router.get("/market-regime")
def market_regime() -> dict:
    """P87 — 시장 레짐 분석. 기존 /regime 지표(있으면)로 분류 + 유사기간·유리/불리 전략. **읽기전용.**"""
    def _run():
        ind = _safe(lambda: __import__("jarvis.portfolio.regime", fromlist=["detect_regime"]).detect_regime(), None)
        from jarvis.research_workflow.regime import detect_regime
        # 기존 감지기가 지표를 주면 사용, 아니면 빈 dict → UNKNOWN(정직)
        indicators = ind.get("indicators") if isinstance(ind, dict) else {}
        return detect_regime(indicators or {})
    return _safe(_run, {"regime": "UNKNOWN"}) or {}


@router.get("/opportunity-queue")
def opportunity_queue() -> dict:
    """P88 — 기회 발견 큐(연구 아이디어만, 트레이드 신호 아님). 기본은 빈 신호 → 빈 큐(정직). **읽기전용.**"""
    from jarvis.research_workflow.opportunity_discovery import discover
    return _safe(lambda: discover({}), {"opportunities": [], "count": 0}) or {}


@router.get("/alt-data")
def alt_data() -> dict:
    """P89 — 대체 연구 데이터 프레임워크 카탈로그(아키텍처). **연구 근거 전용, 신호 아님. 읽기전용.**"""
    from jarvis.research_workflow.alt_data import catalog
    return _safe(catalog, {"sources": {}, "count": 0}) or {}


@router.get("/council-expanded")
def council_expanded(q: str = "") -> dict:
    """P90 — 7관점 협의체(Quant/Macro/Industry/Behavioral/Risk/Contrarian/Portfolio). **논거만, 결정 없음.**"""
    def _run():
        if not (q or "").strip():
            return {"note": "질문(q)을 입력하세요.", "expanded_perspectives": [], "is_decision": False}
        from jarvis.research_workflow.council_evolution import deliberate
        return deliberate(q)
    return _safe(_run, {"note": "council 사용 불가"}) or {}


@router.get("/strategy-lab")
def strategy_lab(q: str = "") -> dict:
    """P91 — Strategy DNA(factors/universe/horizon/entry/exit/risk/validation/failure/regimes). **읽기전용.**"""
    def _run():
        if not (q or "").strip():
            return {"note": "전략명(q)을 입력하세요."}
        from jarvis.research_workflow.strategy_lab import repeated_mistakes, strategy_dna
        metrics = _strategy_metrics(q)
        dna = strategy_dna(q, spec={"metrics": metrics})
        dna["repeated_mistakes"] = repeated_mistakes(q)
        return dna
    return _safe(_run, {"note": "strategy lab 사용 불가"}) or {}


@router.get("/market-cockpit")
def market_cockpit() -> dict:
    """P95 — Jarvis Investment Research OS v1.0 (시장상태→기회→실험→검증→리스크→포트폴리오→결정큐→지식). **READ ONLY.**"""
    from jarvis.research_workflow.market_cockpit import build_market_cockpit
    return _safe(lambda: build_market_cockpit({}, {}), {"market_state": {"regime": "UNKNOWN"}}) or {}


# ══════════════ Live Market Intelligence Integration (P96-100) — DATA→EVENT→CONTEXT. READ ONLY ══════════════
@router.get("/news-intel")
def news_intel(q: str = "", entity: str = "") -> dict:
    """P97 — 뉴스 헤드라인 → 연구 이벤트(유형·영향기업·섹터·관련성·과거유사). **읽기전용, 신호 아님.**"""
    def _run():
        if not (q or "").strip():
            return {"note": "헤드라인(q)을 입력하세요.", "event_type": "", "affected_companies": []}
        from jarvis.research_workflow.news_intelligence import analyze_headline
        return analyze_headline(q, entity=entity)
    return _safe(_run, {"note": "news intel 사용 불가"}) or {}


@router.get("/supply-chain-impact")
def supply_chain_impact(q: str = "", entity: str = "") -> dict:
    """P99 — 이벤트 → 공급망 영향 전파(공급자/고객/경쟁사/섹터·경로·불확실성). 기존 그래프 재사용. **읽기전용.**"""
    def _run():
        if not (q or "").strip() and not entity:
            return {"origin": "", "affected_entities": [], "note": "이벤트/개체(q 또는 entity)를 입력하세요."}
        from jarvis.research_workflow.supply_chain_impact import propagate
        return propagate({"text": q, "entity": entity})
    return _safe(_run, {"origin": "", "affected_entities": []}) or {}


@router.get("/earnings-intel")
def earnings_intel() -> dict:
    """P100 — 실적 인텔리전스 프레임(기대 vs 실제·서프라이즈·전략영향). 입력 없으면 스키마 안내. **읽기전용.**"""
    return {"note": "실적 이벤트는 데이터 소스 연결 시 채워집니다(어댑터 준비 완료).",
            "fields": ["company", "period", "expected_metrics", "actual_metrics", "surprise",
                       "historical_comparison", "related_strategy_impact"],
            "is_advisory": True, "is_decision": False}


@router.get("/market-intel-feed")
def market_intel_feed(q: str = "", entity: str = "") -> dict:
    """P96-100 — 통합 라이브 이벤트 피드(시장/뉴스/내부자/공급망) + 시장 컨텍스트(레짐). **READ ONLY.**

    q(헤드라인/이벤트) 있으면 뉴스·공급망 라이브 데모. 시장 컨텍스트는 항상. 데이터 소스 연결 전엔 정직하게 빈 피드.
    """
    feed = []
    impact = {}
    if (q or "").strip() or entity:
        def _news():
            from jarvis.research_workflow.news_intelligence import analyze_headline
            n = analyze_headline(q, entity=entity)
            return {"category": "NEWS", "event_type": n["event_type"], "label": q or entity,
                    "affected": n["affected_companies"][:4], "relevance": n["relevance_score"]}
        feed.append(_safe(_news, None))

        def _supply():
            from jarvis.research_workflow.supply_chain_impact import propagate
            r = propagate({"text": q, "entity": entity})
            return {"origin": r.get("origin"), "affected_entities": r.get("affected_entities", []),
                    "customers": r.get("customers", []), "direct_suppliers": r.get("direct_suppliers", [])}
        impact = _safe(_supply, {}) or {}

    market_context = _safe(lambda: __import__("jarvis.research_workflow.regime", fromlist=["detect_regime"]).detect_regime({}), {"regime": "UNKNOWN"})
    opportunities = _safe(lambda: __import__("jarvis.research_workflow.opportunity_discovery",
                                             fromlist=["discover"]).discover({}), {"opportunities": []})
    return {"query": q, "live_event_feed": [f for f in feed if f], "impact_map": impact,
            "research_opportunities": opportunities.get("opportunities", []),
            "market_context": {"regime": market_context.get("regime"),
                               "labels": market_context.get("labels", []),
                               "recommended_research": market_context.get("recommended_research", []),
                               "avoid": market_context.get("avoid", [])},
            "adapters": ["market_data", "news", "insider_flow", "supply_chain", "earnings"],
            "is_advisory": True, "is_decision": False,
            "disclaimer": ("Market Intelligence Feed — READ ONLY. 데이터→이벤트→연구컨텍스트→사람검토. "
                           "데이터 소스 미연결 시 빈 피드(정직). 자동 거래·집행·자본배분 없음. 사람이 모든 결정.")}


# ══════════════ Research Validation Loop & Operational v2.0 (P101-110) — READ ONLY ══════════════
# 데모용 백테스트 vs 페이퍼(교육용 예시 — 백테스트 성공/페이퍼 실패). 라이브 데이터 연결 전 검증 패널 시연.
_DEMO_BT = {"strategy_name": "tsmom", "universe": "US KOSPI", "hypothesis": "trend persists",
            "entry_rules": "12-1 momentum cross", "source": "demo",
            "metrics": {"return": 0.22, "sharpe": 1.5, "max_drawdown": -0.11, "volatility": 0.14,
                        "walk_forward": 0.6, "out_of_sample": 0.5, "cost_impact": 0.02,
                        "random_baseline": 0.1, "turnover": 0.3, "parameter_stability": 0.7,
                        "n_obs": 900, "exposure": 0.9}}
_DEMO_PAPER = {"strategy_name": "tsmom", "regime": "HIGH_VOL",
               "metrics": {"return": 0.05, "sharpe": 0.4, "max_drawdown": -0.19, "volatility": 0.21,
                           "cost_impact": 0.09, "turnover": 0.62, "exposure": 0.7}}


@router.get("/research-trigger")
def research_trigger_endpoint(q: str = "", entity: str = "", kind: str = "") -> dict:
    """P101 — 시장 이벤트 → 연구 트리거 → Opportunity → 가설(연구 태스크 체인). **트레이드 신호 아님.**"""
    def _run():
        if not (q or entity):
            return {"note": "이벤트/개체(q 또는 entity)를 입력하세요.", "trigger": {}}
        from jarvis.research_workflow.research_trigger import dispatch
        return dispatch({"kind": kind or "news", "entity": entity, "text": q})
    return _safe(_run, {"trigger": {}}) or {}


@router.get("/strategy-lifecycle")
def strategy_lifecycle_endpoint() -> dict:
    """P105 — 전략 연구 생애주기 보드(DISCOVERED→…→ARCHIVED). 기존 원장 파생. **연구 상태만.**"""
    from jarvis.research_workflow.strategy_lifecycle import board
    return _safe(board, {"strategies": [], "lifecycle": []}) or {}


@router.get("/research-ops-events")
def research_ops_events_endpoint() -> dict:
    """P107 — 연구 운영 이벤트(가설·백테스트·검증실패·페이퍼괴리·사람검토). 기존 이벤트 계층 파생."""
    from jarvis.research_workflow.ops_events import ops_events
    return _safe(lambda: ops_events(), {"events": [], "count": 0}) or {}


@router.get("/research-audit")
def research_audit_endpoint(strategy: str = "") -> dict:
    """P109 — 전략 연구 감사(origin·가설·실험·결과·실패·교훈). 기존 append-only 원장 재구성."""
    def _run():
        if not (strategy or "").strip():
            from jarvis.research_workflow.research_audit import audit_coverage
            return audit_coverage()
        from jarvis.research_workflow.research_audit import audit_strategy
        return audit_strategy(strategy)
    return _safe(_run, {"sections": {}}) or {}


@router.get("/v2-release")
def v2_release_endpoint() -> dict:
    """P110 — Jarvis v2.0 릴리스 검증: 완전 루프 + 안전 점검(거래·집행 없음). READ ONLY."""
    from jarvis.research_workflow.release_validation import validate_release
    return _safe(validate_release, {"release_ready": False, "loop_steps": []}) or {}


@router.get("/validation-loop")
def validation_loop(strategy: str = "") -> dict:
    """P101-110 통합 — Research Validation Dashboard 표면. 생애주기·검증·품질·리뷰큐. **READ ONLY.**

    lifecycle_board·ops events·audit 는 기존 원장에서 실데이터 파생. validation/quality 패널은 데이터
    소스 연결 전이라 교육용 데모(백테스트 성공/페이퍼 실패)로 시연. 자동 거래·집행 없음 — 사람이 모든 결정.
    """
    board = _safe(lambda: __import__("jarvis.research_workflow.strategy_lifecycle",
                                     fromlist=["board"]).board(), {"strategies": []}) or {}
    ops = _safe(lambda: __import__("jarvis.research_workflow.ops_events",
                                   fromlist=["ops_events"]).ops_events(), {"events": [], "review_queue": []}) or {}
    validation = _safe(lambda: __import__("jarvis.research_workflow.paper_validation",
                                          fromlist=["validate"]).validate(_DEMO_BT, _DEMO_PAPER), {}) or {}
    gap = _safe(lambda: __import__("jarvis.research_workflow.validation_gap",
                                   fromlist=["analyze_gap"]).analyze_gap(_DEMO_BT, _DEMO_PAPER), {}) or {}
    quality = _safe(lambda: __import__("jarvis.research_workflow.quality_monitor",
                                       fromlist=["evaluate"]).evaluate(_DEMO_BT), {}) or {}
    release = _safe(lambda: __import__("jarvis.research_workflow.release_validation",
                                       fromlist=["validate_release"]).validate_release(),
                    {"release_ready": False}) or {}
    audit = None
    if (strategy or "").strip():
        audit = _safe(lambda: __import__("jarvis.research_workflow.research_audit",
                                         fromlist=["audit_strategy"]).audit_strategy(strategy), None)
    return {"lifecycle_board": board,
            "validation_panel": {"backtest": _DEMO_BT["metrics"], "paper": _DEMO_PAPER["metrics"],
                                 "tracked_metrics": validation.get("tracked_metrics", {}),
                                 "status": validation.get("status"),
                                 "divergence_detected": validation.get("divergence_detected"),
                                 "cause": validation.get("cause"),
                                 "gaps": gap.get("gaps", {}), "possible_causes": gap.get("possible_causes", []),
                                 "is_demo": True},
            "quality_panel": {"quality_score": quality.get("quality_score"), "grade": quality.get("grade"),
                              "core_dimensions": quality.get("core_dimensions", {}),
                              "weaknesses": quality.get("weaknesses", []),
                              "missing_validations": quality.get("missing_validations", []),
                              "gate": quality.get("gate"), "is_demo": True},
            "review_queue": ops.get("review_queue", []),
            "ops_events": ops.get("events", [])[:20], "ops_by_type": ops.get("by_type", {}),
            "loop_status": {"loop_complete": release.get("loop_complete"),
                            "release_ready": release.get("release_ready"),
                            "safe": (release.get("safety") or {}).get("safe"),
                            "capabilities": release.get("capabilities", [])},
            "audit": audit,
            "is_advisory": True, "is_decision": False,
            "disclaimer": ("Research Validation Loop — READ ONLY. Market Event→Trigger→Hypothesis→"
                           "Experiment→Backtest→Paper→Validation→Risk→Memory. 검증/품질 패널은 데이터 소스 "
                           "연결 전 데모. 자동 거래·집행·자본배분 없음. 사람이 모든 투자 결정.")}


# ══════════════ Live Data Infrastructure & Autonomous Research Ops (P111-120) — READ ONLY ══════════════
@router.get("/data-capability-map")
def data_capability_map() -> dict:
    """P111/P112 — 데이터 역량 카탈로그 + provider 헬스(기존 벤더 클라이언트 재사용). READ ONLY."""
    from jarvis.research_workflow.providers import provider_registry
    return _safe(provider_registry, {"providers": [], "count": 0}) or {}


@router.get("/data-health")
def data_health() -> dict:
    """P118 — DataHealthReport(API availability·freshness·schema·missing·abnormal). 기존 품질 재사용."""
    from jarvis.research_workflow.data_quality import build_data_health
    return _safe(lambda: build_data_health(), {"overall_status": "LIMITED"}) or {}


@router.get("/research-feed")
def research_feed() -> dict:
    """P117 — 연구 피드 수집(데모): Source→Event→Trigger→Opportunity Queue. 중복 방지·health. 자동 투자 없음."""
    demo = {"market": [{"asset": "AAPL", "return": 0.08, "timestamp": "2026-01-03T09:30:00Z",
                        "source": "yfinance"}],
            "news": [{"text": "TSMC supplier expands production capacity", "entity": "TSMC"}]}
    from jarvis.research_workflow.research_feed import collect
    return _safe(lambda: collect(demo), {"collected": [], "opportunity_queue": []}) or {}


@router.get("/live-intelligence")
def live_intelligence() -> dict:
    """P119 — Live Intelligence 표면: Data Sources·Market Feed·Research Queue·Data Health. READ ONLY."""
    from jarvis.research_workflow.live_intelligence import build_live_intelligence
    return _safe(lambda: build_live_intelligence(demo=True), {"data_sources": {}, "market_feed": []}) or {}


@router.get("/operational-validation")
def operational_validation() -> dict:
    """P120 — 외부데이터→메모리 체인 검증 + 아키텍처 안전(새 DB/원장/실행엔진 없음). READ ONLY."""
    from jarvis.research_workflow.operational_validation import validate_operations
    return _safe(validate_operations, {"operational": False, "checks": []}) or {}


# ══════════════ Research Agent Operating System (P121-130) — READ ONLY, ANALYSIS ONLY ══════════════
@router.get("/agent-capability-map")
def agent_capability_map_endpoint() -> dict:
    """P121 — AgentCapabilityMap(역할 계층·목적·입출력·사용엔진). 분석 전용 에이전트. READ ONLY."""
    from jarvis.research_workflow.agent_capability import capability_map
    return _safe(capability_map, {"agents": [], "count": 0}) or {}


@router.get("/agent-validation")
def agent_validation_endpoint() -> dict:
    """P130 — 에이전트 시스템 검증(기존 엔진·중복없음·자율결정없음·메모리·대시보드) + 안전. READ ONLY."""
    from jarvis.research_workflow.agent_validation import validate_agents
    return _safe(validate_agents, {"validated": False, "checks": []}) or {}


@router.get("/agent-workspace")
def agent_workspace(objective: str = "", company: str = "") -> dict:
    """P129 통합 — Research Agents Workspace: active research·agent status·tasks·reports·critic·review queue.

    objective 있으면 다중 에이전트 연구 데모 실행(읽기전용, commit=False). 없으면 capability map + 데모 목표.
    자동 거래·집행·투자결정 없음 — 분석만, 사람이 모든 결정.
    """
    from jarvis.research_workflow.agent_capability import capability_map
    cap = _safe(capability_map, {"agents": []}) or {}
    obj = (objective or "").strip() or "momentum in KR equities under high volatility"
    wf = _safe(lambda: __import__("jarvis.research_workflow.multi_agent_workflow", fromlist=["run"])
               .run(obj, company=company), {}) or {}
    report = wf.get("report", {})
    review = wf.get("review", {})
    return {"agents": cap.get("agents", []), "role_hierarchy": cap.get("role_hierarchy", []),
            "active_research": {"objective": obj,
                                "pipeline": wf.get("pipeline", []),
                                "director_plan": wf.get("director_plan", {})},
            "agent_status": wf.get("stages", []),
            "current_tasks": (wf.get("director_plan", {}) or {}).get("assigned_agents", []),
            "generated_reports": [{"objective": obj, "confidence": report.get("confidence"),
                                   "sections": list(report.get("report", {})),
                                   "limitations": report.get("limitations", [])}] if report else [],
            "critic_feedback": {"verdict": review.get("verdict"), "blocks": review.get("blocks"),
                                "dimensions": review.get("dimensions", {}),
                                "quality": review.get("quality", {})},
            "human_review_queue": wf.get("human_review_queue", []),
            "specialist_memos": {k: v.get("memo_type", k) for k, v in
                                 (wf.get("specialist_memos", {}) or {}).items()},
            "is_demo": not objective,
            "is_advisory": True, "is_decision": False,
            "disclaimer": ("Research Agents — READ ONLY. Director→Analyst→Strategy→Critic→Writer. "
                           "분석 전용 에이전트(트레이딩/집행/결정 아님). 기존 엔진 재사용, 새 메모리 없음. "
                           "자동 거래·집행·자본배분 없음. 사람이 모든 투자 결정.")}


# ══════════════ Research Knowledge Intelligence Layer (P131-140) — READ ONLY, KNOWLEDGE ONLY ══════════════
@router.get("/memory-audit")
def memory_audit_endpoint() -> dict:
    """P131 — 메모리 감사(rmi_/memory_graph/recall/timeline/kg): 저장소·역량·누락연결. READ ONLY."""
    from jarvis.research_workflow.memory_audit import audit_memory
    return _safe(audit_memory, {"memory_stores": []}) or {}


@router.get("/knowledge-graph")
def knowledge_graph_endpoint(topic: str = "") -> dict:
    """P132 — 연구 지식 그래프(질문→가설→실험→결과→실패/성공→교훈). 기존 그래프 확장. READ ONLY."""
    from jarvis.research_workflow.knowledge_graph_upgrade import build_research_knowledge_graph
    return _safe(lambda: build_research_knowledge_graph(topic), {"nodes": [], "edges": []}) or {}


@router.get("/semantic-recall")
def semantic_recall_endpoint(q: str = "") -> dict:
    """P133 — 질문 → Research Context Package(경험·유사실패·과거결론·모순증거). READ ONLY."""
    def _run():
        if not (q or "").strip():
            return {"note": "질문(q)을 입력하세요.", "relevant_experiments": []}
        from jarvis.research_workflow.semantic_recall import recall_context
        return recall_context(q)
    return _safe(_run, {"relevant_experiments": []}) or {}


@router.get("/knowledge-conflicts")
def knowledge_conflicts_endpoint(topic: str = "") -> dict:
    """P135 — 지식 모순(works vs fails) Conflict Report. READ ONLY."""
    from jarvis.research_workflow.conflict_detection import detect_conflicts
    return _safe(lambda: detect_conflicts(topic=topic), {"conflicts": [], "count": 0}) or {}


@router.get("/knowledge-health")
def knowledge_health_endpoint() -> dict:
    """P139 — Knowledge Health Score(중복·노후·모순·근거누락). READ ONLY."""
    from jarvis.research_workflow.knowledge_quality import build_knowledge_health
    return _safe(build_knowledge_health, {"health_score": 0, "grade": "EMPTY"}) or {}


@router.get("/brain-validation")
def brain_validation_endpoint() -> dict:
    """P140 — 연구 두뇌 검증(회수·실패재사용·중복없음·에이전트지식·대시보드) + 안전. READ ONLY."""
    from jarvis.research_workflow.brain_validation import validate_brain
    return _safe(validate_brain, {"validated": False, "checks": []}) or {}


@router.get("/research-brain")
def research_brain(topic: str = "") -> dict:
    """P138 통합 — Research Brain Workspace: knowledge graph·past research·failure patterns·strategy/company
    memory·conflicts·lessons. **READ ONLY. 지식 시스템 전용, 자동 거래·집행 없음.**"""
    graph = _safe(lambda: __import__("jarvis.research_workflow.knowledge_graph_upgrade",
                                     fromlist=["build_research_knowledge_graph"])
                  .build_research_knowledge_graph(topic, limit=80), {"nodes": [], "edges": []}) or {}
    audit = _safe(lambda: __import__("jarvis.research_workflow.memory_audit",
                                     fromlist=["audit_memory"]).audit_memory(), {}) or {}
    conflicts = _safe(lambda: __import__("jarvis.research_workflow.conflict_detection",
                                         fromlist=["detect_conflicts"]).detect_conflicts(topic=topic),
                      {"conflicts": []}) or {}
    health = _safe(lambda: __import__("jarvis.research_workflow.knowledge_quality",
                                      fromlist=["build_knowledge_health"]).build_knowledge_health(), {}) or {}
    # 실패 패턴 — assistant.failure_intelligence 재사용
    fails = _safe(lambda: _failure_patterns(), {"by_category": {}, "top_category": None})
    # 과거 연구/교훈/전략·기업 메모리 — 그래프 노드에서 파생
    ntypes = graph.get("node_types", {})

    def _nodes(kind):
        return [n for n in graph.get("nodes", []) if n["type"] == kind][:20]

    return {"knowledge_graph": {"nodes": graph.get("nodes", []), "edges": graph.get("edges", []),
                                "node_count": graph.get("node_count", 0),
                                "node_types": ntypes, "research_chain": graph.get("research_chain", [])},
            "past_research": _nodes("Experiment") + _nodes("Question"),
            "failure_patterns": fails,
            "strategy_memory": _nodes("Strategy"),
            "company_memory": _nodes("Sector") + _nodes("MacroEvent"),
            "conflicts": conflicts.get("conflicts", []),
            "lessons": _nodes("Lesson"),
            "knowledge_health": {"health_score": health.get("health_score"), "grade": health.get("grade"),
                                 "issues": health.get("issues", {})},
            "entity_counts": audit.get("entity_counts", {}),
            "is_advisory": True, "is_decision": False,
            "disclaimer": ("Research Brain — READ ONLY. 질문→회수→분석→충돌검사→결과→교훈. 지식 시스템 전용. "
                           "기존 rmi_/그래프/recall 재사용, 새 DB/원장/메모리 없음. 사람이 모든 결정.")}


def _failure_patterns() -> dict:
    from jarvis.research_assistant.engine import ResearchAssistantEngine
    fi = ResearchAssistantEngine().failure_intelligence()
    d = fi.to_dict() if hasattr(fi, "to_dict") else dict(fi)
    return {"total_failures": d.get("total_failures", 0), "by_category": d.get("by_category", {}),
            "top_category": d.get("top_category"), "lessons": d.get("lessons", [])[:8]}


# ══════════════ Research Operations & Institutional Deployment (P141-150) — READ ONLY, ADVISORY ══════════════
@router.get("/research-schedule")
def research_schedule(cycle: str = "daily") -> dict:
    """P141 — 연구 운영 계획(daily/weekly/monthly): 태스크·배정·검토큐. 자동 투자 없음. READ ONLY."""
    from jarvis.research_workflow.research_scheduler import plan_cycle
    return _safe(lambda: plan_cycle(cycle), {"tasks": []}) or {}


@router.get("/morning-briefing")
def morning_briefing() -> dict:
    """P142 — Daily Market Brief(시장·레짐·이벤트·기회·리스크·교훈 + confidence·limitations). READ ONLY."""
    demo_events = [{"kind": "macro", "text": "CPI surprise"}, {"kind": "earnings", "text": "NVDA earnings"}]
    from jarvis.research_workflow.morning_briefing import generate
    return _safe(lambda: generate(events=demo_events), {"brief": {}}) or {}


@router.get("/company-monitor")
def company_monitor(company: str = "") -> dict:
    """P143 — CompanyUpdateReport(재무·실적·뉴스·소유 변화·영향·우선순위). 신호 아님. READ ONLY."""
    def _run():
        name = (company or "NVDA").strip()
        from jarvis.research_workflow.company_monitor import update
        return update(name, financials=[{"company": name, "expected": {"eps": 0.5},
                      "actual": {"eps": 0.62}}], headlines=[{"text": f"{name} product news", "entity": name}])
    return _safe(_run, {"events": []}) or {}


@router.get("/strategy-health")
def strategy_health_endpoint() -> dict:
    """P144 — 전략 건강 보드(성과·검증·레짐·리스크·과거). READ ONLY."""
    from jarvis.research_workflow.strategy_health import StrategyHealthMonitor
    return _safe(lambda: StrategyHealthMonitor().board(), {"strategies": []}) or {}


@router.get("/agent-performance")
def agent_performance_endpoint() -> dict:
    """P148 — Agent Performance Report(디렉터/분석/비평/작성 품질). 자율 자기수정 아님. READ ONLY."""
    from jarvis.research_workflow.agent_performance import report
    return _safe(lambda: report(objective="momentum research"), {"agents": {}}) or {}


@router.get("/research-workspace")
def research_workspace_endpoint(topic: str = "") -> dict:
    """P146 — 사람 연구 워크스페이스(inbox·review queue·agent outputs·history). 투자 승인·거래 없음. READ ONLY."""
    from jarvis.research_workflow.research_workspace import build_workspace
    return _safe(lambda: build_workspace(topic=topic), {"review_queue": []}) or {}


@router.get("/research-ops-validation")
def research_ops_validation() -> dict:
    """P150 — Jarvis Research OS v1.5 검증(스케줄러·에이전트·리포트·지식·사람검토·무중복·안전). READ ONLY."""
    from jarvis.research_workflow.ops_validation import validate_research_ops
    return _safe(validate_research_ops, {"operational": False, "checks": []}) or {}


@router.get("/research-organization")
def research_organization(topic: str = "") -> dict:
    """P149 통합 — Research Organization Dashboard: market·company·strategy·agent·knowledge·reports·review.
    **READ ONLY. 자문만, 자동 거래·집행·자본배분 없음. 사람이 모든 결정.**"""
    briefing = _safe(lambda: __import__("jarvis.research_workflow.morning_briefing", fromlist=["generate"])
                     .generate(events=[{"kind": "macro", "text": "CPI"}]), {}) or {}
    company = _safe(lambda: __import__("jarvis.research_workflow.company_monitor", fromlist=["update"])
                    .update("NVDA", financials=[{"company": "NVDA", "expected": {"eps": 0.5},
                            "actual": {"eps": 0.62}}]), {}) or {}
    health = _safe(lambda: __import__("jarvis.research_workflow.strategy_health",
                                      fromlist=["StrategyHealthMonitor"]).StrategyHealthMonitor().board(),
                   {"strategies": []}) or {}
    agents = _safe(lambda: __import__("jarvis.research_workflow.agent_performance", fromlist=["report"])
                   .report(objective="momentum research"), {}) or {}
    knowledge = _safe(lambda: __import__("jarvis.research_workflow.knowledge_quality",
                                         fromlist=["build_knowledge_health"]).build_knowledge_health(), {}) or {}
    workspace = _safe(lambda: __import__("jarvis.research_workflow.research_workspace",
                                         fromlist=["build_workspace"]).build_workspace(topic=topic), {}) or {}
    v15 = _safe(lambda: __import__("jarvis.research_workflow.ops_validation",
                                   fromlist=["validate_research_ops"]).validate_research_ops(),
                {"operational": False}) or {}
    brief = briefing.get("brief", {})
    return {"market_overview": {"regime": brief.get("2_current_regime", {}),
                                "opportunities": brief.get("4_research_opportunities", []),
                                "risk_factors": brief.get("5_risk_factors", []),
                                "confidence": briefing.get("confidence")},
            "company_monitoring": {"company": company.get("company"), "events": company.get("events", []),
                                   "impact": company.get("impact", {}),
                                   "research_priority": company.get("research_priority")},
            "strategy_health": {"strategies": health.get("strategies", []),
                                "review_needed_count": health.get("review_needed_count", 0)},
            "agent_status": {"agents": agents.get("agents", {}),
                             "overall_effectiveness": agents.get("overall_effectiveness")},
            "knowledge_health": {"health_score": knowledge.get("health_score"),
                                 "grade": knowledge.get("grade"), "issues": knowledge.get("issues", {})},
            "research_reports": workspace.get("agent_outputs", [])[:6],
            "review_queue": workspace.get("review_queue", []),
            "operational_status": {"operational": v15.get("operational"),
                                   "version": v15.get("version"),
                                   "capabilities": v15.get("capabilities", [])},
            "is_advisory": True, "is_decision": False,
            "disclaimer": ("Research Organization — READ ONLY. External Data→Opportunity→Agent Research→"
                           "Experiment→Validation→Knowledge Update→Improvement. 자문만, 자동 거래·집행·자본배분 "
                           "없음. 사람이 모든 투자 결정.")}


# ══════════════ Institutional Intelligence Expansion (P151-160) — READ ONLY, ADVISORY ══════════════
@router.get("/data-production")
def data_production_endpoint() -> dict:
    """P151 — DataProductionReport(provider availability·freshness·quality·lineage). 데이터 변형 없음. READ ONLY."""
    from jarvis.research_workflow.data_production import build_data_production
    return _safe(build_data_production, {"reports": []}) or {}


@router.get("/sector-intelligence")
def sector_intelligence_endpoint(sector: str = "semiconductor") -> dict:
    """P152 — SectorIntelligenceReport(핵심개체·이벤트·과거·리스크·연구질문). 투자 랭킹 아님. READ ONLY."""
    from jarvis.research_workflow.sector_intelligence import analyze_sector
    return _safe(lambda: analyze_sector(sector), {"key_entities": []}) or {}


@router.get("/macro-intelligence")
def macro_intelligence_endpoint() -> dict:
    """P153 — MacroContextReport(상태·지표·과거·영향자산·불확실성). 예측 아님. READ ONLY."""
    demo = {"fed_funds": 5.0, "cpi": 3.5, "unemployment": 4.2}
    from jarvis.research_workflow.macro_intelligence import build_macro_context
    return _safe(lambda: build_macro_context(indicators=demo), {"macro_state": "UNKNOWN"}) or {}


@router.get("/company-intelligence")
def company_intelligence_endpoint(entity: str = "TSMC") -> dict:
    """P154 — CompanyIntelligenceReport(관계·이벤트·재무·교훈·리스크). 매수/매도 신호 아님. READ ONLY."""
    def _run():
        name = (entity or "TSMC").strip()
        from jarvis.research_workflow.company_intelligence import analyze_company
        return analyze_company(name, financials=[{"company": name, "expected": {"eps": 0.5},
                               "actual": {"eps": 0.62}}], headlines=[{"text": f"{name} news", "entity": name}])
    return _safe(_run, {"relationships": {}}) or {}


@router.get("/research-context")
def research_context_endpoint(q: str = "", entity: str = "", sector: str = "") -> dict:
    """P155 — ResearchContextPackage(8섹션: 질문·환경·과거·기업·전략·리스크·모순·누락). READ ONLY."""
    def _run():
        if not (q or entity or sector):
            return {"note": "질문(q)/개체(entity)/섹터(sector)를 입력하세요.", "package": {}}
        from jarvis.research_workflow.research_context_engine import build_research_context
        return build_research_context(q, entity=entity, sector=sector)
    return _safe(_run, {"package": {}}) or {}


@router.get("/cross-asset")
def cross_asset_endpoint() -> dict:
    """P156 — CrossAssetReport(자산군 관계·상관·레짐·리스크 전이). 포트폴리오 배분 아님. READ ONLY."""
    demo = {"AAPL~SPY": 0.72, "GLD~DXY": -0.58, "TLT~SPY": -0.35}
    from jarvis.research_workflow.cross_asset_intelligence import build_cross_asset
    return _safe(lambda: build_cross_asset(correlations=demo), {"asset_classes": []}) or {}


@router.get("/institutional-memory")
def institutional_memory_endpoint() -> dict:
    """P157 — InstitutionalMemoryReport(테마·사이클·기간·성공/실패 스터디). 새 메모리 없음. READ ONLY."""
    from jarvis.research_workflow.institutional_memory_expansion import build_institutional_memory
    return _safe(build_institutional_memory, {"research_themes": []}) or {}


@router.get("/intelligence-quality")
def intelligence_quality_endpoint(topic: str = "momentum") -> dict:
    """P158 — IntelligenceQualityReport(data·evidence·historical·conflict·uncertainty → confidence). READ ONLY."""
    from jarvis.research_workflow.intelligence_quality import score_intelligence
    return _safe(lambda: score_intelligence(topic=topic), {"confidence": "LOW"}) or {}


@router.get("/intelligence-validation")
def intelligence_validation_endpoint() -> dict:
    """P160 — 기관 인텔리전스 검증(데이터·섹터·매크로·기업·컨텍스트·품질·무중복) + 안전. READ ONLY."""
    from jarvis.research_workflow.institutional_intelligence_validation import validate_intelligence
    return _safe(validate_intelligence, {"validated": False, "checks": []}) or {}


@router.get("/institutional-intelligence")
def institutional_intelligence(topic: str = "", sector: str = "semiconductor", entity: str = "TSMC") -> dict:
    """P159 통합 — Institutional Intelligence Dashboard: data health·market·sector·macro·company·knowledge·quality.
    **READ ONLY. 자문만, 자동 거래·집행·자본배분 없음. 사람이 모든 결정.**"""
    dp = _safe(lambda: __import__("jarvis.research_workflow.data_production",
                                  fromlist=["build_data_production"]).build_data_production(), {}) or {}
    regime = _safe(lambda: __import__("jarvis.research_workflow.regime", fromlist=["detect_regime"])
                   .detect_regime({}), {"regime": "UNKNOWN"}) or {}
    sec = _safe(lambda: __import__("jarvis.research_workflow.sector_intelligence",
                                   fromlist=["analyze_sector"]).analyze_sector(sector), {}) or {}
    mac = _safe(lambda: __import__("jarvis.research_workflow.macro_intelligence",
                                   fromlist=["build_macro_context"])
                .build_macro_context(indicators={"fed_funds": 5.0, "cpi": 3.5, "unemployment": 4.2}), {}) or {}
    co = _safe(lambda: __import__("jarvis.research_workflow.company_intelligence", fromlist=["analyze_company"])
               .analyze_company(entity), {}) or {}
    knowledge = _safe(lambda: __import__("jarvis.research_workflow.knowledge_quality",
                                         fromlist=["build_knowledge_health"]).build_knowledge_health(), {}) or {}
    quality = _safe(lambda: __import__("jarvis.research_workflow.intelligence_quality",
                                       fromlist=["score_intelligence"]).score_intelligence(topic=topic or sector),
                    {}) or {}
    v = _safe(lambda: __import__("jarvis.research_workflow.institutional_intelligence_validation",
                                 fromlist=["validate_intelligence"]).validate_intelligence(),
              {"validated": False}) or {}
    return {"data_production_health": {"overall_status": dp.get("overall_status"),
                                       "available_count": dp.get("available_count"),
                                       "count": dp.get("count"), "average_quality": dp.get("average_quality"),
                                       "reports": dp.get("reports", [])[:12]},
            "market_intelligence": {"regime": regime.get("regime"), "labels": regime.get("labels", [])},
            "sector_intelligence": {"sector": sec.get("sector"), "key_entities": sec.get("key_entities", []),
                                    "risk_factors": sec.get("risk_factors", []),
                                    "research_questions": sec.get("research_questions", [])},
            "macro_context": {"macro_state": mac.get("macro_state"), "indicators": mac.get("indicators", {}),
                              "affected_assets": mac.get("affected_assets", []),
                              "uncertainty": mac.get("uncertainty")},
            "company_intelligence": {"entity": co.get("entity"), "relationships": co.get("relationships", {}),
                                     "risks": co.get("risks", [])},
            "knowledge_context": {"health_score": knowledge.get("health_score"),
                                  "grade": knowledge.get("grade")},
            "quality_scores": {"confidence": quality.get("confidence"),
                               "dimensions": quality.get("dimensions", {}),
                               "reliability": quality.get("reliability_score")},
            "validation": {"validated": v.get("validated"), "capabilities": v.get("capabilities", [])},
            "is_advisory": True, "is_decision": False,
            "disclaimer": ("Institutional Intelligence — READ ONLY. 시장·섹터·매크로·기업·지식·품질 통합 컨텍스트. "
                           "예측/랭킹/배분 아님. 자동 거래·집행 없음. 사람이 모든 투자 결정.")}


# ══════════════ Institutional Committee & Production Readiness (P161-170) — READ ONLY, ADVISORY ══════════════
@router.get("/committee-packet")
def committee_packet_endpoint(q: str = "") -> dict:
    """P161 — CommitteePacket(요약·증거·리스크·반대시각·신뢰도·한계·사람질문). BUY/SELL 없음. READ ONLY."""
    def _run():
        if not (q or "").strip():
            return {"note": "연구 질문(q)을 입력하세요.", "questions_for_human": []}
        from jarvis.research_workflow.investment_committee import build_committee_packet
        return build_committee_packet(q)
    return _safe(_run, {"questions_for_human": []}) or {}


@router.get("/debate")
def debate_endpoint(q: str = "") -> dict:
    """P162 — DebateReport(강세·약세·리스크·대안·누락·역사반례). 예측 아님. READ ONLY."""
    def _run():
        if not (q or "").strip():
            return {"note": "연구 질문(q)을 입력하세요."}
        from jarvis.research_workflow.debate_engine import build_debate
        return build_debate(q)
    return _safe(_run, {}) or {}


@router.get("/conviction")
def conviction_endpoint(topic: str = "momentum") -> dict:
    """P163 — ResearchConvictionReport(6요인 → LOW/MEDIUM/HIGH). 투자 등급 아님. READ ONLY."""
    from jarvis.research_workflow.conviction_framework import build_conviction
    return _safe(lambda: build_conviction(topic), {"conviction_level": "LOW"}) or {}


@router.get("/portfolio-research")
def portfolio_research_endpoint() -> dict:
    """P164 — PortfolioResearchView(노출·중첩·상관·집중·시나리오). 배분 제안 아님. READ ONLY."""
    from jarvis.research_workflow.portfolio_research_view import build_portfolio_research
    return _safe(lambda: build_portfolio_research(correlations={"AAPL~SPY": 0.72, "GLD~DXY": -0.58}),
                 {"strategy_health": []}) or {}


@router.get("/decision-center")
def decision_center_endpoint(q: str = "") -> dict:
    """P165 — Human Decision Center(committee packet·decision log·follow-up·archive). 투자 승인·거래 없음. READ ONLY."""
    from jarvis.research_workflow.human_decision_center import build_decision_center
    return _safe(lambda: build_decision_center(q), {"decision_log": []}) or {}


@router.get("/production-status")
def production_status_endpoint() -> dict:
    """P166 — ProductionStatusReport(7 컴포넌트 severity OK/WARNING/CRITICAL). READ ONLY."""
    from jarvis.research_workflow.production_monitor import build_production_status
    return _safe(build_production_status, {"overall_severity": "UNKNOWN", "components": []}) or {}


@router.get("/operational-metrics")
def operational_metrics_endpoint() -> dict:
    """P167 — OperationalMetricsReport(처리량·지연·활용·가용성·신선도·완료·백로그). READ ONLY."""
    from jarvis.research_workflow.operational_metrics import build_operational_metrics
    return _safe(build_operational_metrics, {"metrics": {}}) or {}


@router.get("/governance")
def governance_endpoint() -> dict:
    """P168 — GovernanceReport(권한·감사·무결성·체크포인트·아키텍처·안전). READ ONLY."""
    from jarvis.research_workflow.governance import build_governance
    return _safe(build_governance, {"governance": "REVIEW_REQUIRED", "checks": []}) or {}


@router.get("/system-validation")
def system_validation_endpoint() -> dict:
    """P169 — 전체 시스템 검증(워크플로·위원회·거버넌스·모니터링·지표·대시보드·무중복). READ ONLY."""
    from jarvis.research_workflow.system_validation import validate_system
    return _safe(validate_system, {"validated": False, "checks": []}) or {}


@router.get("/release-v20")
def release_v20_endpoint() -> dict:
    """P170 — Release Readiness Report(v2.0, 아키텍처 동결). READ ONLY."""
    from jarvis.research_workflow.release_v20 import build_release_report
    return _safe(build_release_report, {"release_ready": False}) or {}


@router.get("/production-readiness")
def production_readiness(q: str = "Does momentum work in KR equities?") -> dict:
    """P161-170 통합 — Committee & Production dashboard: overview·committee·debate·conviction·portfolio·
    governance·production·metrics·review queue. **READ ONLY. 자문만, 거래·집행·배분·승인 없음. 사람이 결정.**"""
    committee = _safe(lambda: __import__("jarvis.research_workflow.investment_committee",
                                         fromlist=["build_committee_packet"]).build_committee_packet(q), {}) or {}
    debate = _safe(lambda: __import__("jarvis.research_workflow.debate_engine", fromlist=["build_debate"])
                   .build_debate(q), {}) or {}
    conviction = _safe(lambda: __import__("jarvis.research_workflow.conviction_framework",
                                          fromlist=["build_conviction"]).build_conviction(q), {}) or {}
    portfolio = _safe(lambda: __import__("jarvis.research_workflow.portfolio_research_view",
                                         fromlist=["build_portfolio_research"])
                      .build_portfolio_research(correlations={"AAPL~SPY": 0.72}), {}) or {}
    governance = _safe(lambda: __import__("jarvis.research_workflow.governance", fromlist=["build_governance"])
                       .build_governance(), {}) or {}
    production = _safe(lambda: __import__("jarvis.research_workflow.production_monitor",
                                         fromlist=["build_production_status"]).build_production_status(), {}) or {}
    metrics = _safe(lambda: __import__("jarvis.research_workflow.operational_metrics",
                                       fromlist=["build_operational_metrics"]).build_operational_metrics(), {}) or {}
    release = _safe(lambda: __import__("jarvis.research_workflow.release_v20", fromlist=["build_release_report"])
                    .build_release_report(), {}) or {}
    dc = _safe(lambda: __import__("jarvis.research_workflow.human_decision_center",
                                  fromlist=["build_decision_center"]).build_decision_center(q), {}) or {}
    return {"institutional_overview": {"version": release.get("version"),
                                       "release_ready": release.get("release_ready"),
                                       "architecture_frozen": release.get("architecture_frozen"),
                                       "capabilities": [c["capability"] for c in release.get("capability_matrix", [])]},
            "committee_packet": {"research_summary": committee.get("research_summary"),
                                 "confidence": committee.get("confidence"),
                                 "limitations": committee.get("limitations", []),
                                 "questions_for_human": committee.get("questions_for_human", []),
                                 "risk_summary": committee.get("risk_summary", {}),
                                 "alternative_views": committee.get("alternative_views", {})},
            "debate": {"bull_case": debate.get("bull_case", {}), "bear_case": debate.get("bear_case", {}),
                       "risk_case": debate.get("risk_case", {}),
                       "historical_counterexamples": debate.get("historical_counterexamples", [])},
            "conviction": {"level": conviction.get("conviction_level"),
                           "score": conviction.get("conviction_score"),
                           "factors": conviction.get("factors", {})},
            "portfolio_research": {"strategy_health": portfolio.get("strategy_health", []),
                                   "factor_exposure": portfolio.get("factor_exposure", {}),
                                   "concentration": portfolio.get("concentration", {}),
                                   "correlation": portfolio.get("correlation", [])},
            "governance_status": {"governance": governance.get("governance"),
                                  "passed": governance.get("passed"),
                                  "checks": governance.get("checks", [])},
            "production_health": {"overall_severity": production.get("overall_severity"),
                                  "components": production.get("components", []),
                                  "counts": production.get("counts", {})},
            "operational_metrics": metrics.get("metrics", {}),
            "review_queue": dc.get("follow_up_research", []),
            "is_advisory": True, "is_decision": False,
            "disclaimer": ("Committee & Production — READ ONLY. 위원회·토론·확신도·거버넌스·모니터링. "
                           "BUY/SELL/EXECUTE/ALLOCATE 없음. 브로커·자본배분 없음. 모든 투자 결정은 사람.")}


# ── P171-180 Autonomous Research Intelligence Enhancement (READ ONLY) ──────────
@router.get("/research-intelligence")
def research_intelligence(q: str = "Does momentum work in KR equities?") -> dict:
    """P171-180 통합 — 창의적 가설·탐색트리·연속큐·실험우선순위·확장·성찰·계획·협업·생산성·검증.
    **READ ONLY. 자문만, 연구 자동 실행 없음, 자율 승인 없음. 모든 결정은 사람.**"""
    creative = _safe(lambda: __import__("jarvis.research_workflow.creative_hypothesis",
                                        fromlist=["discover_hypotheses"]).discover_hypotheses(q, limit=8), {}) or {}
    search = _safe(lambda: __import__("jarvis.research_workflow.research_search",
                                      fromlist=["build_search_space"]).build_search_space(q, top_k=10), {}) or {}
    queue = _safe(lambda: __import__("jarvis.research_workflow.continuous_queue",
                                     fromlist=["build_continuous_queue"]).build_continuous_queue(topic=q), {}) or {}
    prioritized = _safe(lambda: __import__("jarvis.research_workflow.experiment_prioritization",
                                           fromlist=["prioritize_experiments"]).prioritize_experiments(topic=q, limit=8), {}) or {}
    planning = _safe(lambda: __import__("jarvis.research_workflow.research_planning",
                                        fromlist=["build_research_plan"]).build_research_plan(topic=q), {}) or {}
    productivity = _safe(lambda: __import__("jarvis.research_workflow.productivity_optimization",
                                            fromlist=["build_productivity_report"]).build_productivity_report(), {}) or {}
    reflection = _safe(lambda: __import__("jarvis.research_workflow.self_reflection",
                                          fromlist=["reflect_on_cycle"]).reflect_on_cycle(), {}) or {}
    autonomy = _safe(lambda: __import__("jarvis.research_workflow.autonomy_validation",
                                        fromlist=["validate_autonomy"]).validate_autonomy(), {}) or {}
    return {"query": q,
            "creative_hypotheses": {"count": creative.get("hypothesis_count", 0),
                                    "diversity": creative.get("diversity", {}),
                                    "hypotheses": creative.get("hypotheses", [])[:8]},
            "research_search": {"surfaced_count": search.get("surfaced_count", 0),
                                "merged_duplicates": search.get("merged_duplicates", 0),
                                "candidates": search.get("highest_value_candidates", [])[:8]},
            "continuous_queue": {"queue_size": queue.get("queue_size", 0),
                                 "by_source": queue.get("by_source", {}),
                                 "backlog": queue.get("backlog", [])[:8],
                                 "recommended_next": queue.get("recommended_next", {})},
            "experiment_prioritization": {"coverage_context": prioritized.get("coverage_context", {}),
                                          "recommendations": prioritized.get("recommendations", [])[:8]},
            "research_planning": planning.get("plans", {}),
            "productivity": {"metrics": productivity.get("metrics", {}),
                             "recommendations": productivity.get("recommendations", [])},
            "self_reflection": reflection.get("reflection", {}),
            "autonomy_validation": {"validated": autonomy.get("validated"),
                                    "checks": autonomy.get("checks", []),
                                    "reuse_count": autonomy.get("reuse_analysis", {}).get("reuse_count"),
                                    "duplicated_logic": autonomy.get("duplicated_logic", []),
                                    "remaining_limitations": autonomy.get("remaining_limitations", [])},
            "is_advisory": True, "is_decision": False,
            "disclaimer": ("Autonomous Research Intelligence — READ ONLY. 창의적 가설·탐색·큐·우선순위·확장·"
                           "성찰·계획·협업·생산성. 연구 자동 실행 없음, 자율 승인 없음, 새 아키텍처 없음. "
                           "BUY/SELL/EXECUTE/ALLOCATE 없음. 모든 결정은 사람.")}


# ── P181-200 Autonomous Research Discovery & Validation Loop v3.0 (READ ONLY) ──
@router.get("/autonomous-research")
def autonomous_research(q: str = "Does momentum work in KR equities?") -> dict:
    """P181-200 통합 — 연구 사이클·시장관찰·가설·실험큐·검증·랭킹·사람 검토큐·지표·릴리스 v3.0.
    **READ ONLY. 연구 자동화 ON, 실행 OFF. 자동 백테스트 없음, WAITING_HUMAN 체크포인트 유지. 모든 결정은 사람.**"""
    cycle = _safe(lambda: __import__("jarvis.research_workflow.research_cycle",
                                     fromlist=["run_cycle"]).run_cycle(q), {}) or {}
    obs = _safe(lambda: __import__("jarvis.research_workflow.market_observation",
                                   fromlist=["observe_market"]).observe_market(), {}) or {}
    disc = _safe(lambda: __import__("jarvis.research_workflow.hypothesis_discovery",
                                    fromlist=["discover_research"]).discover_research(q, limit=8), {}) or {}
    research_hyps = disc.get("research_hypotheses", [])
    prio = _safe(lambda: __import__("jarvis.research_workflow.research_priority",
                                    fromlist=["prioritize_research"]).prioritize_research(research_hyps, limit=8), {}) or {}
    gate = _safe(lambda: __import__("jarvis.research_workflow.research_gate",
                                    fromlist=["build_approval_queue"]).build_approval_queue(
                                        prio.get("research_queue", []), limit=8), {}) or {}
    brief = _safe(lambda: __import__("jarvis.research_workflow.research_brief",
                                     fromlist=["build_research_brief"]).build_research_brief(topic=q), {}) or {}
    metrics = _safe(lambda: __import__("jarvis.research_workflow.research_metrics_v3",
                                       fromlist=["build_research_metrics"]).build_research_metrics(topic=q), {}) or {}
    loopval = _safe(lambda: __import__("jarvis.research_workflow.autonomous_validation_v3",
                                       fromlist=["validate_loop"]).validate_loop(), {}) or {}
    audit = _safe(lambda: __import__("jarvis.research_workflow.autonomous_validation_v3",
                                     fromlist=["audit_production"]).audit_production(), {}) or {}
    release = _safe(lambda: __import__("jarvis.research_workflow.release_v30",
                                       fromlist=["build_release_report_v30"]).build_release_report_v30(), {}) or {}
    return {"query": q,
            "cycle_status": {"state": cycle.get("state"),
                             "history": cycle.get("history", []),
                             "human_checkpoint_pending": cycle.get("human_checkpoint_pending"),
                             "auto_backtest": cycle.get("auto_backtest")},
            "opportunities": {"count": obs.get("opportunity_count", 0),
                              "by_type": obs.get("by_type", {}),
                              "items": obs.get("opportunities", [])[:6]},
            "hypotheses": {"count": disc.get("hypothesis_count", 0),
                           "with_why_different": disc.get("with_why_different", 0),
                           "items": research_hyps[:6]},
            "experiment_queue": {"queue_size": gate.get("queue_size", 0),
                                 "requests": gate.get("requests", [])[:6],
                                 "available_actions": gate.get("available_actions", []),
                                 "forbidden_actions": gate.get("forbidden_actions", [])},
            "research_ranking": {"queue": prio.get("research_queue", [])[:6],
                                 "formula": prio.get("formula")},
            "validation_results": brief.get("sections", {}).get("validation_results", {}),
            "human_review_queue": {"pending": gate.get("queue_size", 0),
                                   "actions": gate.get("available_actions", [])},
            "metrics": metrics.get("metrics", {}),
            "loop_validation": {"validated": loopval.get("validated"),
                                "checks": loopval.get("checks", [])},
            "production_audit": {"audited": audit.get("audited"),
                                 "ledger_count": audit.get("ledger_count"),
                                 "duplicate_logic": audit.get("duplicate_logic", [])},
            "release": {"version": release.get("version"), "status": release.get("status"),
                        "research_automation": release.get("research_automation"),
                        "execution": release.get("execution"),
                        "decision_authority": release.get("decision_authority"),
                        "production_ready": release.get("production_ready"),
                        "capabilities": release.get("capabilities", {})},
            "is_advisory": True, "is_decision": False,
            "disclaimer": ("Autonomous Research OS v3.0 — READ ONLY. 관찰→기회→가설→실험제안→사람 체크포인트→"
                           "외부테스트→검증→랭킹→지식→다음 사이클. 연구 자동화 ON, 실행 OFF, 자동 백테스트 없음. "
                           "BUY/SELL/EXECUTE/ALLOCATE 없음. 모든 결정은 사람.")}


# ── Data Integration — 우선순위 소스 연결 상태 + 예측 커버리지 (READ ONLY) ──
@router.get("/data-connection")
def data_connection() -> dict:
    """KRX/OpenDART/SEC-EDGAR 연결 상태 — availability·freshness·quality·lineage + 예측 커버리지.
    **READ ONLY. 데이터만, 지능 추가 없음. 기존 provider 재사용. 실행·포트폴리오 없음.**"""
    status = _safe(lambda: __import__("jarvis.research_workflow.data_connection",
                                      fromlist=["data_connection_status"]).data_connection_status(), {}) or {}
    coverage = _safe(lambda: __import__("jarvis.research_workflow.prediction_coverage_audit",
                                        fromlist=["build_coverage_audit"]).build_coverage_audit(), {}) or {}
    score = _safe(lambda: __import__("jarvis.research_workflow.research_validation_score",
                                     fromlist=["build_validation_score"]).build_validation_score(), {}) or {}
    return {"data_sources": {"priority": status.get("priority_sources", []),
                             "sources": status.get("sources", []),
                             "dimensions_known": status.get("dimensions_known"),
                             "dimensions_unknown": status.get("dimensions_unknown"),
                             "known_pct": status.get("known_pct"),
                             "objectives": status.get("objectives", [])},
            "prediction_coverage": {"total": coverage.get("total_predictions"),
                                    "by_source": coverage.get("source_distribution", {}),
                                    "by_confidence": coverage.get("confidence_distribution", {}),
                                    "missing_invalidation_pct": coverage.get("missing_invalidation_pct"),
                                    "missing_horizon_pct": coverage.get("missing_horizon_pct"),
                                    "pending": coverage.get("pending"), "evaluated": coverage.get("evaluated")},
            "validation_score": {"status": score.get("status"), "score": score.get("score"),
                                 "graded_scorable": score.get("graded_scorable"),
                                 "needed": score.get("needed")},
            "is_advisory": True, "is_decision": False,
            "disclaimer": ("Data Connection — READ ONLY. 우선순위 소스 availability·freshness·quality·lineage. "
                           "키 없으면 정직하게 NEEDS_CREDENTIALS. 데이터만 개선, 지능/실행/포트폴리오 없음.")}
