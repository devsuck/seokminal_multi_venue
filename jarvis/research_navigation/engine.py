"""Unified Navigation Engine (P43) — 기존 페이지/모듈을 단순 IA 로 재배치. **읽기전용, 결정 권한 없음.**

기존 Jarvis 모듈(P41 스캐너로 발견)을 목표 네비게이션 트리(Home → Research/Knowledge/Agents/System)로 결정적으로
매핑한다. **새 대시보드 생성 금지 — 기존 기능 보존, 재배치만.** 중복/미배치 페이지를 표면화하고 네비게이션 매니페스트와
문서를 렌더한다. 거래·집행·배포·승인 없음. 엔진은 execute()/trade()/deploy()/allocate()/approve() 를 노출하지 않는다.
"""
from __future__ import annotations

import os

from jarvis.research_navigation import models as M


class NavigationEngine:
    """통합 네비게이션 빌더. 순수 결정적(원장 없음 — 복잡도 최소화). 기존 모듈 READ ONLY 발견."""

    def __init__(self, modules=None) -> None:
        # modules 주입 가능(테스트). 기본은 P41 스캐너로 실제 트리 발견.
        self._modules = modules

    def modules(self) -> list:
        if self._modules is not None:
            return sorted(self._modules)
        from jarvis.integration_audit import scanner  # P41 재사용
        return scanner.list_modules(scanner.default_root())

    # ── 매핑 ──
    def assign(self) -> dict:
        """{(section, item): [modules]} 결정적 배치."""
        out: dict = {}
        for name in self.modules():
            key = M.item_for(name)
            out.setdefault(key, []).append(name)
        return {k: sorted(v) for k, v in out.items()}

    def nav_items(self) -> list:
        assigned = self.assign()
        items = []
        for section in M.SECTIONS:
            for item in M.NAV_ITEMS[section]:
                mods = assigned.get((section, item), [])
                items.append(M.NavItem(section=section, item=item, module_count=len(mods),
                                       modules=mods))
        return items

    def nav_sections(self) -> list:
        by_item = {(i.section, i.item): i for i in self.nav_items()}
        sections = []
        for section in M.SECTIONS:
            its = [by_item[(section, item)] for item in M.NAV_ITEMS[section]]
            sections.append(M.NavSection(
                section=section, item_count=len(its),
                module_count=sum(i.module_count for i in its),
                items=[i.to_dict() for i in its]))
        return sections

    def tree(self) -> dict:
        """Home 을 루트로 하는 네비게이션 트리(딕셔너리)."""
        return {"Home": {s.section: {i["item"]: i["modules"] for i in s.items}
                         for s in self.nav_sections()}}

    # ── 커버리지·중복 ──
    def coverage(self) -> float:
        total = len(self.modules())
        if total == 0:
            return 1.0
        placed = sum(len(v) for v in self.assign().values())
        return round(placed / total, 6)

    def unplaced(self) -> list:
        """어떤 항목에도 배치되지 않은 모듈(항상 빈 목록이어야 — 모든 모듈은 default 로라도 배치됨)."""
        placed = {m for v in self.assign().values() for m in v}
        return sorted(set(self.modules()) - placed)

    def duplicate_pages(self) -> list:
        """같은 항목 안에서 같은 이름 계열(family) ≥2 = 통합 검토 후보(혼란 페이지)."""
        dups = []
        for (section, item), mods in sorted(self.assign().items()):
            fams: dict = {}
            for m in mods:
                fams.setdefault(M.family_of(m), []).append(m)
            for fam, members in sorted(fams.items()):
                if len(members) >= 2:
                    dups.append(M.DuplicatePage(section=section, item=item, family=fam,
                                                members=sorted(members)))
        return dups

    def panel_mapping(self) -> dict:
        """기존 대시보드 패널 유형 → 섹션(보존·통합). 결정적."""
        return dict(sorted(M.PANEL_TO_SECTION.items()))

    # ── 매니페스트 ──
    def build_manifest(self, generated_at: str = "") -> M.NavManifest:
        sections = self.nav_sections()
        dups = self.duplicate_pages()
        core = {"sections": [s.to_dict() for s in sections],
                "coverage": self.coverage(), "dups": [d.to_dict() for d in dups]}
        return M.NavManifest(
            section_count=len(sections),
            item_count=sum(s.item_count for s in sections),
            module_count=len(self.modules()), coverage=self.coverage(),
            duplicate_page_count=len(dups), digest=M.content_digest(core),
            generated_at=generated_at, sections=[s.to_dict() for s in sections],
            duplicate_pages=[d.to_dict() for d in dups])

    def summary(self, generated_at: str = "") -> dict:
        man = self.build_manifest(generated_at)
        return {"section_count": man.section_count, "item_count": man.item_count,
                "module_count": man.module_count, "coverage": man.coverage,
                "duplicate_page_count": man.duplicate_page_count, "digest": man.digest}

    # ── 문서 렌더(docs/navigation/) ──
    def render_docs(self, out_dir: str, generated_at: str = "") -> list:
        os.makedirs(out_dir, exist_ok=True)
        man = self.build_manifest(generated_at)
        lines = ["# Jarvis Unified Navigation (P43)", "",
                 "기존 페이지/모듈을 단순 정보구조로 재배치(새 대시보드 없음, 기능 보존).", "",
                 f"- 섹션 {man.section_count} · 항목 {man.item_count} · 모듈 {man.module_count}",
                 f"- 커버리지 {man.coverage} · 중복 페이지 계열 {man.duplicate_page_count}",
                 f"- digest `{man.digest}`", "", "```", "Home"]
        for s in self.nav_sections():
            lines.append(f"├─ {s.section} ({s.module_count})")
            for it in s.items:
                lines.append(f"│   ├ {it['item']} ({it['module_count']})")
        lines += ["```", "", "## 항목별 백킹 모듈", ""]
        for s in self.nav_sections():
            lines.append(f"### {s.section}")
            for it in s.items:
                mods = ", ".join(it["modules"]) or "—"
                lines.append(f"- **{it['item']}** ({it['module_count']}): {mods}")
            lines.append("")
        lines += ["## 중복·혼란 페이지 후보(같은 항목 동일 계열 ≥2)", ""]
        for d in self.duplicate_pages():
            lines.append(f"- {d.section}/{d.item}: {d.family}_* → {', '.join(d.members)}")
        lines += ["", "## 기존 대시보드 패널 통합 매핑", ""]
        for panel, sec in self.panel_mapping().items():
            lines.append(f"- {panel} → {sec}")
        lines += ["", "> 기존 기능 보존 · 새 대시보드 생성 금지 · 재배치만 · 거래/집행/승인 없음.", ""]
        p = os.path.join(out_dir, "navigation.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        import json as _json
        pj = os.path.join(out_dir, "navigation_manifest.json")
        with open(pj, "w", encoding="utf-8") as f:
            f.write(_json.dumps(man.to_dict(), ensure_ascii=False, indent=2))
        return sorted([p, pj])
