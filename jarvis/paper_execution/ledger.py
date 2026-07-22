"""Paper Execution 원장 (P6.2) — append-only. 삭제/재작성 없음. capital=paper."""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

_ORDERS = "paper_orders.jsonl"
_FILLS = "paper_fills.jsonl"
_POSITIONS = "paper_positions.jsonl"
_REPORTS = "paper_execution_reports.jsonl"


def _read(name: str) -> list[dict]:
    p = state_path(name)
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def _append(name: str, row: dict) -> None:
    p = state_path(name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps({**row, "capital": "paper"}, ensure_ascii=False, default=str) + "\n")


def append_order(o: dict) -> None:
    _append(_ORDERS, o)


def append_fill(f: dict) -> None:
    _append(_FILLS, f)


def append_position(p: dict) -> None:
    _append(_POSITIONS, p)


def append_report(r: dict) -> None:
    _append(_REPORTS, r)


def read_orders() -> list[dict]:
    return _read(_ORDERS)


def read_fills() -> list[dict]:
    return _read(_FILLS)


def read_positions() -> list[dict]:
    return _read(_POSITIONS)


def read_reports() -> list[dict]:
    return _read(_REPORTS)


def current_positions() -> dict:
    """전략별 최신 포지션 스냅샷(append-only fold)."""
    latest: dict = {}
    for row in _read(_POSITIONS):
        latest[row["strategy_id"]] = row
    return latest


def executed_proposal_ids() -> set:
    return {r["proposal_id"] for r in _read(_REPORTS)}
