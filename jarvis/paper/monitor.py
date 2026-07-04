"""Paper Monitor Agent — 승인된 페이퍼 후보를 자본 없이 운용.

paper_active 전략은 배포된 forward 러너(tsmom_forward/buyback_forward 또는 내부원장) 실행.
live 주문 절대 없음.
"""
from __future__ import annotations

import argparse
import json

from jarvis.paper.deploy import deployment_of, run_forward
from jarvis.paper.ledger import PaperLedger
from jarvis.registry import Status, StrategyRegistry


def monitor(strategy_id: str, since: str | None = None) -> dict:
    """상태 + 배포정보 + forward 러너 실행결과 + 원장 요약."""
    reg = StrategyRegistry()
    st = reg.state(strategy_id)
    if st is None:
        return {"strategy_id": strategy_id, "error": "미등록"}
    dep = deployment_of(strategy_id)
    report = {
        "strategy_id": strategy_id, "status": st["status"], "since": since,
        "deployed": dep is not None,
        "runner": dep["runner"] if dep else None,
        "rules": dep["rules"] if dep else None,
        "ledger": PaperLedger().summary(strategy_id),
        "live_orders": "disabled",
    }
    if st["status"] == Status.PAPER_ACTIVE.value and dep is not None:
        report["forward"] = run_forward(strategy_id)
    else:
        report["forward"] = {"available": False, "reason": "not_paper_active_or_undeployed"}
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.paper.monitor")
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--since", default=None)
    args = ap.parse_args(argv)
    print(json.dumps(monitor(args.strategy, args.since), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
