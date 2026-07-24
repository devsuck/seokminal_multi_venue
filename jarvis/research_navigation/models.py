"""Unified Navigation 자료형 (P43) — 통합 정보구조(IA). **UI 결정 권한 없음, 거래·집행 없음.**

기존 페이지/모듈을 단순한 네비게이션 트리(Home → Research/Knowledge/Agents/System)로 재배치한다. **새 대시보드를
만들지 않는다 — 기존 기능을 보존하며 재배치만.** P41 integration_audit.categorize() 를 재사용(통합). 결정적·읽기전용.
거래·집행·배포·승인 없음.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

from jarvis.integration_audit.models import (  # P41 재사용 — 중복 금지
    CAT_AGENTS,
    CAT_EXECUTION,
    CAT_KNOWLEDGE,
    CAT_MONITORING,
    CAT_OTHER,
    CAT_RESEARCH,
    CAT_SIMULATION,
    CAT_SYSTEM,
    categorize,
    family_of,
)

# ── 최상위 섹션 ──
SEC_RESEARCH = "Research"
SEC_KNOWLEDGE = "Knowledge"
SEC_AGENTS = "Agents"
SEC_SYSTEM = "System"
SECTIONS = (SEC_RESEARCH, SEC_KNOWLEDGE, SEC_AGENTS, SEC_SYSTEM)

# ── 섹션별 하위 항목(목표 IA) ──
NAV_ITEMS = {
    SEC_RESEARCH: ("Alpha", "Simulation", "Experiments"),
    SEC_KNOWLEDGE: ("Graph", "Memory", "Insights"),
    SEC_AGENTS: ("Tasks", "History"),
    SEC_SYSTEM: ("Monitoring", "Configuration"),
}

# ── 카테고리 → 섹션 매핑(P41 카테고리 재사용) ──
_CATEGORY_TO_SECTION = {
    CAT_RESEARCH: SEC_RESEARCH,
    CAT_SIMULATION: SEC_RESEARCH,
    CAT_KNOWLEDGE: SEC_KNOWLEDGE,
    CAT_AGENTS: SEC_AGENTS,
    CAT_MONITORING: SEC_SYSTEM,
    CAT_SYSTEM: SEC_SYSTEM,
    CAT_EXECUTION: SEC_SYSTEM,
    CAT_OTHER: SEC_SYSTEM,
}

# ── 섹션 안에서 항목 배정 규칙(키워드 우선순위; 첫 일치, 없으면 default) ──
# (섹션: [(항목, 키워드튜플)...], default 항목)
_ITEM_RULES = {
    SEC_RESEARCH: ([
        ("Experiments", ("experiment",)),
        ("Simulation", ("simulation", "paper", "backtest")),
    ], "Alpha"),
    SEC_KNOWLEDGE: ([
        ("Graph", ("_kg", "kg", "graph")),
        ("Memory", ("memory",)),
    ], "Insights"),
    SEC_AGENTS: ([
        ("History", ("history", "audit", "evolution", "learning", "experience")),
    ], "Tasks"),
    SEC_SYSTEM: ([
        ("Monitoring", ("monitoring", "observ", "diagnostic", "health", "benchmark",
                        "resilience", "profiling", "watchdog")),
    ], "Configuration"),
}

# ── 기존 대시보드 패널 유형 → 섹션(보존·통합용) ──
PANEL_TO_SECTION = {
    "STATISTICS": SEC_RESEARCH,
    "TIMELINE": SEC_RESEARCH,
    "RESEARCH_PROGRESS": SEC_RESEARCH,
    "KNOWLEDGE_SUMMARY": SEC_KNOWLEDGE,
    "HEALTH": SEC_SYSTEM,
    "MONITORING": SEC_SYSTEM,
}

FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "ACTIVATE_LIVE",
    "APPROVE_FOR_TRADING", "EXECUTE", "DEPLOY", "TRADE", "ALLOCATE", "APPROVE", "DECIDE",
})


def _digest(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def content_digest(payload) -> str:
    return _digest(payload)


def is_forbidden_verb(word) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def section_for(name: str) -> str:
    """모듈 이름 → 최상위 섹션(P41 카테고리 경유). 결정적."""
    return _CATEGORY_TO_SECTION.get(categorize(name), SEC_SYSTEM)


def item_for(name: str) -> tuple:
    """모듈 이름 → (섹션, 항목). 결정적. 키워드 규칙 우선, 없으면 섹션 default."""
    sec = section_for(name)
    rules, default = _ITEM_RULES[sec]
    n = (name or "").lower()
    for item, keywords in rules:
        if any(k in n for k in keywords):
            return sec, item
    return sec, default


@dataclass(frozen=True)
class NavItem:
    section: str
    item: str
    module_count: int
    modules: list

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class NavSection:
    section: str
    item_count: int
    module_count: int
    items: list             # [NavItem.to_dict()]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DuplicatePage:
    section: str
    item: str
    family: str
    members: list

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class NavManifest:
    section_count: int
    item_count: int
    module_count: int
    coverage: float          # 배치된 모듈 / 전체 모듈
    duplicate_page_count: int
    digest: str
    generated_at: str
    sections: list = field(default_factory=list)
    duplicate_pages: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


__all__ = ["SECTIONS", "NAV_ITEMS", "PANEL_TO_SECTION", "NavItem", "NavSection", "NavManifest",
           "DuplicatePage", "section_for", "item_for", "categorize", "family_of",
           "is_forbidden_verb", "content_digest"]
