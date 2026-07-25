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
