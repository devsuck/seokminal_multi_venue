"""`python -m jarvis.execution_audit <cmd>` — 집행 파이프라인 교차검증 CLI. **AUDIT-ONLY.**

  check [request_id] [--commit]   해당 요청(또는 전체) 교차검증 → 인증서
  status                          인증 원장 요약(인증서 수·상태 분포)
  verify                          해시체인 무결성 검증
  replay [request_id]             재감사(결정적)

읽기전용 — 주문/집행/브로커 호출/상태변경 없음. 거래를 승인하지 않음.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _request_ids() -> list:
    from jarvis.config import state_path
    p = state_path("live_execution_requests.jsonl")
    if not os.path.exists(p):
        return []
    ids = []
    with open(p) as f:
        for ln in f:
            if ln.strip():
                ids.append(json.loads(ln)["request_id"])
    return sorted(set(ids))


def _cmd_check(request_id, commit: bool) -> int:
    from jarvis.execution_audit.engine import ExecutionAuditEngine
    now = _now()
    eng = ExecutionAuditEngine()
    ids = [request_id] if request_id else _request_ids()
    out = []
    for rid in ids:
        out.append(eng.audit(rid, now, commit=commit).to_dict())
    dist: dict = {}
    for c in out:
        dist[c["audit_status"]] = dist.get(c["audit_status"], 0) + 1
    print(json.dumps({"audited": len(out), "status_distribution": dist, "committed": commit,
                      "certificates": out,
                      "note": "교차검증 증명만 — 거래 승인 아님·집행/주문/브로커 없음"},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_status() -> int:
    from jarvis.execution_audit.ledger import last_certificate, read_certificates
    certs = read_certificates()
    dist: dict = {}
    for c in certs:
        dist[c.get("audit_status")] = dist.get(c.get("audit_status"), 0) + 1
    print(json.dumps({"n_certificates": len(certs), "status_distribution": dist,
                      "last_certificate": last_certificate()},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_verify() -> int:
    from jarvis.execution_audit.verify import verify_chain
    res = verify_chain()
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    return 0 if res["ok"] else 1


def _cmd_replay(request_id) -> int:
    from jarvis.execution_audit.engine import ExecutionAuditEngine
    from jarvis.execution_audit.verify import replay, verify_chain
    eng = ExecutionAuditEngine()
    ids = [request_id] if request_id else _request_ids()
    out = {rid: replay(eng, rid) for rid in ids}
    print(json.dumps({"chain": verify_chain(), "replays": out},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="jarvis.execution_audit")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("request_id", nargs="?", default=None)
    c.add_argument("--commit", action="store_true")
    sub.add_parser("status")
    sub.add_parser("verify")
    r = sub.add_parser("replay")
    r.add_argument("request_id", nargs="?", default=None)
    args = ap.parse_args(argv)
    if args.cmd == "check":
        return _cmd_check(args.request_id, args.commit)
    if args.cmd == "status":
        return _cmd_status()
    if args.cmd == "verify":
        return _cmd_verify()
    if args.cmd == "replay":
        return _cmd_replay(args.request_id)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
