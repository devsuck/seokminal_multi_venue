"""Research API 검증 (P10.29) — 체인·변조·중복·스키마 일관성·읽기전용 경계·결정적 재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 스키마 일관성: 엔드포인트 응답 키 == 등록
스키마 필드. 권한 경계: 모든 엔드포인트 GET·read_only, 금지 동사 없음. **변경/실행/거래/주문/배포 없음.**
"""
from __future__ import annotations

from jarvis.research_api import ledger
from jarvis.research_api.models import (
    ALLOWED_METHODS,
    ENDPOINT_SCHEMAS,
    GENESIS,
    content_hash,
    is_forbidden_path,
    schema_id as _schema_id,
)


def _verify_records(records: list, id_field: str) -> dict:
    if not records:
        return {"ok": True, "n": 0, "reason": "empty"}
    prev = GENESIS
    seen = set()
    for i, r in enumerate(records):
        if r.get("previous_hash") != prev:
            return {"ok": False, "broken_at": i, "reason": "previous_hash_broken"}
        if not r.get("record_hash"):
            return {"ok": False, "broken_at": i, "reason": "missing_record_hash"}
        rid = r.get(id_field)
        if rid in seen:
            return {"ok": False, "broken_at": i, "reason": "duplicate_id"}
        if content_hash(r) != r.get("record_hash"):
            return {"ok": False, "broken_at": i, "reason": "record_hash_mismatch"}
        seen.add(rid)
        prev = r["record_hash"]
    return {"ok": True, "n": len(records), "reason": "chain_intact"}


def verify_ledger(which) -> dict:
    filename, id_field = which
    return _verify_records(ledger.read_jsonl(filename), id_field)


def schema_consistency() -> dict:
    """등록 스키마 필드 == 엔드포인트 권위 스키마. 등록 스키마 결측/불일치 탐지."""
    issues: list = []
    for function, fields in ENDPOINT_SCHEMAS.items():
        rec = ledger.get_schema(_schema_id(function))
        if rec is None:
            continue  # 미부트스트랩은 이슈 아님(등록 시에만 검증)
        if set(rec.get("fields", [])) != set(fields):
            issues.append(f"schema_mismatch:{function}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def permission_boundary() -> dict:
    """권한 경계: 모든 엔드포인트 read_only·GET·금지 동사 없음."""
    issues: list = []
    for e in ledger.read_endpoints():
        if e.get("method") not in ALLOWED_METHODS:
            issues.append(f"non_get_method:{e.get('path')}")
        if not e.get("read_only", False):
            issues.append(f"not_read_only:{e.get('path')}")
        if is_forbidden_path(e.get("path", ""), e.get("function", "")):
            issues.append(f"forbidden_verb:{e.get('path')}")
    # 접근 로그도 전부 GET·read_only 여야 함.
    for a in ledger.read_access():
        if a.get("method") not in ALLOWED_METHODS or not a.get("read_only", False):
            issues.append(f"access_not_read_only:{a.get('access_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    schema = schema_consistency()
    perm = permission_boundary()
    ok = ok and schema["ok"] and perm["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "schema": schema, "permission": perm}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "endpoint_count": r1.endpoint_count, "access_count": r1.access_count,
            "schema_count": r1.schema_count}
