"""Knowledge Queries (P4) — 읽기 전용 그래프 쿼리. graph.db 없으면 빈 결과."""
from __future__ import annotations

import json

from jarvis.db.sqlite import Database
from jarvis.knowledge.schema import STRATEGY_FAILED, graph_db_path, graph_exists, node_id


def _ro() -> Database | None:
    if not graph_exists():
        return None
    return Database(graph_db_path(), read_only=True)


def _meta(row) -> dict:
    try:
        return json.loads(row["metadata"]) if row.get("metadata") else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def find_failed_strategies() -> list[dict]:
    """실패 상태이거나 failed_because 경험을 가진 전략."""
    db = _ro()
    if db is None:
        return []
    out = {}
    for n in db.query("SELECT * FROM nodes WHERE type='Strategy'"):
        m = _meta(n)
        if m.get("status") in STRATEGY_FAILED:
            out[n["id"]] = {"strategy": n["name"], "status": m.get("status"), "via": "status"}
    # derived_from → failed_because
    linked = db.query("""
        SELECT s.name AS strat, fr.name AS reason FROM edges e1
        JOIN nodes s   ON s.id = e1.source_id AND s.type='Strategy'
        JOIN edges e2  ON e2.source_id = e1.target_id AND e2.relation='failed_because'
        JOIN nodes fr  ON fr.id = e2.target_id
        WHERE e1.relation='derived_from'""")
    for r in linked:
        sid = node_id("Strategy", r["strat"])
        row = out.setdefault(sid, {"strategy": r["strat"], "status": None, "via": "experiment"})
        row.setdefault("reasons", set())
        if isinstance(row.get("reasons"), set):
            row["reasons"].add(r["reason"])
    db.close()
    return [{**v, "reasons": sorted(v["reasons"])} if isinstance(v.get("reasons"), set) else v
            for v in out.values()]


def find_related_experiments(strategy: str) -> list[dict]:
    db = _ro()
    if db is None:
        return []
    out = db.query("""
        SELECT ex.id, ex.name, ex.metadata FROM edges e
        JOIN nodes ex ON ex.id = e.target_id AND ex.type='Experiment'
        WHERE e.relation='derived_from' AND e.source_id=?""", (node_id("Strategy", strategy),))
    db.close()
    return [{"experiment": r["id"].split(":", 1)[1], "hypothesis": r["name"], **_meta(r)}
            for r in out]


def strategy_lineage(strategy: str) -> dict:
    """Strategy → Experiment → {Hypothesis, FailureReason, Dataset} 계보."""
    db = _ro()
    if db is None:
        return {}
    sid = node_id("Strategy", strategy)
    snode = db.query("SELECT * FROM nodes WHERE id=?", (sid,))
    if not snode:
        db.close()
        return {}
    exps = db.query("SELECT target_id FROM edges WHERE source_id=? AND relation='derived_from'", (sid,))
    lineage = {"strategy": strategy, "status": _meta(snode[0]).get("status"), "experiments": []}
    for e in exps:
        exp_id = e["target_id"]
        rels = db.query("SELECT relation,target_id FROM edges WHERE source_id=?", (exp_id,))
        node = db.query("SELECT name FROM nodes WHERE id=?", (exp_id,))
        lineage["experiments"].append({
            "experiment": exp_id.split(":", 1)[1],
            "hypothesis": [r["target_id"].split(":", 1)[1] for r in rels if r["relation"] == "tested"],
            "failed_because": [r["target_id"].split(":", 1)[1] for r in rels if r["relation"] == "failed_because"],
            "used_datasets": [r["target_id"].split(":", 1)[1] for r in rels if r["relation"] == "used"],
        })
    db.close()
    return lineage


def failure_pattern_summary() -> dict:
    """FailureReason별 experiment 카운트(failed_because 엣지 집계)."""
    db = _ro()
    if db is None:
        return {}
    rows = db.query("""
        SELECT fr.name AS reason, COUNT(*) AS n FROM edges e
        JOIN nodes fr ON fr.id = e.target_id
        WHERE e.relation='failed_because' GROUP BY fr.name ORDER BY n DESC""")
    db.close()
    return {r["reason"]: r["n"] for r in rows}


def regime_performance_map() -> dict:
    """Regime → 영향받은 전략/결정 맵(affected_by + PortfolioDecision.regime)."""
    db = _ro()
    if db is None:
        return {}
    out: dict = {}
    for r in db.query("SELECT * FROM nodes WHERE type='Regime'"):
        regime = r["name"]
        strats = db.query("""SELECT s.name FROM edges e JOIN nodes s ON s.id=e.source_id
            WHERE e.relation='affected_by' AND e.target_id=?""", (r["id"],))
        decs = db.query("""SELECT name FROM nodes WHERE type='PortfolioDecision'
            AND json_extract(metadata,'$.regime')=?""", (regime,))
        out[regime] = {"strategies": sorted({s["name"] for s in strats}),
                       "decisions": len(decs)}
    db.close()
    return out


def signal_contribution_graph() -> list[dict]:
    """Strategy → generated → Signal → contributed_to → Allocation 경로."""
    db = _ro()
    if db is None:
        return []
    out = db.query("""
        SELECT s.name AS strategy, sig.name AS signal, a.name AS allocation FROM edges g
        JOIN nodes s   ON s.id=g.source_id AND s.type='Strategy'
        JOIN nodes sig ON sig.id=g.target_id AND sig.type='Signal'
        JOIN edges c   ON c.source_id=sig.id AND c.relation='contributed_to'
        JOIN nodes a   ON a.id=c.target_id
        WHERE g.relation='generated'""")
    db.close()
    return [dict(r) for r in out]


def graph_counts() -> dict:
    db = _ro()
    if db is None:
        return {}
    by_type = {r["type"]: r["n"] for r in db.query("SELECT type,COUNT(*) n FROM nodes GROUP BY type")}
    by_rel = {r["relation"]: r["n"] for r in db.query("SELECT relation,COUNT(*) n FROM edges GROUP BY relation")}
    db.close()
    return {"nodes_by_type": by_type, "edges_by_relation": by_rel}
