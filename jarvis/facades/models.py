"""Consolidation Facades 자료형 (C1) — 과분할 계열의 단일 참조점. **읽기전용, 무손실.**

헌장 "Simplicity Over Complexity / Integration Before Expansion" 실행. 겹치는 연구 모듈 계열마다 **대표 문(파사드)**
하나를 정의해, 신규 개발·문서·온보딩이 계열당 1개만 보게 한다. **하부 모듈은 변경/삭제하지 않는다(프리즈 유지).**
파사드는 얇은 레지스트리일 뿐 — 새 엔진/원장/지능 계층이 아니다. 거래·집행 없음.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

# ── 계열 정의: 파사드명 → (설명, 대표 모듈, 흡수 대상 멤버들) ──
# 근거: docs/maintainability_review.md (테마별 과분할 분석)
FAMILIES = {
    "coordination": {
        "description": "연구 에이전트/팀/세션 조율·관리. 9개 모듈이 사실상 같은 책임.",
        "representative": "research_orchestration",
        "members": [
            "research_agents", "research_coordinator", "research_council",
            "research_organization", "research_orchestration", "research_operations",
            "research_manager", "research_control", "research_collaboration",
        ],
    },
    "oversight": {
        "description": "연구 감독·거버넌스·검증·신뢰성. 5개 모듈이 겹치는 감독 책임.",
        "representative": "research_governance",
        "members": [
            "research_governance", "research_compliance", "research_reviewer",
            "research_validation", "research_reliability",
        ],
    },
    "observability": {
        "description": "연구 관측·모니터링·관측소. 3개 모듈이 같은 관측 책임.",
        "representative": "research_observability",
        "members": [
            "research_observability", "research_observatory", "research_monitoring",
        ],
    },
    "self_improvement": {
        "description": "연구 진화·개선·학습·생애주기. 4개 모듈이 겹치는 자기개선 책임.",
        "representative": "research_improvement",
        "members": [
            "research_evolution", "research_improvement", "research_learning",
            "research_lifecycle",
        ],
    },
}

FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "ACTIVATE_LIVE",
    "EXECUTE", "DEPLOY", "TRADE", "ALLOCATE", "APPROVE",
})


def is_forbidden_verb(word) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


@dataclass(frozen=True)
class FacadeInfo:
    name: str
    description: str
    representative: str
    declared_members: list
    present_members: list      # 실제 트리에 존재하는 멤버
    missing_members: list      # 선언됐지만 트리에 없는 멤버
    member_count: int
    reduction: str             # 축소 효과 요약

    def to_dict(self) -> dict:
        return asdict(self)
