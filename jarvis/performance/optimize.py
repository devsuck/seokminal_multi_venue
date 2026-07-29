"""Performance 안전 최적화 유틸리티 (P37) — 캐싱·인덱싱·지연 로딩. **결과 불변 보장.**

모든 유틸리티는 기존 나이브 구현과 **동일한 결과**를 산출한다(캐싱·인덱싱·지연 로딩만). 데이터 형식·소유권·원장 구조·결과를
변경하지 않는다. 순수 함수(부작용 없음, 파일 쓰기 없음). 상위 계층은 READ ONLY.
"""
from __future__ import annotations

import hashlib
import json
import os


# ══════════════ 인덱싱 헬퍼 ══════════════
def build_index(records, key) -> dict:
    """레코드를 key 필드값으로 인덱싱 → {value: [records]}. O(n) 1회 → O(1) 조회."""
    idx: dict = {}
    for r in records:
        idx.setdefault(r.get(key), []).append(r)
    return idx


def index_lookup(index, value) -> list:
    """인덱스 조회(선형 스캔과 동일 결과)."""
    return list(index.get(value, []))


def build_unique_index(records, key) -> dict:
    """유일 키 인덱스 → {value: record}(마지막 우선). 조회 O(1)."""
    return {r.get(key): r for r in records}


# ══════════════ 지연 로딩 ══════════════
def stream_read_jsonl(path):
    """JSONL 을 한 줄씩 지연 파싱(전체 메모리 적재 없음). read_jsonl 와 동일 순서·내용."""
    if not os.path.exists(path):
        return
    with open(path) as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                yield json.loads(ln)
            except (ValueError, json.JSONDecodeError):
                continue


def count_lines(path) -> int:
    """레코드 수를 스트리밍으로 계수(전체 적재 없음). len(read_jsonl) 와 동일."""
    n = 0
    for _ in stream_read_jsonl(path):
        n += 1
    return n


def first_n(iterable, n) -> list:
    """지연 이터러블에서 앞 n개만(지연 슬라이스)."""
    out = []
    for i, item in enumerate(iterable):
        if i >= max(0, n):
            break
        out.append(item)
    return out


# ══════════════ 배치 처리(대량 레코드) ══════════════
def chunk(iterable, size):
    """이터러블을 size 단위 청크로(대량 레코드 처리, 메모리 상한)."""
    if size <= 0:
        raise ValueError("size must be > 0")
    batch = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def dedupe_preserve_order(records, key) -> list:
    """key 기준 중복 제거(첫 등장 우선, 순서 보존)."""
    seen = set()
    out = []
    for r in records:
        v = r.get(key)
        if v not in seen:
            seen.add(v)
            out.append(r)
    return out


# ══════════════ 캐시된 해시체인 검증(결과 동일) ══════════════
_GENESIS = "GENESIS"


def _content_hash(record: dict) -> str:
    core = {k: v for k, v in record.items()
            if k not in ("previous_hash", "record_hash", "report_hash")}
    blob = json.dumps(core, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


class HashVerifyCache:
    """레코드 해시 계산 메모이제이션(동일 core → 캐시). 검증 결과는 나이브와 동일."""

    def __init__(self):
        self._cache: dict = {}
        self.hits = 0
        self.misses = 0

    def content_hash(self, record) -> str:
        core = {k: v for k, v in record.items()
                if k not in ("previous_hash", "record_hash", "report_hash")}
        ckey = json.dumps(core, sort_keys=True, ensure_ascii=False, default=str)
        if ckey in self._cache:
            self.hits += 1
            return self._cache[ckey]
        self.misses += 1
        val = "sha256:" + hashlib.sha256(ckey.encode()).hexdigest()[:16]
        self._cache[ckey] = val
        return val

    def verify_chain(self, records) -> dict:
        """캐시 사용 해시체인 검증 — verify_hash_records 와 동일 결과."""
        if not records:
            return {"ok": True, "n": 0, "reason": "empty"}
        prev = _GENESIS
        for i, r in enumerate(records):
            if r.get("previous_hash") != prev:
                return {"ok": False, "broken_at": i, "reason": "previous_hash_broken"}
            if not r.get("record_hash"):
                return {"ok": False, "broken_at": i, "reason": "missing_record_hash"}
            if self.content_hash(r) != r.get("record_hash"):
                return {"ok": False, "broken_at": i, "reason": "record_hash_mismatch"}
            prev = r["record_hash"]
        return {"ok": True, "n": len(records), "reason": "chain_intact"}


def memoize(fn):
    """단순 결정적 메모이제이션 데코레이터(불변 인자용)."""
    cache: dict = {}

    def wrapper(*args):
        if args in cache:
            return cache[args]
        v = fn(*args)
        cache[args] = v
        return v

    wrapper.cache = cache
    return wrapper
