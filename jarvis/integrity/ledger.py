"""원장 무결성 검증 (P15) — 해시체인·변조·중복·타임스탬프·계보·replay. **읽기 전용·결정적.**

기존 P9~P13 원장 형식(JSONL + previous_hash + record_hash, content_hash 관례 동일)을 읽어 무결성을 검증한다. 원본을
수정/삭제하지 않는다(완전 additive). 레코드 리스트를 입력받아 순수 함수로 판정한다.
"""
from __future__ import annotations

import hashlib
import json
import re

GENESIS = "GENESIS"
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$")


def content_hash(record: dict) -> str:
    """프로젝트 관례: previous_hash/record_hash/report_hash 제외 후 SHA256[:16]."""
    core = {k: v for k, v in record.items()
            if k not in ("previous_hash", "record_hash", "report_hash")}
    blob = json.dumps(core, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def verify_hash_chain(records: list) -> dict:
    """해시체인 검증(previous_hash 링크 + record_hash 재계산). GENESIS 시작."""
    prev = GENESIS
    for i, r in enumerate(records):
        if r.get("previous_hash") != prev:
            return {"ok": False, "broken_at": i, "reason": "previous_hash_broken"}
        if not r.get("record_hash"):
            return {"ok": False, "broken_at": i, "reason": "missing_record_hash"}
        if content_hash(r) != r.get("record_hash"):
            return {"ok": False, "broken_at": i, "reason": "record_hash_mismatch"}
        prev = r["record_hash"]
    return {"ok": True, "broken_at": -1, "reason": "chain_intact", "n": len(records)}


def detect_tamper(records: list) -> list:
    """변조 탐지(record_hash 불일치 인덱스 목록)."""
    out = []
    for i, r in enumerate(records):
        if r.get("record_hash") and content_hash(r) != r.get("record_hash"):
            out.append(i)
    return out


def detect_duplicate_ids(records: list, id_field: str) -> list:
    """중복 ID 목록(정렬)."""
    seen: set = set()
    dups: set = set()
    for r in records:
        rid = r.get(id_field)
        if rid in seen:
            dups.add(rid)
        seen.add(rid)
    return sorted(dups)


def detect_invalid_timestamps(records: list, ts_field: str) -> list:
    """무효 타임스탬프(ISO8601 아님) 레코드 인덱스."""
    out = []
    for i, r in enumerate(records):
        ts = r.get(ts_field)
        if ts is None or not isinstance(ts, str) or not _ISO_RE.match(ts):
            out.append(i)
    return out


def replay_consistency(records: list) -> dict:
    """replay 결정성: 체인 재계산 두 번 동일 산출."""
    def recompute():
        prev = GENESIS
        chain = []
        for r in records:
            core = {k: v for k, v in r.items()
                    if k not in ("previous_hash", "record_hash", "report_hash")}
            h = "sha256:" + hashlib.sha256(
                json.dumps({**core, "previous_hash": prev}, sort_keys=True,
                           ensure_ascii=False, default=str).encode()).hexdigest()[:16]
            chain.append(h)
            prev = h
        return chain
    a = recompute()
    b = recompute()
    return {"deterministic": a == b, "final": a[-1] if a else GENESIS, "n": len(records)}


def detect_orphan_artifacts(records: list, id_field: str, parent_field: str) -> list:
    """dangling parent(존재하지 않는 부모 참조) 레코드 ID 목록."""
    ids = {r.get(id_field) for r in records}
    out = []
    for r in records:
        parent = r.get(parent_field)
        if parent and parent not in ids:
            out.append(r.get(id_field))
    return sorted(o for o in out if o is not None)


def detect_broken_lineage(records: list, id_field: str, parent_field: str) -> dict:
    """계보 무결성: dangling + 순환."""
    orphans = detect_orphan_artifacts(records, id_field, parent_field)
    edges = [(r.get(id_field), r.get(parent_field)) for r in records if r.get(parent_field)]
    graph: dict = {}
    for a, b in edges:
        graph.setdefault(a, set()).add(b)
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict = {}

    def dfs(n) -> bool:
        color[n] = GRAY
        for m in sorted(x for x in graph.get(n, ()) if x is not None):
            c = color.get(m, WHITE)
            if c == GRAY:
                return True
            if c == WHITE and dfs(m):
                return True
        color[n] = BLACK
        return False

    has_cycle = any(color.get(n, WHITE) == WHITE and dfs(n)
                    for n in sorted(x for x in graph if x is not None))
    return {"ok": not orphans and not has_cycle, "orphans": orphans, "has_cycle": has_cycle}


def verify_ledger(records: list, *, id_field: str = "record_hash", parent_field: str | None = None,
                  ts_field: str | None = None) -> dict:
    """원장 종합 무결성 검증(결정적 집계). **읽기 전용.**"""
    chain = verify_hash_chain(records)
    tamper = detect_tamper(records)
    dups = detect_duplicate_ids(records, id_field)
    replay = replay_consistency(records)
    ts = detect_invalid_timestamps(records, ts_field) if ts_field else []
    lineage = (detect_broken_lineage(records, id_field, parent_field)
               if parent_field else {"ok": True, "orphans": [], "has_cycle": False})
    ok = (chain["ok"] and not tamper and not dups and replay["deterministic"]
          and not ts and lineage["ok"])
    return {"ok": ok, "n": len(records), "chain": chain, "tamper": tamper,
            "duplicate_ids": dups, "replay": replay, "invalid_timestamps": ts,
            "lineage": lineage}
