"""jarvis.system_integration — System Integration & Final Validation Layer (P35). **통합·검증 전용.**

**ARCHIVED (Phase1 STEP4, 2026-08-01):** most-referenced of the D-cluster (5 internal callers) but every caller is itself never invoked by api_server/scripts/ops/scheduler — whole internal audit-tooling cluster unreachable from any live entrypoint. Migration: archive together with release_candidate/security_audit/production_review/architecture_docs + the 5 already-archived research_* modules that depend on security_audit's dynamic scan; re-evaluate for full removal in a later phase.

전체 연구 생태계를 검증한다: 계층 간 무결성·소유권·원장·해시·계보·결정적 재현·API 일관성·안전성. 시스템 리포트·커버리지·
의존성 그래프·아키텍처 요약을 생성한다. Validation Runs·Findings·System Reports·Lineage 를 소유한다.

**기능 추가 없음 — 통합·검증만. 계층 소유권/원장은 불변, 정적 검사·파일 읽기만(import 결합 없음, 변경 없음).**
execution/broker/live_trading/portfolio_execution import·호출 없음. VALIDATION ≠ MUTATION · INTEGRATION ≠
EXECUTION. 불변·append-only·해시체인·결정적·재현. 원장 sysint_ 접두사.
"""
from jarvis.system_integration.engine import SystemIntegrationEngine  # noqa: F401
from jarvis.system_integration.models import (  # noqa: F401
    CHECK_STATUSES,
    CHECK_TYPES,
    LAYER_REGISTRY,
    REQUIRED_MODULES,
    ArtifactRecord,
    FindingRecord,
    IntegrationSummary,
    SystemReportRecord,
    ValidationRecord,
    packages_unique,
    prefixes_unique,
    registered_packages,
    registered_prefixes,
    verify_hash_records,
)
