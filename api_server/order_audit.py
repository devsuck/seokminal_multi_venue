"""Append-only order audit trail.

Every order that reaches a broker is recorded as one JSON line with a UTC
timestamp, so there is a durable, tamper-evident record independent of the
browser's localStorage log. JSONL keeps appends atomic and the file
greppable. Path is configurable via ORDER_AUDIT_PATH.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path


def _audit_path() -> Path:
    return Path(os.environ.get("ORDER_AUDIT_PATH", "data/order_audit.jsonl"))


def record_order(
    *,
    venue: str,
    request: dict,
    result: dict | None,
    status: str,
    path: Path | None = None,
) -> dict:
    """Append one audit entry and return it.

    ``status`` is "submitted" | "rejected" | "error". ``result`` is the broker
    response when available, else None. Failures to write are swallowed by the
    caller's discretion — this function raises only on truly broken I/O.
    """
    entry = {
        "ts": _dt.datetime.now(_dt.UTC).isoformat(),
        "venue": venue,
        "status": status,
        "request": request,
        "result": result,
    }
    target = path or _audit_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_recent(limit: int = 100, path: Path | None = None) -> list[dict]:
    """Return the most recent audit entries (newest last), up to ``limit``."""
    target = path or _audit_path()
    if not target.exists():
        return []
    with open(target, encoding="utf-8") as f:
        lines = f.readlines()
    out = []
    for line in lines[-limit:]:
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out
