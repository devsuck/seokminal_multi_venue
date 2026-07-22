"""엔티티 추출 (P4) — P3 projection SQLite → 그래프 노드.

결정적. 손상 metadata JSON은 안전 skip. 빈 소스 테이블은 0 노드(tolerate).
"""
from __future__ import annotations

import json

from jarvis.knowledge.schema import (
    FAILED_STATUSES,
    datasets_from_meta,
    failure_category,
    node_id,
)

_METRIC_KEYS = ("net", "net_pnl", "net_base", "sharpe", "random_percentile", "percentile")


def _loads(s):
    if not s:
        return {}
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}


def aggregate_experiments(p3) -> dict:
    """experiments(run당 1행) → id별 집계. 결정적."""
    rows = p3.query("SELECT id,hypothesis,result,status,created_at,metadata FROM experiments")
    agg: dict = {}
    for r in rows:
        eid = r["id"]
        if not eid:
            continue
        meta = _loads(r["metadata"])
        a = agg.get(eid)
        if a is None:
            a = agg[eid] = {"id": eid, "hypothesis": r["hypothesis"] or eid, "n_runs": 0,
                            "latest_ts": "", "latest_status": None, "latest_result": None,
                            "failure_cats": set(), "datasets": set(), "metrics": {}}
        a["n_runs"] += 1
        ts = r["created_at"] or ""
        if ts >= a["latest_ts"]:
            a["latest_ts"] = ts
            a["latest_status"] = r["status"]
            a["latest_result"] = r["result"]
            a["metrics"] = {k: meta[k] for k in _METRIC_KEYS if meta.get(k) is not None}
        if r["status"] in FAILED_STATUSES:
            a["failure_cats"].add(failure_category(r["result"], meta.get("reason"), r["status"]))
        for d in datasets_from_meta(meta):
            a["datasets"].add(d)
    return agg


def build_nodes(p3, agg: dict) -> dict:
    """모든 노드 dict{id: node}. node = (id,type,name,metadata,created_at)."""
    nodes: dict = {}

    def add(ntype, key, name, meta=None, created_at=None):
        nid = node_id(ntype, key)
        nodes[nid] = {"id": nid, "type": ntype, "name": name,
                      "metadata": meta or {}, "created_at": created_at}
        return nid

    # Strategy
    for r in p3.query("SELECT id,name,status,family,created_at,config_hash FROM strategies"):
        add("Strategy", r["id"], r["name"],
            {"status": r["status"], "family": r["family"], "config_hash": r["config_hash"]},
            r["created_at"])

    # Experiment + Hypothesis (id별 집계)
    fail_cats, datasets, metric_names = set(), set(), set()
    for eid, a in agg.items():
        add("Experiment", eid, a["hypothesis"],
            {"status": a["latest_status"], "result": a["latest_result"],
             "n_runs": a["n_runs"], "metrics": a["metrics"]}, a["latest_ts"] or None)
        add("Hypothesis", eid, a["hypothesis"])
        fail_cats |= a["failure_cats"]
        datasets |= a["datasets"]
        metric_names |= set(a["metrics"])

    for cat in sorted(fail_cats):
        add("FailureReason", cat, cat)
    for ds in sorted(datasets):
        add("Dataset", ds, ds)
    for m in sorted(metric_names):
        add("Metric", m, m)

    # Regime (portfolio_decisions.regime — 현재 희소, tolerate)
    for r in p3.query("SELECT DISTINCT regime FROM portfolio_decisions WHERE regime IS NOT NULL"):
        if r["regime"]:
            add("Regime", r["regime"], r["regime"])

    # Signal / Allocation / PortfolioDecision (소스 있으면)
    for r in p3.query("SELECT id,strategy_id,instrument,direction,strength,timestamp FROM signals"):
        add("Signal", str(r["id"]), f"{r['strategy_id']}:{r['instrument']}",
            {"strategy_id": r["strategy_id"], "instrument": r["instrument"],
             "direction": r["direction"], "strength": r["strength"]}, r["timestamp"])
    for r in p3.query("SELECT id,strategy_id,weight,risk_contribution,timestamp FROM allocations"):
        add("Allocation", str(r["id"]), r["strategy_id"],
            {"strategy_id": r["strategy_id"], "weight": r["weight"],
             "risk_contribution": r["risk_contribution"]}, r["timestamp"])
    for r in p3.query("SELECT id,decision,reason,timestamp,regime,risk_level FROM portfolio_decisions"):
        add("PortfolioDecision", str(r["id"]), r["decision"],
            {"reason": r["reason"], "regime": r["regime"], "risk_level": r["risk_level"]},
            r["timestamp"])

    return nodes
