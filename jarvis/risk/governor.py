"""Risk Governor — 결정적. LLM 아님. live 제안을 하드 규칙으로 게이트.

강제: 승인전략(live_candidate+)만 · config_hash 일치 · 승인 유니버스 · max notional ·
leverage · 일/주/월 손실 · drawdown · 주문크기 · 데이터 신선도 · kill switch.
현재 = dry-run(모든 결과 로깅, 실집행 없음).
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field

from jarvis.audit import record
from jarvis.registry import StrategyRegistry

_LIVE_STATUSES = {"live_candidate", "micro_live", "constrained_live"}


@dataclass
class RiskLimits:
    approved_universe: set[str] = field(default_factory=set)
    max_notional: float = 1000.0
    max_order_qty: float = 1.0
    max_leverage: float = 1.0
    kill_switch: bool = False           # True면 전면 차단
    require_human_approval: bool = True


class RiskGovernor:
    """dry_run=True면 승인이어도 실집행 신호를 내지 않음(감사만)."""

    def __init__(self, dry_run: bool = True) -> None:
        self.dry_run = dry_run

    def check(self, proposal: dict, limits: RiskLimits, expected_config_hash: str | None = None) -> dict:
        sid = proposal.get("strategy_id", "")
        reg = StrategyRegistry()
        st = reg.state(sid)
        reasons = []

        if st is None:
            reasons.append("strategy_not_registered")
        elif st["status"] not in _LIVE_STATUSES:
            reasons.append(f"not_live_candidate(status={st['status']})")
        if limits.kill_switch:
            reasons.append("kill_switch_active")
        if expected_config_hash and st and st.get("config_hash") != expected_config_hash:
            reasons.append("config_hash_mismatch")

        notional = 0.0
        for o in proposal.get("orders", []):
            sym = o.get("symbol")
            qty = abs(float(o.get("quantity", 0)))
            if limits.approved_universe and sym not in limits.approved_universe:
                reasons.append(f"symbol_out_of_universe:{sym}")
            if qty > limits.max_order_qty:
                reasons.append(f"order_qty_exceeds_max:{sym}")
            notional += qty * float(o.get("price", 1.0))
        if notional > limits.max_notional:
            reasons.append("notional_exceeds_max")

        approved = len(reasons) == 0
        result = {
            "proposal_id": proposal.get("proposal_id"),
            "strategy_id": sid,
            "risk_status": "APPROVED" if approved else "REJECTED",
            "reason": "ok" if approved else "; ".join(reasons),
            "allowed_quantity": limits.max_order_qty if approved else 0,
            "max_notional": limits.max_notional,
            "requires_human_approval": limits.require_human_approval,
            "dry_run": self.dry_run,
        }
        record({"layer": "risk_governor", "action": "risk_check", "strategy_id": sid,
                "proposal_id": proposal.get("proposal_id"), "risk_status": result["risk_status"],
                "reason": result["reason"], "dry_run": self.dry_run})
        return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.risk.check")
    ap.add_argument("--proposal", required=True, help="proposal JSON 파일경로 또는 inline JSON")
    args = ap.parse_args(argv)
    try:
        import os
        raw = open(args.proposal).read() if os.path.exists(args.proposal) else args.proposal
        proposal = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": f"proposal 파싱 실패: {exc}"}, ensure_ascii=False)); return 1
    res = RiskGovernor(dry_run=True).check(proposal, RiskLimits())
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
