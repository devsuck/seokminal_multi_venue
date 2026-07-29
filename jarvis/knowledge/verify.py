"""Graph 검증 (P4) — 결정적 재생성 + 저장 checksum 일치.

임시 graph에 재구축한 checksum == 현재 저장 checksum이면 deterministic.
소스(JSONL/projection) 무변경.
"""
from __future__ import annotations

import os
import tempfile

from jarvis.db.sqlite import Database
from jarvis.knowledge.builder import build
from jarvis.knowledge.schema import graph_db_path, graph_exists


def verify(path: str | None = None, projection_db: str | None = None) -> dict:
    path = path or graph_db_path()
    if not graph_exists(path):
        return {"ok": False, "reason": "graph_missing", "graph_exists": False}

    db = Database(path, read_only=True)
    stored = db.query("SELECT value FROM graph_meta WHERE key='checksum'")
    stored_checksum = stored[0]["value"] if stored else None
    node_count = db.count("nodes")
    edge_count = db.count("edges")
    db.close()

    tmp = os.path.join(tempfile.mkdtemp(), "graph_verify.db")
    rep = build(tmp, projection_db=projection_db, ts="verify")
    for sfx in ("", "-wal", "-shm"):
        try:
            os.remove(tmp + sfx)
        except OSError:
            pass

    deterministic = (rep.checksum == stored_checksum) if stored_checksum else False
    return {
        "ok": bool(deterministic),
        "graph_exists": True,
        "deterministic": deterministic,
        "stored_checksum": stored_checksum,
        "rebuilt_checksum": rep.checksum,
        "node_count": node_count,
        "edge_count": edge_count,
    }
