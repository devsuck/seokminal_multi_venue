"""Operational Audit 검증 (P9.6) — 해시체인 무결성·변조 탐지·중복 탐지·리플레이. 읽기전용.

자체 원장(record_hash 스킴): previous_hash 링크 + record_hash 재계산(변조) + id 중복.
소스 원장 체인 검증(chain-broken 발견 규칙용)도 제공. replay: 동일 입력 재감사 → 동일 산출.
"""
from __future__ import annotations

import hashlib
import json

from jarvis.operational_audit import ledger
from jarvis.operational_audit.models import GENESIS, content_hash


def verify_records(records: list, id_field: str, hash_field: str = "record_hash",
                   recompute: bool = True) -> dict:
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
        if recompute and _generic_content_hash(r) != h:
            return {"ok": False, "n": len(records), "broken_at": i,
                    "reason": "record_hash_mismatch", "latest_hash": None}
        seen.add(rid)
        prev = h
    return {"ok": True, "n": len(records), "reason": "chain_intact", "latest_hash": prev}


def _generic_content_hash(record: dict) -> str:
    """P9.2/9.3/9.4/9.6 공통 content_hash 재현(소스 체인 검증용)."""
    core = {k: v for k, v in record.items()
            if k not in ("previous_hash", "record_hash", "report_hash")}
    blob = json.dumps(core, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def verify_ledger(which) -> dict:
    filename, id_field = which
    return verify_records(ledger.read_jsonl(filename), id_field)


def verify_chain() -> dict:
    """자체 감사 원장 전부 검증."""
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results}


def verify_source_chains() -> dict:
    """감사 입력 소스 원장 체인 무결성(chain-broken 발견 규칙 근거)."""
    results = {}
    for cfg in ledger.SOURCE_CHAINS:
        filename, id_field, hash_field, recompute = cfg
        results[filename] = verify_records(ledger.read_jsonl(filename), id_field,
                                           hash_field, recompute)
    return results


def replay(engine, now: str = "") -> dict:
    """동일 입력 두 번 감사 → 동일 산출(결정성). commit 없음(관측만)."""
    r1 = engine.audit(now, commit=False)
    r2 = engine.audit(now, commit=False)
    same = (r1["report"].to_dict() == r2["report"].to_dict()
            and [e.event_id for e in r1["events"]] == [e.event_id for e in r2["events"]])
    return {"deterministic": same,
            "compliance_score": r1["report"].compliance_score,
            "event_count": r1["report"].event_count,
            "report_hash": r1["report"].record_hash}
