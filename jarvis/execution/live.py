"""`python -m jarvis.execution.live` — live 실행 시도. 현 레벨에선 BLOCKED."""
from __future__ import annotations

import argparse
import json

from jarvis.execution.gateway import ExecutionGateway


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.execution.live")
    ap.add_argument("--proposal", required=True)
    args = ap.parse_args(argv)
    res = ExecutionGateway().execute({"proposal_id": args.proposal, "strategy_id": "?", "orders": []}, mode="live")
    print(f"{res['execution_status']}: {res['reason']}")
    print(json.dumps(res, ensure_ascii=False))
    return 0 if res["execution_status"] != "BLOCKED" else 3


if __name__ == "__main__":
    raise SystemExit(main())
