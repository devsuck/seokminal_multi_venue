"""Architecture Documentation & Freeze 자료형 (P36) — 문서화 전용. **리팩터링 없음.**

현재 Jarvis 아키텍처의 완전한 문서를 생성한다: 시스템 개요·계층 책임 맵·데이터 흐름·소유권 경계·원장 카탈로그·의존성 그래프·
보안 경계·연구 워크플로·모듈 레퍼런스. **핵심 아키텍처를 리팩터링하지 않는다 — 문서화만.** DOCUMENTATION ONLY ·
FREEZE ≠ REFACTOR. 결정적 생성(P35 레지스트리가 단일 진실). 상위 계층은 READ ONLY.
"""
from __future__ import annotations

import hashlib
import json

# ── 생성 문서 카탈로그(9종) ──
ARCHITECTURE_DOCS = (
    "01_system_architecture_overview.md",
    "02_layer_responsibility_map.md",
    "03_data_flow_diagram.md",
    "04_ownership_boundary.md",
    "05_ledger_catalog.md",
    "06_dependency_graph.md",
    "07_security_boundary.md",
    "08_research_workflow.md",
    "09_module_reference.md",
)

# ── 계층 책임 요약(P21~P34 + P35) — 문서 생성용 ──
LAYER_RESPONSIBILITIES = {
    "production_readiness": "배포 준비성·거버넌스 검토 기록 (VALIDATED != DEPLOYED)",
    "research_automation": "연구 자동화 오케스트레이션 기록 (COMPLETED != VALIDATED)",
    "research_monitoring": "연구 생태계 건강·관측성 관찰 (OBSERVE != CONTROL)",
    "research_reliability": "신뢰성 엔지니어링·복구 기록 (RECORD != REPAIR)",
    "autonomous_research": "자율 연구 개선 루프·지식 생성 (KNOWLEDGE != TRADING)",
    "research_agent_coordination": "연구 에이전트 협업 조정 (CONSENSUS != APPROVAL)",
    "research_memory_intelligence": "장기 연구 메모리 지능 (MEMORY DOES NOT DECIDE)",
    "research_insight_intelligence": "연구 통찰·해석 (INSIGHT != DECISION)",
    "research_strategy_generation": "연구 전략 후보 생성 (GENERATED != SELECTED)",
    "meta_research_intelligence": "연구 과정 메타 분석 (OBSERVATION != OPTIMIZATION)",
    "experiment_orchestration": "실험 조정 기록 (ORCHESTRATION != EXECUTION)",
    "research_resource_manager": "연구 자원 추적 (RECORD != ALLOCATE)",
    "research_api_gateway": "통합 읽기 전용 API (GATEWAY != EXECUTION)",
    "research_dashboard_backend": "백엔드 집계 (AGGREGATION != DECISION)",
    "system_integration": "시스템 통합·최종 검증 (VALIDATION != MUTATION)",
}

# ── 보안 경계 요약(전 계층 공통 불변) ──
SECURITY_BOUNDARIES = (
    "실행 권한 없음 (no execute/deploy/trade/allocate/approve)",
    "브로커 연결 없음 (no broker/live_trading imports)",
    "라이브 배포 없음 (no live deployment)",
    "자율 거래 없음 (no autonomous trading)",
    "append-only 원장 (no update/delete API)",
    "SHA256 해시체인 무결성 (tamper detectable)",
    "상위 계층 READ ONLY (no cross-ownership mutation)",
    "결정적 재현 (deterministic replay)",
)


def _digest(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def doc_hash(content) -> str:
    """문서 내용 해시(결정적)."""
    return _digest({"content": content})


def is_documented(package) -> bool:
    return package in LAYER_RESPONSIBILITIES
