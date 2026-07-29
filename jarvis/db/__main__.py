"""`python -m jarvis.db <cmd>` — 프로젝션 CLI.

  rebuild   JSONL → SQLite 재구축(ProjectionReport)
  status    {database_exists, last_projection, table_counts, source_checksum}
  verify    프로젝션이 JSONL과 일치·결정적 재생성인지 확인
"""
from __future__ import annotations

import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cmd_rebuild() -> int:
    from jarvis.db.projector import rebuild
    rep = rebuild(ts=_now())
    print(json.dumps(rep.to_dict(), ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_status() -> int:
    from jarvis.db.projector import source_checksum
    from jarvis.db.query import table_counts
    from jarvis.db.sqlite import Database, db_path, exists
    ex = exists(db_path())
    last = None
    if ex:
        db = Database(read_only=True)
        last = db.get_meta("last_projection")
        db.close()
    out = {"database_exists": ex, "last_projection": last,
           "table_counts": table_counts() if ex else {},
           "source_checksum": source_checksum()}
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_verify() -> int:
    from jarvis.db.verify import verify
    res = verify()
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    return 0 if res.get("ok") else 1


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="jarvis.db")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("rebuild")
    sub.add_parser("status")
    sub.add_parser("verify")
    args = ap.parse_args(argv)
    if args.cmd == "rebuild":
        return _cmd_rebuild()
    if args.cmd == "status":
        return _cmd_status()
    if args.cmd == "verify":
        return _cmd_verify()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
