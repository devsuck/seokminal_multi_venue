"""Turnover Budget Governance (P2.4 F3) — 과도한 포트폴리오 변경 통제.

기간(기본 월) 회전율 예산 대비 제안 회전율을 검사. 초과 시 decision_engine에
BLOCK 권고(강제 리밸런스 절대 없음). 기존 리밸런스 임계는 불변.
**제안 전용.** append-only turnover_ledger.jsonl.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

from jarvis.agents import META_PORTFOLIO_AGENT
from jarvis.audit import record
from jarvis.config import state_path
from jarvis.permissions import require

_LEDGER = "turnover_ledger.jsonl"
_EPS = 1e-9


@dataclass(frozen=True)
class TurnoverConfig:
    budget: float = 0.20        # 기간 회전율 예산
    period: str = "monthly"     # monthly=YYYY-MM · yearly=YYYY · daily=YYYY-MM-DD


@dataclass(frozen=True)
class TurnoverCheck:
    approved: bool
    current_turnover: float
    proposed_turnover: float
    remaining_budget: float
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def _period_key(ts: str, period: str) -> str:
    if period == "yearly":
        return ts[:4]
    if period == "daily":
        return ts[:10]
    return ts[:7]  # monthly


def _read_ledger() -> list[dict]:
    path = state_path(_LEDGER)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def current_period_turnover(now: str, rows: list[dict] | None = None,
                            period: str = "monthly") -> float:
    rows = rows if rows is not None else _read_ledger()
    key = _period_key(now, period)
    return round(sum(float(r.get("turnover", 0.0)) for r in rows
                     if _period_key(r.get("timestamp", ""), period) == key), 6)


def check_turnover(proposed_turnover: float, now: str,
                   config: TurnoverConfig | None = None,
                   rows: list[dict] | None = None) -> TurnoverCheck:
    c = config or TurnoverConfig()
    cur = current_period_turnover(now, rows, c.period)
    remaining = c.budget - cur
    approved = proposed_turnover <= remaining + _EPS
    reason = ("within_budget" if approved else
              f"budget_exceeded(current={round(cur,4)}+proposed={round(proposed_turnover,4)}>budget={c.budget})")
    return TurnoverCheck(approved=approved, current_turnover=round(cur, 6),
                         proposed_turnover=round(proposed_turnover, 6),
                         remaining_budget=round(remaining, 6), reason=reason)


def record_turnover(turnover: float, now: str, ts: str = "",
                    principal=META_PORTFOLIO_AGENT) -> dict:
    """수락된 회전율을 기간 원장에 append. 권한: record_turnover(PAPER_ONLY) + audit."""
    require(principal, "record_turnover", str(round(turnover, 6)))
    path = state_path(_LEDGER)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    row = {"timestamp": ts or now, "period_key": _period_key(now, "monthly"),
           "turnover": round(turnover, 6)}
    with open(path, "a") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    record({"layer": "meta_portfolio", "action": "record_turnover",
            "turnover": round(turnover, 6), "period_key": row["period_key"], "result": "written"})
    return {"written": True, "turnover": round(turnover, 6)}
