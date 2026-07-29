"""관계 추출 (P4) — P3 projection + 노드집합 → 그래프 엣지.

끝점 노드가 없는 엣지는 skip(missing references tolerate). 결정적.
"""
from __future__ import annotations

from jarvis.knowledge.schema import node_id


def build_edges(p3, agg: dict, node_ids: set) -> tuple[list, int]:
    """(edges, skipped). edge = (source_id, relation, target_id, metadata_dict)."""
    edges: list = []
    skipped = 0

    def link(src, rel, tgt, meta=None):
        nonlocal skipped
        if src in node_ids and tgt in node_ids:
            edges.append((src, rel, tgt, meta or {}))
        else:
            skipped += 1

    # Strategy → derived_from → Experiment (id 일치)
    for r in p3.query("SELECT id FROM strategies"):
        sid = r["id"]
        exp = node_id("Experiment", sid)
        if exp in node_ids:
            link(node_id("Strategy", sid), "derived_from", exp)

    # Experiment → tested → Hypothesis / failed_because → FailureReason / used → Dataset
    for eid, a in agg.items():
        exp = node_id("Experiment", eid)
        link(exp, "tested", node_id("Hypothesis", eid))
        for cat in sorted(a["failure_cats"]):
            link(exp, "failed_because", node_id("FailureReason", cat))
        for ds in sorted(a["datasets"]):
            link(exp, "used", node_id("Dataset", ds))

    # Strategy → generated → Signal
    sig_by_strat: dict = {}
    for r in p3.query("SELECT id,strategy_id,timestamp FROM signals"):
        sig = node_id("Signal", str(r["id"]))
        link(node_id("Strategy", r["strategy_id"]), "generated", sig)
        sig_by_strat.setdefault(r["strategy_id"], []).append((sig, r["timestamp"]))

    # Signal → contributed_to → Allocation (strategy_id 매칭)
    alloc_rows = p3.query("SELECT id,strategy_id,timestamp FROM allocations")
    for ar in alloc_rows:
        alloc = node_id("Allocation", str(ar["id"]))
        for sig, _ts in sig_by_strat.get(ar["strategy_id"], []):
            link(sig, "contributed_to", alloc)

    # Allocation → produced → PortfolioDecision (timestamp 매칭)
    pdec_by_ts: dict = {}
    for r in p3.query("SELECT id,timestamp,regime FROM portfolio_decisions"):
        pdec_by_ts.setdefault(r["timestamp"], []).append((node_id("PortfolioDecision", str(r["id"])),
                                                          r["regime"]))
    for ar in alloc_rows:
        for pdec, regime in pdec_by_ts.get(ar["timestamp"], []):
            link(node_id("Allocation", str(ar["id"])), "produced", pdec)
            # Strategy → affected_by → Regime (배분→결정 레짐 경유)
            if regime:
                link(node_id("Strategy", ar["strategy_id"]), "affected_by",
                     node_id("Regime", regime))

    # 중복 제거(결정적)
    seen = set()
    uniq = []
    for e in edges:
        k = (e[0], e[1], e[2])
        if k not in seen:
            seen.add(k)
            uniq.append(e)
    return uniq, skipped
