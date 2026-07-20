"""완료된 페이퍼 트레이드 1건을 저널 CSV(프론트 repo)에 append.
docs/orderflow-journal.csv 헤더 순서 고정 — 바꾸지 않는다."""
from __future__ import annotations

import csv
import datetime as _dt
import os

FIELDS = [
    "datetime", "symbol", "direction", "ict_context", "of_trigger", "level_basis",
    "entry", "stop", "target", "risk_r", "result_r", "note",
]


def append_trade_row(
    path: str,
    *,
    entered_ts: float,
    symbol: str,
    direction: str,
    ict_context: str,
    of_trigger: str,
    level_basis: str,
    entry: float,
    stop: float,
    target: float,
    risk_r: float,
    result_r: float,
    note: str,
) -> None:
    row = {
        "datetime": _dt.datetime.fromtimestamp(entered_ts, tz=_dt.timezone.utc).isoformat(),
        "symbol": symbol, "direction": direction, "ict_context": ict_context,
        "of_trigger": of_trigger, "level_basis": level_basis,
        "entry": entry, "stop": stop, "target": target,
        "risk_r": risk_r, "result_r": result_r, "note": note,
    }
    is_new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow(row)
