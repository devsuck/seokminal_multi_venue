"""Execution Simulation 원장 (P7.5) — append-only. 삭제/재작성 없음. 소스 진실=JSONL.

simulation_orders.jsonl · simulation_fills.jsonl · simulation_reports.jsonl.
가상 체결 감사 산출물만. 집행 게이트웨이 무관·주문 없음·포지션 변경 없음.
"""
from __future__ import annotations

from jarvis.config import state_path
from jarvis.ledger_io import append, read_jsonl

_ORDERS = "simulation_orders.jsonl"
_FILLS = "simulation_fills.jsonl"
_REPORTS = "simulation_reports.jsonl"

_EPS = 1e-9


def append_order(order: dict) -> None:
    append(_ORDERS, order, resolver=state_path)


def append_fill(fill: dict) -> None:
    append(_FILLS, fill, resolver=state_path)


def append_report(report: dict) -> None:
    append(_REPORTS, report, resolver=state_path)


def read_orders() -> list[dict]:
    return read_jsonl(_ORDERS, resolver=state_path)


def read_fills() -> list[dict]:
    return read_jsonl(_FILLS, resolver=state_path)


def read_reports() -> list[dict]:
    return read_jsonl(_REPORTS, resolver=state_path)


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
