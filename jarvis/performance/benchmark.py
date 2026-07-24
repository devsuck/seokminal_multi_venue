"""Performance 벤치마크·동등성 검증 (P37) — 최적화 경로가 나이브 경로와 동일 결과인지 검증. **결과 불변.**

벤치마크는 결정적 산출(연산 수·결과 해시)만 반환한다(월클럭 단정 없음 — 플래키 방지). 최적화 경로(캐시/인덱스/지연)가
나이브 경로와 **동일 결과**임을 확인하는 동등성 검사를 제공한다. 상위 계층은 READ ONLY.
"""
from __future__ import annotations

from jarvis.performance import optimize
from jarvis.system_integration.models import verify_hash_records


# ══════════════ 동등성 검사(최적화 == 나이브) ══════════════
def equiv_index_vs_scan(records, key, value) -> bool:
    """인덱스 조회 == 선형 스캔."""
    scan = [r for r in records if r.get(key) == value]
    idx = optimize.index_lookup(optimize.build_index(records, key), value)
    return scan == idx


def equiv_stream_vs_full(path, full_records) -> bool:
    """지연 스트리밍 == 전체 적재."""
    return list(optimize.stream_read_jsonl(path)) == full_records


def equiv_count(path, full_records) -> bool:
    """스트리밍 계수 == len(전체)."""
    return optimize.count_lines(path) == len(full_records)


def equiv_hash_verify(records) -> bool:
    """캐시 해시체인 검증 == 나이브 verify_hash_records."""
    cache = optimize.HashVerifyCache()
    return cache.verify_chain(records) == verify_hash_records(records)


def equiv_chunk(records, size) -> bool:
    """청크 재조립 == 원본."""
    reassembled = [item for batch in optimize.chunk(records, size) for item in batch]
    return reassembled == records


# ══════════════ 결정적 벤치마크(연산 수·결과 해시) ══════════════
def benchmark_hash_verification(records) -> dict:
    """해시 검증 벤치마크: 캐시 히트/미스 + 결과(결정적)."""
    cache = optimize.HashVerifyCache()
    result = cache.verify_chain(records)
    return {"operation": "hash_verification", "records": len(records),
            "cache_hits": cache.hits, "cache_misses": cache.misses, "ok": result["ok"]}


def benchmark_indexing(records, key) -> dict:
    """인덱싱 벤치마크: 인덱스 크기(결정적)."""
    idx = optimize.build_index(records, key)
    return {"operation": "indexing", "records": len(records), "distinct_keys": len(idx)}


def large_record_processing(n) -> dict:
    """대량 레코드 처리 스케일 검사(결정적). n개 합성 레코드를 청크/인덱스/중복제거."""
    records = [{"id": f"r{i}", "grp": f"g{i % 10}", "v": i} for i in range(max(0, n))]
    batches = list(optimize.chunk(records, 128))
    idx = optimize.build_index(records, "grp")
    deduped = optimize.dedupe_preserve_order(records, "id")
    return {"operation": "large_record_processing", "records": len(records),
            "batches": len(batches), "distinct_groups": len(idx), "deduped": len(deduped)}
