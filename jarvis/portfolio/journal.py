"""Portfolio Decision Journal (P2.4 F1) — 포트폴리오 결정의 '왜'를 기록.

모든 포트폴리오 평가는 append-only 저널 레코드를 남긴다: 왜 리밸런스했나/거부됐나/
노출을 줄였나/변화 없었나. 기존 audit 로거 사용. **제안 전용 — 주문 안 냄.**
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field

from jarvis.agents import META_PORTFOLIO_AGENT
from jarvis.audit import record
from jarvis.config import state_path
from jarvis.permissions import require

_LEDGER = "portfolio_decisions.jsonl"
DECISIONS = {"REBALANCE", "HOLD", "RISK_REDUCTION", "BLOCKED"}


@dataclass(frozen=True)
class PortfolioDecisionRecord:
    timestamp: str
    inputs: dict            # {regime, volatility, quality_score, active_strategies, correlation_state}
    before: dict            # 현재 strategy_weights
    after: dict             # 제안 weights
    decision: str           # REBALANCE | HOLD | RISK_REDUCTION | BLOCKED
    reasons: list = field(default_factory=list)
    blockers: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def record_decision(rec: PortfolioDecisionRecord,
                    principal=META_PORTFOLIO_AGENT) -> dict:
    """저널 레코드 append. 권한: write_portfolio_journal(PAPER_ONLY) + audit."""
    if rec.decision not in DECISIONS:
        raise ValueError(f"decision must be one of {DECISIONS}, got {rec.decision}")
    require(principal, "write_portfolio_journal", rec.decision)
    path = state_path(_LEDGER)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(rec.to_dict(), ensure_ascii=False, default=str) + "\n")
    record({"layer": "portfolio_journal", "action": "write_portfolio_journal",
            "decision": rec.decision, "n_reasons": len(rec.reasons),
            "n_blockers": len(rec.blockers), "result": "written"})
    return {"written": True, "decision": rec.decision}


def read_all() -> list[dict]:
    path = state_path(_LEDGER)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def read_latest(limit: int = 20) -> list[dict]:
    return read_all()[-limit:]


def last_timestamp() -> str | None:
    rows = read_all()
    return rows[-1]["timestamp"] if rows else None
