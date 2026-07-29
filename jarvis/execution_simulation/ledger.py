"""Execution Simulation 원장 (P7.5) — append-only. 삭제/재작성 없음. 소스 진실=JSONL.

simulation_orders.jsonl · simulation_fills.jsonl · simulation_reports.jsonl.
가상 체결 감사 산출물만. 집행 게이트웨이 무관·주문 없음·포지션 변경 없음.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

_ORDERS = "simulation_orders.jsonl"
_FILLS = "simulation_fills.jsonl"
_REPORTS = "simulation_reports.jsonl"

_EPS = 1e-9


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
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def append_order(order: dict) -> None:
    _append(_ORDERS, order)


def append_fill(fill: dict) -> None:
    _append(_FILLS, fill)


def append_report(report: dict) -> None:
    _append(_REPORTS, report)


def read_orders() -> list[dict]:
    return _read(_ORDERS)


def read_fills() -> list[dict]:
    return _read(_FILLS)


def read_reports() -> list[dict]:
    return _read(_REPORTS)


def simulation_exists(simulation_id: str) -> bool:
    return any(r.get("simulation_id") == simulation_id for r in read_reports())


def simulated_position(symbol: str) -> float:
    """시뮬 원장(simulation_fills)만으로 재현한 가상 포지션. 페이퍼/실포지션 무관.

    BUY는 +filled_quantity, SELL은 −filled_quantity. 주문 심볼 매칭.
    """
    orders = {o["simulation_id"]: o for o in read_orders()}
    pos = 0.0
    for f in read_fills():
        o = orders.get(f["simulation_id"])
        if o is None or o.get("symbol") != symbol:
            continue
        q = float(f.get("filled_quantity", 0.0))
        if o.get("side") == "BUY":
            pos += q
        elif o.get("side") == "SELL":
            pos -= q
    return round(pos, 8)
