"""Graph Builder (P4) — P3 projection → nodes/edges → graph.db. 결정적·재생성.

소스 JSONL 무변경(P3 projection도 읽기만; 자체 임시 projection 재구축 가능).
삭제 후 rebuild하면 동일 checksum. graph.db는 disposable.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field

from jarvis.db.sqlite import Database
from jarvis.knowledge.entities import aggregate_experiments, build_nodes
from jarvis.knowledge.relations import build_edges
from jarvis.knowledge.schema import GRAPH_SCHEMA, graph_db_path


@dataclass
class GraphReport:
    timestamp: str
    node_count: int = 0
    edge_count: int = 0
    nodes_by_type: dict = field(default_factory=dict)
    edges_by_relation: dict = field(default_factory=dict)
    skipped_edges: int = 0
    checksum: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _canon(meta: dict) -> str:
    return json.dumps(meta or {}, sort_keys=True, ensure_ascii=False, default=str)


def graph_checksum(nodes: dict, edges: list) -> str:
    h = hashlib.sha256()
    for nid in sorted(nodes):
        n = nodes[nid]
        h.update(json.dumps([n["id"], n["type"], n["name"], _canon(n["metadata"]),
                             n["created_at"]], sort_keys=True, default=str).encode())
    h.update(b"||")
    for e in sorted(edges, key=lambda x: (x[0], x[1], x[2], _canon(x[3]))):
        h.update(json.dumps([e[0], e[1], e[2], _canon(e[3])], default=str).encode())
    return "sha256:" + h.hexdigest()


def _open_projection(projection_db: str | None, ts: str) -> tuple:
    """(Database, own_tmp_path_or_None). None이면 임시 P3 projection 재구축."""
    if projection_db is not None:
        return Database(projection_db, read_only=True), None
    from jarvis.db.projector import rebuild as p3_rebuild
    tmp = os.path.join(tempfile.mkdtemp(), "proj.db")
    p3_rebuild(tmp, ts=ts)
    return Database(tmp, read_only=True), tmp


def build(graph_path: str | None = None, projection_db: str | None = None,
          ts: str = "") -> GraphReport:
    p3, own_tmp = _open_projection(projection_db, ts)
    try:
        agg = aggregate_experiments(p3)
        nodes = build_nodes(p3, agg)
        edges, skipped = build_edges(p3, agg, set(nodes))
    finally:
        p3.close()
        if own_tmp:
            for sfx in ("", "-wal", "-shm"):
                try:
                    os.remove(own_tmp + sfx)
                except OSError:
                    pass

    path = graph_path or graph_db_path()
    g = Database(path)
    g.executescript("DROP TABLE IF EXISTS nodes; DROP TABLE IF EXISTS edges;"
                    " DROP TABLE IF EXISTS graph_meta;" + GRAPH_SCHEMA)
    g.executemany("INSERT INTO nodes(id,type,name,metadata,created_at) VALUES (?,?,?,?,?)",
                  [(n["id"], n["type"], n["name"], _canon(n["metadata"]), n["created_at"])
                   for n in nodes.values()])
    g.executemany("INSERT INTO edges(source_id,relation,target_id,metadata) VALUES (?,?,?,?)",
                  [(e[0], e[1], e[2], _canon(e[3])) for e in edges])

    by_type: dict = {}
    for n in nodes.values():
        by_type[n["type"]] = by_type.get(n["type"], 0) + 1
    by_rel: dict = {}
    for e in edges:
        by_rel[e[1]] = by_rel.get(e[1], 0) + 1

    checksum = graph_checksum(nodes, edges)
    for k, v in {"last_build": ts, "checksum": checksum, "node_count": len(nodes),
                 "edge_count": len(edges)}.items():
        g.execute("INSERT OR REPLACE INTO graph_meta(key,value) VALUES (?,?)", (k, str(v)))
    g.close()

    return GraphReport(timestamp=ts, node_count=len(nodes), edge_count=len(edges),
                       nodes_by_type=by_type, edges_by_relation=by_rel,
                       skipped_edges=skipped, checksum=checksum)
