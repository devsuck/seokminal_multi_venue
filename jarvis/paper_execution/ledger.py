"""Paper Execution 원장 (P6.2) — append-only. 삭제/재작성 없음. capital=paper."""
from __future__ import annotations

from jarvis.config import state_path
from jarvis.ledger_io import append, read_jsonl

_ORDERS = "paper_orders.jsonl"
_FILLS = "paper_fills.jsonl"
_POSITIONS = "paper_positions.jsonl"
_REPORTS = "paper_execution_reports.jsonl"


def _append(name: str, row: dict) -> None:
    append(name, {**row, "capital": "paper"}, resolver=state_path)


def _read(name: str) -> list[dict]:
    return read_jsonl(name, resolver=state_path)


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
