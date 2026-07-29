"""불변 읽기 캐시 (P14) — 버전 기반 무효화. **읽기 캐시 전용, 불변·결정적.**

한 번 저장된 항목은 변경되지 않는다(같은 key+version 에 다른 값 저장 시 거부). 무효화는 버전 단위로만 수행하며,
기존 값을 변형하지 않는다. 통계·리포트를 제공한다. 기존 원장/모듈을 건드리지 않는다(완전 additive).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass


class ImmutableCacheError(Exception):
    """불변 캐시 항목 재정의 시도 — 거부."""


def _fingerprint(value) -> str:
    blob = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class CacheStats:
    entries: int
    hits: int
    misses: int
    puts: int
    rejected: int
    invalidations: int
    versions: int

    def to_dict(self) -> dict:
        return asdict(self)


class ImmutableCache:
    """버전 기반 불변 읽기 캐시. (namespace, key, version) → value.

    - put: 신규만 저장(같은 (ns,key,version) 에 다른 값이면 ImmutableCacheError). 동일 값 재저장은 무연산.
    - get: 조회(hit/miss 통계). 반환 값은 저장값의 결정적 복제(json round-trip)로 원본 변형 방지.
    - invalidate_version: 버전 단위 무효화. 기존 값 변형 없음, 삭제만.
    """

    def __init__(self) -> None:
        self._store: dict = {}                 # (ns, key, version) -> (value, fingerprint)
        self._hits = 0
        self._misses = 0
        self._puts = 0
        self._rejected = 0
        self._invalidations = 0

    @staticmethod
    def _k(namespace: str, key: str, version) -> tuple:
        return (namespace, key, str(version))

    def put(self, namespace: str, key: str, version, value) -> bool:
        """신규 저장. 이미 동일 값이면 True(무연산), 다른 값이면 거부. 반환: 저장/존재 여부."""
        k = self._k(namespace, key, version)
        fp = _fingerprint(value)
        if k in self._store:
            if self._store[k][1] != fp:
                self._rejected += 1
                raise ImmutableCacheError(f"불변 캐시 재정의 거부 {k}")
            return True
        self._store[k] = (json.loads(json.dumps(value, default=str)), fp)
        self._puts += 1
        return True

    def get(self, namespace: str, key: str, version, default=None):
        """조회. 저장값의 결정적 복제 반환(원본 불변). 없으면 default."""
        k = self._k(namespace, key, version)
        if k in self._store:
            self._hits += 1
            return json.loads(json.dumps(self._store[k][0], default=str))
        self._misses += 1
        return default

    def contains(self, namespace: str, key: str, version) -> bool:
        return self._k(namespace, key, version) in self._store

    def fingerprint(self, namespace: str, key: str, version) -> str | None:
        k = self._k(namespace, key, version)
        return self._store[k][1] if k in self._store else None

    def invalidate_version(self, namespace: str, version) -> int:
        """(namespace, version) 의 모든 항목 무효화(삭제). 반환: 제거 수."""
        targets = [k for k in self._store if k[0] == namespace and k[2] == str(version)]
        for k in targets:
            del self._store[k]
        if targets:
            self._invalidations += 1
        return len(targets)

    def invalidate_namespace(self, namespace: str) -> int:
        """namespace 전체 무효화(삭제). 반환: 제거 수."""
        targets = [k for k in self._store if k[0] == namespace]
        for k in targets:
            del self._store[k]
        if targets:
            self._invalidations += 1
        return len(targets)

    def versions(self, namespace: str | None = None) -> list:
        vs = {k[2] for k in self._store if namespace is None or k[0] == namespace}
        return sorted(vs)

    def keys(self, namespace: str | None = None) -> list:
        return sorted(k for k in self._store if namespace is None or k[0] == namespace)

    def stats(self) -> CacheStats:
        return CacheStats(
            entries=len(self._store), hits=self._hits, misses=self._misses, puts=self._puts,
            rejected=self._rejected, invalidations=self._invalidations,
            versions=len({k[2] for k in self._store}))

    def report(self) -> dict:
        """결정적 캐시 리포트(namespace 별 항목 수·버전·hit rate)."""
        by_ns: dict = {}
        for (ns, _key, ver) in self._store:
            by_ns.setdefault(ns, {"entries": 0, "versions": set()})
            by_ns[ns]["entries"] += 1
            by_ns[ns]["versions"].add(ver)
        namespaces = {ns: {"entries": d["entries"], "versions": sorted(d["versions"])}
                      for ns, d in sorted(by_ns.items())}
        total_reads = self._hits + self._misses
        hit_rate = round(self._hits / total_reads, 6) if total_reads else 0.0
        return {"stats": self.stats().to_dict(), "namespaces": namespaces, "hit_rate": hit_rate}
