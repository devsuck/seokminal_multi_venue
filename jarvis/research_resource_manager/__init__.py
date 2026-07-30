"""jarvis.research_resource_manager — Research Resource Manager Layer (P32). **자동 배분·프로비저닝 없음.**

**ARCHIVED (Phase1 STEP3-B, 2026-07-31):** no active real-import caller found; only historically referenced by security_audit's dynamic AUDIT_TARGETS scan (outside default testpaths). Migration: if security_audit scanning is revived, this is a listed consumer; otherwise safe candidate for full removal in a later phase.

연구 자원을 추적한다: 데이터셋·컴퓨트·스토리지·연구 예산·GPU 사용·실험 배분. Resource Registry·Usage·Budget·
Allocation·Reports·Lineage 를 소유한다.

**기록만 한다 — 자동으로 배분하지 않으며 인프라를 프로비저닝하지 않는다.** execution/broker/live_trading/
portfolio_execution import·호출 없음. RECORD ≠ ALLOCATE · RECORD ≠ PROVISION · TRACK ≠ EXECUTE. 불변·append-only·
해시체인·결정적·재현. 상위 계층(P10~P31)은 READ ONLY. 원장 rrm_ 접두사.
"""
from jarvis.research_resource_manager.engine import ResearchResourceManagerEngine  # noqa: F401
from jarvis.research_resource_manager.models import (  # noqa: F401
    BUDGET_CATEGORIES,
    RESOURCE_TYPES,
    USAGE_PURPOSES,
    AllocationRecord,
    ArtifactRecord,
    BudgetRecord,
    ResourceRecord,
    ResourceReportRecord,
    ResourceSummary,
    UnknownEntityError,
    UsageRecord,
    classify_utilization,
    ratio,
    utilization,
)
