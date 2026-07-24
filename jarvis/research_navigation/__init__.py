"""jarvis.research_navigation — Unified UI & Navigation (P43). **읽기전용, 결정 권한 없음.**

기존 Jarvis 페이지/모듈을 단순 정보구조(Home → Research/Knowledge/Agents/System)로 재배치한다. **새 대시보드를
만들지 않고 기존 기능을 보존한다 — 재배치만.** P41 integration_audit.categorize() 를 재사용(통합, 중복 금지).
결정적 매니페스트·문서 렌더. 거래·집행·배포·승인 없음. 엔진은 execute()/trade()/deploy()/allocate()/approve() 없음.
기존 P1~P42 불변.
"""
from jarvis.research_navigation.engine import NavigationEngine  # noqa: F401
from jarvis.research_navigation.models import (  # noqa: F401
    NAV_ITEMS,
    PANEL_TO_SECTION,
    SECTIONS,
    DuplicatePage,
    NavItem,
    NavManifest,
    NavSection,
    item_for,
    section_for,
)
