"""jarvis.architecture_docs — Documentation & Architecture Freeze (P36). **문서화 전용.**

**ARCHIVED (Phase1 STEP4, 2026-08-01):** not covered by the original Phase1 inventory (109-module scope missed this one). Real functional import only from release_candidate/gate.py (check_no_dependency_violations), which itself has 0 external callers — 5th member of the same dead-end D-cluster (release_candidate/security_audit/production_review/system_integration). docs/architecture/*.md was last hand-generated 2026-07-30 (one manual `python -m jarvis.architecture_docs generate` run, no cron/CI wiring). Migration: archive together with that cluster; re-evaluate for full removal in a later phase.

현재 Jarvis 아키텍처의 완전한 문서(docs/architecture/ 9종)를 P35 레지스트리로부터 결정적으로 생성하고, 중복 책임·
미사용 모듈·의존성 위반·소유권 모호성을 검증한다. **핵심 아키텍처를 리팩터링하지 않는다 — 문서화만.** DOCUMENTATION
ONLY · FREEZE ≠ REFACTOR. 상위 계층은 READ ONLY. 새 원장·새 연구 지능 없음.
"""
from jarvis.architecture_docs import generator, validate  # noqa: F401
from jarvis.architecture_docs.models import (  # noqa: F401
    ARCHITECTURE_DOCS,
    LAYER_RESPONSIBILITIES,
    SECURITY_BOUNDARIES,
    doc_hash,
    is_documented,
)
