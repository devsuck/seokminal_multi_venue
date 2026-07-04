"""`python -m jarvis.registry show [--status X]` — 전략 현재상태 조회."""
from __future__ import annotations

import argparse
import json

from jarvis.registry.lifecycle import StrategyRegistry, seed_from_experiment_registry


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.registry")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show")
    s.add_argument("--status", default=None)
    sub.add_parser("seed")
    args = ap.parse_args(argv)

    reg = StrategyRegistry()
    if args.cmd == "seed":
        n = seed_from_experiment_registry(reg)
        print(json.dumps({"seeded": n}, ensure_ascii=False)); return 0
    rows = reg.list(args.status)
    print(json.dumps({"count": len(rows), "strategies": rows}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
