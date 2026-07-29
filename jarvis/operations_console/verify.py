"""Operations Console 감사 검증 (P9.5) — 원장 체인 무결성 표시용. **읽기전용.**

각 원장: previous_hash 링크(직전 해시) + 해시필드 존재 + id 중복 탐지. record_hash 스킴 원장은
content 재계산으로 변조까지 탐지(P9.2/9.3/9.4 공통). P9.1(report_hash)은 링크 무결성만.
**변경/집행/복구 없음 — 표시만.** 소유 계층 코드를 import 하지 않고 JSONL 로만 검증.
"""
from __future__ import annotations

import hashlib
import json

from jarvis.operations_console import ledger

GENESIS = "GENESIS"


def _content_hash(record: dict) -> str:
    """P9.2/9.3/9.4 공통 content_hash 재현(previous_hash·record_hash·report_hash 제외)."""
    core = {k: v for k, v in record.items()
            if k not in ("previous_hash", "record_hash", "report_hash")}
    blob = json.dumps(core, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def verify_ledger(cfg) -> dict:
    filename, id_field, hash_field, recompute = cfg
    records = ledger.read_jsonl(filename)
    if not records:
        return {"ok": True, "n": 0, "reason": "empty", "latest_hash": None}
    prev = GENESIS
    seen = set()
    for i, r in enumerate(records):
        if r.get("previous_hash") != prev:
            return {"ok": False, "n": len(records), "broken_at": i,
                    "reason": "previous_hash_broken", "latest_hash": None}
        h = r.get(hash_field)
        if not h:
            return {"ok": False, "n": len(records), "broken_at": i,
                    "reason": "missing_hash", "latest_hash": None}
        rid = r.get(id_field)
        if rid in seen:
            return {"ok": False, "n": len(records), "broken_at": i,
                    "reason": "duplicate_id", "latest_hash": None}
        if recompute and _content_hash(r) != h:
            return {"ok": False, "n": len(records), "broken_at": i,
                    "reason": "hash_mismatch", "latest_hash": None}
        seen.add(rid)
        prev = h
    return {"ok": True, "n": len(records), "reason": "chain_intact", "latest_hash": prev}


def verify_all() -> dict:
    """전 감사 원장 체인 검증 → 종합 + 원장별 상태·최신 해시."""
    results = {}
    ok = True
    for cfg in ledger.AUDIT_LEDGERS:
        res = verify_ledger(cfg)
        results[cfg[0]] = res
        ok = ok and res["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results}
