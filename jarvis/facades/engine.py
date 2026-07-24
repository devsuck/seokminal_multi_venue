"""Consolidation Facades Engine (C1) — 과분할 계열의 단일 참조점. **읽기전용, 무손실.**

각 계열(coordination/oversight/observability/self_improvement)의 대표 문을 제공한다. P41 스캐너로 멤버 존재를
검증(READ ONLY)하고, 축소 효과를 집계한다. **하부 모듈을 import/변경/삭제하지 않는다** — 결합을 늘리지 않기 위해
멤버는 '이름'으로만 다룬다. 거래·집행·배포 없음. 엔진은 execute()/trade()/deploy()/allocate()/approve() 없음.
"""
from __future__ import annotations

from jarvis.facades import models as M
from jarvis.facades.models import FacadeInfo


class FacadeRegistry:
    """통합 파사드 레지스트리. 순수 결정적 · 원장 없음 · 하부 모듈 무결합(이름만 참조)."""

    def __init__(self, module_names=None) -> None:
        # module_names 주입 가능(테스트). 기본은 P41 스캐너로 실제 트리.
        self._modules = module_names

    def _present(self) -> set:
        if self._modules is not None:
            return set(self._modules)
        from jarvis.integration_audit import scanner
        return set(scanner.list_modules(scanner.default_root()))

    def families(self) -> list:
        return sorted(M.FAMILIES)

    def facade(self, name: str) -> FacadeInfo:
        if name not in M.FAMILIES:
            raise KeyError(f"미정의 파사드 {name}")
        spec = M.FAMILIES[name]
        present_all = self._present()
        declared = list(spec["members"])
        present = [m for m in declared if m in present_all]
        missing = [m for m in declared if m not in present_all]
        return FacadeInfo(
            name=name, description=spec["description"], representative=spec["representative"],
            declared_members=declared, present_members=present, missing_members=missing,
            member_count=len(present),
            reduction=f"{len(present)}개 모듈 → 참조점 1개")

    def all_facades(self) -> list:
        return [self.facade(n) for n in self.families()]

    def members_of(self, name: str) -> list:
        return self.facade(name).present_members

    def representative_of(self, name: str) -> str:
        return M.FAMILIES[name]["representative"]

    def resolve(self, module: str) -> str | None:
        """모듈 이름 → 소속 파사드명(없으면 None). 결정적."""
        for n, spec in M.FAMILIES.items():
            if module in spec["members"]:
                return n
        return None

    def summary(self) -> dict:
        facs = self.all_facades()
        covered = sum(f.member_count for f in facs)
        return {"facade_count": len(facs),
                "modules_covered": covered,
                "reduction": f"{covered}개 모듈 → 참조점 {len(facs)}개",
                "facades": [{"name": f.name, "representative": f.representative,
                             "members": f.member_count} for f in facs],
                "note": ("헌장 Integration Before Expansion. 하부 모듈은 프리즈 유지(무손실). "
                         "신규 개발은 파사드 대표 모듈을 우선 확장하라 — 새 패키지 금지.")}
