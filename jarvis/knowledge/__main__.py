"""`python -m jarvis.knowledge <cmd>` — 지식그래프 CLI. 소스 파일 무기록.

  rebuild            P3 projection → graph.db 재구축(GraphReport)
  verify             결정적 재생성 + checksum 일치
  query <name> [arg] 지식 쿼리(failed_strategies/related_experiments/lineage/
                     failure_patterns/regime_map/signal_graph/counts)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cmd_rebuild() -> int:
    from jarvis.knowledge.builder import build
    rep = build(ts=_now())
    print(json.dumps(rep.to_dict(), ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_verify() -> int:
    from jarvis.knowledge.verify import verify
    res = verify()
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    return 0 if res.get("ok") else 1


def _cmd_query(name: str, arg: str | None) -> int:
    from jarvis.knowledge import query as q
    fns = {
        "failed_strategies": lambda: q.find_failed_strategies(),
        "related_experiments": lambda: q.find_related_experiments(arg or ""),
        "lineage": lambda: q.strategy_lineage(arg or ""),
        "failure_patterns": lambda: q.failure_pattern_summary(),
        "regime_map": lambda: q.regime_performance_map(),
        "signal_graph": lambda: q.signal_contribution_graph(),
        "counts": lambda: q.graph_counts(),
    }
    if name not in fns:
        print(json.dumps({"error": f"unknown query '{name}'", "available": sorted(fns)},
                         ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(fns[name](), ensure_ascii=False, indent=2, default=str))
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="jarvis.knowledge")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("rebuild")
    sub.add_parser("verify")
    qp = sub.add_parser("query")
    qp.add_argument("name")
    qp.add_argument("arg", nargs="?", default=None)
    args = ap.parse_args(argv)
    if args.cmd == "rebuild":
        return _cmd_rebuild()
    if args.cmd == "verify":
        return _cmd_verify()
    if args.cmd == "query":
        return _cmd_query(args.name, args.arg)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
