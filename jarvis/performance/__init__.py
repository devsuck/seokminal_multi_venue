"""jarvis.performance — Performance & Scalability Validation (P37). **결과 불변 안전 최적화.**

시스템 성능을 행위 변경 없이 분석·개선한다: 캐싱·인덱싱 헬퍼·지연 로딩·최적화 유틸리티. **데이터 형식·소유권·원장 구조·결과를
변경하지 않는다.** OPTIMIZATION ≠ BEHAVIOR CHANGE · SAME RESULTS GUARANTEED. 순수 유틸리티(원장 없음, 파일 쓰기 없음).
상위 계층은 READ ONLY. 새 원장·새 연구 지능 없음.
"""
from jarvis.performance import benchmark, optimize  # noqa: F401
from jarvis.performance.models import (  # noqa: F401
    ALLOWED_OPTIMIZATIONS,
    BENCHMARK_OPERATIONS,
    FORBIDDEN_CHANGES,
    is_allowed_optimization,
    is_forbidden_change,
)
from jarvis.performance.optimize import (  # noqa: F401
    HashVerifyCache,
    build_index,
    build_unique_index,
    chunk,
    count_lines,
    dedupe_preserve_order,
    index_lookup,
    memoize,
    stream_read_jsonl,
)
