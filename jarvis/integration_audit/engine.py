"""Integration Audit Engine (P41) — 기존 Jarvis 통합 감사·통합 제안·로드맵·문서 렌더. **읽기전용.**

기존 시스템을 스캔·분석해 결정적 감사 리포트와 통합 제안·로드맵을 만들고, docs/integration_audit/ 에 마크다운을
렌더한다. **기존 원장·레코드·코드는 절대 변경하지 않는다.** 새 지능 계층·핵심 연구 로직 리팩터 없음. 거래·집행·배포 없음.
"""
from __future__ import annotations

import os

from jarvis.integration_audit import models as M
from jarvis.integration_audit import scanner

# 통합 검토 우선순위가 높은(큰) 계열 임계치
_INTEGRATE_MIN = 3


class IntegrationAuditEngine:
    """기존 아키텍처 통합 감사 엔진. 순수 정적 분석(읽기전용) — 상태 기록/원장 없음(복잡도 최소화)."""

    def __init__(self, root: str | None = None) -> None:
        self.root = root or scanner.default_root()

    # ── 스캔 결과 ──
    def inventory(self) -> list:
        return scanner.inventory(self.root)

    def module_names(self) -> list:
        return scanner.list_modules(self.root)

    def dependency_stats(self) -> M.DependencyStats:
        edges = scanner.import_edges(self.root)
        deg = scanner.in_degrees(self.root)
        top = sorted(deg.items(), key=lambda kv: (-kv[1], kv[0]))[:15]
        return M.DependencyStats(edge_count=len(edges), node_count=len(deg),
                                 top_imported=[list(t) for t in top],
                                 orphans=scanner.orphan_modules(self.root))

    def duplicate_clusters(self) -> list:
        return scanner.duplicate_clusters(self.root)

    def orphans(self) -> list:
        return scanner.orphan_modules(self.root)

    def ui_inventory(self) -> list:
        return scanner.ui_pages(self.root)

    def category_distribution(self) -> dict:
        dist: dict = {}
        for i in self.inventory():
            dist[i.category] = dist.get(i.category, 0) + 1
        return dict(sorted(dist.items()))

    def pattern_distribution(self) -> dict:
        dist: dict = {}
        for i in self.inventory():
            dist[i.pattern] = dist.get(i.pattern, 0) + 1
        return dict(sorted(dist.items()))

    # ── 통합 제안(결정적) ──
    def integration_proposals(self) -> list:
        proposals = []
        for c in self.duplicate_clusters():
            if c.category == "MIXED":
                action, rationale = "REVIEW", "다중 카테고리 계열 — 책임 경계 재정의 후 결정"
            elif c.size >= _INTEGRATE_MIN:
                action, rationale = "INTEGRATE", f"{c.size}개 동일계열 — 공용 파사드로 통합 검토(중복 축소)"
            else:
                action, rationale = "KEEP", "소규모 계열 — 현행 유지, 통합 이득 낮음"
            proposals.append(M.IntegrationProposal(
                family=c.family, category=c.category, members=c.members, action=action,
                rationale=rationale))
        return proposals

    def roadmap(self) -> list:
        """통합 로드맵(순서화된 단계). 결정적."""
        integ = [p for p in self.integration_proposals() if p.action == "INTEGRATE"]
        review = [p for p in self.integration_proposals() if p.action == "REVIEW"]
        steps = [
            "1. 로컬 런타임 단일 진입점 도입(P42) — 기존 boot()/status() 통합, 중복 스크립트 제거",
            "2. 통합 네비게이션 정보구조 도입(P43) — 기존 페이지를 카테고리로 재배치, 신규 대시보드 생성 금지",
            "3. 개인 연구 어시스턴트(P44) — 기존 원장 READ ONLY 요약, 신규 지능 계층 없음",
            "4. 로컬 자동화(P45) — 반복 연구 작업 워크플로화, 거래/배포/배분 없음",
        ]
        for p in integ:
            steps.append(f"통합 검토: {p.family}_* 계열({p.category}, {len(p.members)}개) → 공용 파사드")
        for p in review:
            steps.append(f"경계 재검토: {p.family}_* 계열(MIXED, {len(p.members)}개)")
        return steps

    # ── 리포트 ──
    def build_report(self, generated_at: str = "") -> M.AuditReport:
        inv = self.inventory()
        clusters = self.duplicate_clusters()
        proposals = self.integration_proposals()
        core = {
            "module_count": len(inv),
            "categories": self.category_distribution(),
            "patterns": self.pattern_distribution(),
            "clusters": [c.family for c in clusters],
            "orphans": self.orphans(),
            "proposals": [(p.family, p.action) for p in proposals],
            "ui": [u["module"] for u in self.ui_inventory()],
        }
        return M.AuditReport(
            module_count=len(inv), category_distribution=self.category_distribution(),
            pattern_distribution=self.pattern_distribution(),
            duplicate_cluster_count=len(clusters), orphan_count=len(self.orphans()),
            proposal_count=len(proposals), ui_page_count=len(self.ui_inventory()),
            digest=M.content_digest(core), generated_at=generated_at,
            modules=[i.to_dict() for i in inv],
            duplicate_clusters=[c.to_dict() for c in clusters],
            proposals=[p.to_dict() for p in proposals])

    def summary(self, generated_at: str = "") -> dict:
        r = self.build_report(generated_at)
        return {"module_count": r.module_count, "category_distribution": r.category_distribution,
                "pattern_distribution": r.pattern_distribution,
                "duplicate_cluster_count": r.duplicate_cluster_count,
                "orphan_count": r.orphan_count, "proposal_count": r.proposal_count,
                "ui_page_count": r.ui_page_count, "digest": r.digest}

    # ── 문서 렌더(docs/integration_audit/ 에 신규 파일만 생성) ──
    def _md_inventory(self) -> str:
        lines = ["# 1. Module Inventory (모듈 인벤토리)", "",
                 f"총 {len(self.inventory())}개 모듈. 카테고리/패턴/파일수/테스트/CLI.", "",
                 "| Module | Category | Pattern | .py | tests | cli |",
                 "|---|---|---|---|---|---|"]
        for i in self.inventory():
            lines.append(f"| {i.name} | {i.category} | {i.pattern} | {i.py_files} | "
                         f"{'✓' if i.has_tests else ''} | {'✓' if i.has_cli else ''} |")
        return "\n".join(lines) + "\n"

    def _md_architecture(self) -> str:
        dist = self.category_distribution()
        lines = ["# 2. Current Architecture (현재 아키텍처)", "",
                 "카테고리별 모듈 분포(연구 환경 정보구조):", ""]
        for cat, n in dist.items():
            lines.append(f"- **{cat}**: {n}개")
        lines += ["", "```", "Jarvis (기존 P1~P40+ 기반, READ ONLY)", "│"]
        for cat in M.CATEGORIES:
            if cat in dist:
                lines.append(f"├─ {cat} ({dist[cat]})")
        lines += ["```", ""]
        return "\n".join(lines) + "\n"

    def _md_dependencies(self) -> str:
        s = self.dependency_stats()
        lines = ["# 3. Dependency Graph (의존성 그래프)", "",
                 f"노드 {s.node_count}개 · 엣지 {s.edge_count}개(intra-jarvis import).", "",
                 "## 가장 많이 참조되는 모듈(in-degree 상위)", "",
                 "| Module | in-degree |", "|---|---|"]
        for name, deg in s.top_imported:
            lines.append(f"| {name} | {deg} |")
        return "\n".join(lines) + "\n"

    def _md_ui(self) -> str:
        lines = ["# 4. UI / Page Inventory (UI·페이지 인벤토리)", "",
                 "이 저장소에는 별도 프론트엔드 코드가 없다(대시보드 UI는 별도 저장소). "
                 "백엔드 페이지/라우팅 성격 모듈:", "",
                 "| Module | Category | Pattern |", "|---|---|---|"]
        for u in self.ui_inventory():
            lines.append(f"| {u['module']} | {u['category']} | {u['pattern']} |")
        return "\n".join(lines) + "\n"

    def _md_duplicates(self) -> str:
        lines = ["# 5. Duplicate / Overlap Analysis (중복·과중복 분석)", "",
                 "같은 이름 계열(family) ≥2 = 잠재 중복/책임 중첩 후보:", "",
                 "| Family | Category | Size | Members | Recommendation |",
                 "|---|---|---|---|---|"]
        for c in self.duplicate_clusters():
            lines.append(f"| {c.family}_* | {c.category} | {c.size} | "
                         f"{', '.join(c.members)} | {c.recommendation} |")
        return "\n".join(lines) + "\n"

    def _md_unused(self) -> str:
        orph = self.orphans()
        lines = ["# 6. Unused / Orphan Analysis (미사용·고립 분석)", "",
                 f"다른 모듈에서 import 되지 않는 패키지 {len(orph)}개(엔트리포인트 제외). "
                 "= 통합·보관(archive) 후보. **자동 삭제하지 않음 — 검토 후 결정.**", ""]
        for o in orph:
            lines.append(f"- {o} ({M.categorize(o)})")
        return "\n".join(lines) + "\n"

    def _md_proposal(self) -> str:
        lines = ["# 7. Integration Proposal & Roadmap (통합 제안·로드맵)", "",
                 "## 통합 제안(계열별, 결정적)", "",
                 "| Family | Category | Action | Members | Rationale |",
                 "|---|---|---|---|---|"]
        for p in self.integration_proposals():
            lines.append(f"| {p.family}_* | {p.category} | **{p.action}** | "
                         f"{len(p.members)} | {p.rationale} |")
        lines += ["", "## 통합 로드맵", ""]
        for step in self.roadmap():
            lines.append(f"- {step}")
        lines += ["", "> 원칙: 기존 소유 경계 불변 · 기존 원장 READ ONLY · 추가만 · 마이그레이션/덮어쓰기 없음 · "
                  "기능이 이미 있으면 INTEGRATE(중복 금지).", ""]
        return "\n".join(lines) + "\n"

    def render_docs(self, out_dir: str, generated_at: str = "") -> list:
        """docs/integration_audit/ 에 감사 문서 7종 + README 렌더. 신규 파일만 생성(덮어쓰기는 감사 산출물 자체만)."""
        os.makedirs(out_dir, exist_ok=True)
        r = self.build_report(generated_at)
        files = {
            "01_module_inventory.md": self._md_inventory(),
            "02_architecture.md": self._md_architecture(),
            "03_dependency_graph.md": self._md_dependencies(),
            "04_ui_page_inventory.md": self._md_ui(),
            "05_duplicate_analysis.md": self._md_duplicates(),
            "06_unused_analysis.md": self._md_unused(),
            "07_integration_proposal.md": self._md_proposal(),
            "README.md": (
                "# Jarvis Integration Audit (P41)\n\n"
                "기존 Jarvis 아키텍처의 결정적 통합 감사 산출물. "
                "`python -m jarvis.integration_audit render` 로 재생성 가능(읽기전용 정적 분석).\n\n"
                f"- 모듈 수: {r.module_count}\n- 중복 계열: {r.duplicate_cluster_count}\n"
                f"- 고립 모듈: {r.orphan_count}\n- 통합 제안: {r.proposal_count}\n"
                f"- 감사 digest: `{r.digest}`\n\n"
                "문서: 01 인벤토리 · 02 아키텍처 · 03 의존성 · 04 UI · 05 중복 · 06 미사용 · 07 통합제안.\n\n"
                "> 기존 P1~P40+ 는 기반이며 불변(READ ONLY). 추가만, 마이그레이션 없음.\n"),
        }
        written = []
        for fname, content in files.items():
            p = os.path.join(out_dir, fname)
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
            written.append(p)
        return sorted(written)
