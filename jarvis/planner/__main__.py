"""`python -m jarvis.planner <cmd>` — 커버리지 최적화 CLI. 소스 파일 무기록.

  analyze [--write] [--top N]   projection+KG → 랭킹 제안(기본 dry-run)
  verify                        결정적 출력 확인
"""
from __future__ import annotations

import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cmd_analyze(write: bool, top: int) -> int:
    from jarvis.planner.planner import run_planner, write_proposals
    rep = run_planner(ts=_now())
    out = rep.to_dict()
    out["proposals"] = out["proposals"][:top]
    out["note"] = ("제안 전용 — 집행 없음. " +
                   ("WRITE: 원장 기록됨." if write else "DRY-RUN: 무기록."))
    if write:
        out["ledger"] = write_proposals(rep)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_verify() -> int:
    from jarvis.planner.verify import verify
    res = verify()
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    return 0 if res.get("ok") else 1


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="jarvis.planner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("--write", action="store_true")
    a.add_argument("--top", type=int, default=20)
    sub.add_parser("verify")
    args = ap.parse_args(argv)
    if args.cmd == "analyze":
        return _cmd_analyze(args.write, args.top)
    if args.cmd == "verify":
        return _cmd_verify()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
