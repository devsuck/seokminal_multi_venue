"""Architecture 일관성 검증 (P36) — 문서·아키텍처 일관성 정적 검사. **문서화만, 변경 없음.**

중복 책임·미사용 모듈·의존성 위반·소유권 모호성을 분석한다. 핵심 아키텍처는 리팩터링하지 않는다. READ ONLY.
"""
from __future__ import annotations

from jarvis.architecture_docs import generator, models as M
from jarvis.system_integration.models import LAYER_REGISTRY, packages_unique, prefixes_unique


def check_all_layers_documented() -> dict:
    """모든 등록 계층이 책임 맵에 문서화됨."""
    missing = [l["package"] for l in LAYER_REGISTRY if not M.is_documented(l["package"])]
    return {"check": "all_documented", "ok": not missing, "missing": missing}


def check_no_duplicate_responsibilities() -> dict:
    """중복 책임: 책임 문자열 유일(계층별 고유 책임)."""
    resp = [M.LAYER_RESPONSIBILITIES[l["package"]] for l in LAYER_REGISTRY
            if l["package"] in M.LAYER_RESPONSIBILITIES]
    dupes = sorted({r for r in resp if resp.count(r) > 1})
    return {"check": "no_duplicate_responsibilities", "ok": not dupes, "duplicates": dupes}


def check_ownership_unambiguous() -> dict:
    """소유권 모호성 없음: 접두사·패키지 유일."""
    ok = prefixes_unique() and packages_unique()
    return {"check": "ownership_unambiguous", "ok": ok}


def check_no_dependency_violations() -> dict:
    """의존성 위반 없음: 의존성 그래프 순환 없음(단방향 상위 참조)."""
    from jarvis.system_integration.engine import SystemIntegrationEngine
    graph = SystemIntegrationEngine().dependency_graph()
    # DFS 순환 탐지
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {}

    def dfs(n):
        color[n] = GRAY
        for m in graph.get(n, []):
            c = color.get(m, WHITE)
            if c == GRAY:
                return True
            if c == WHITE and dfs(m):
                return True
        color[n] = BLACK
        return False

    cyclic = any(color.get(n, WHITE) == WHITE and dfs(n) for n in sorted(graph))
    return {"check": "no_dependency_violations", "ok": not cyclic}


def check_docs_generated() -> dict:
    """9개 문서 모두 생성 가능·비어있지 않음."""
    docs = generator.generate_docs()
    complete = set(docs) == set(M.ARCHITECTURE_DOCS) and all(len(c) > 0 for c in docs.values())
    return {"check": "docs_generated", "ok": complete, "count": len(docs)}


def check_docs_deterministic() -> dict:
    """문서 생성 결정적(동일 입력 → 동일 산출)."""
    a = generator.generate_docs()
    b = generator.generate_docs()
    return {"check": "docs_deterministic", "ok": a == b}


def run_consistency_checks() -> dict:
    """전체 아키텍처 일관성 검사."""
    checks = [check_all_layers_documented(), check_no_duplicate_responsibilities(),
              check_ownership_unambiguous(), check_no_dependency_violations(),
              check_docs_generated(), check_docs_deterministic()]
    return {"ok": all(c["ok"] for c in checks), "checks": checks}
