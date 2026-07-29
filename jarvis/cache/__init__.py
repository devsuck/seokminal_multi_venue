"""jarvis.cache — 불변 읽기 캐시 레이어 (P14 Production Hardening). **읽기 캐시 전용, 완전 additive.**

버전 기반 무효화·불변 항목·결정적 조회·통계·리포트를 제공한다. 기존 P9~P13 원장/모듈을 변경하지 않으며, 원장 쓰기·
변형·실행 능력이 없다. 캐시는 순수 인메모리이며 원본 데이터를 복제해 반환하여 절대 변형하지 않는다.
"""
from jarvis.cache.store import (  # noqa: F401
    CacheStats,
    ImmutableCache,
    ImmutableCacheError,
)
