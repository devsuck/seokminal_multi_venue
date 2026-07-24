"""Performance & Scalability 자료형 (P37) — 성능 분석·안전 최적화 유틸. **동작·결과 변경 없음.**

시스템 성능을 행위 변경 없이 분석·개선한다. 허용: 캐싱·인덱싱 헬퍼·지연 로딩·최적화 유틸리티. **금지: 데이터 형식 변경·
소유권 변경·원장 구조 변경·결과 변경.** OPTIMIZATION ≠ BEHAVIOR CHANGE · SAME RESULTS GUARANTEED. 순수 유틸리티(원장
없음). 상위 계층은 READ ONLY.
"""
from __future__ import annotations

# ── 벤치마크 대상 연산 ──
BENCHMARK_OPERATIONS = ("ledger_reading", "hash_verification", "replay", "lineage_validation",
                        "large_record_processing", "report_generation")

# ── 허용 최적화 기법 ──
ALLOWED_OPTIMIZATIONS = ("caching", "indexing", "lazy_loading", "optimization_utilities")
# ── 금지 변경(행위/결과) ──
FORBIDDEN_CHANGES = ("data_format", "ownership", "ledger_structure", "results")


def is_allowed_optimization(kind) -> bool:
    return kind in ALLOWED_OPTIMIZATIONS


def is_forbidden_change(kind) -> bool:
    return kind in FORBIDDEN_CHANGES
