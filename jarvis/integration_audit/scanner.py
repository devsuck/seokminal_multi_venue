"""Integration Audit 스캐너 (P41) — 파일시스템 + AST 정적 분석. **읽기전용, 코드 변경 없음.**

주어진 패키지 루트(기본: jarvis/)를 스캔해 모듈 인벤토리·의존성 엣지·미사용(orphan)·중복 계열·UI 페이지를 만든다.
파일을 읽기만 하며 절대 수정하지 않는다. 결정적(정렬된 출력).
"""
from __future__ import annotations

import ast
import os

from jarvis.integration_audit import models as M

# 스캔 제외 디렉토리
_SKIP_DIRS = {"__pycache__", "tests", "_state"}
# orphan 판정에서 제외(엔트리포인트/루트성 모듈)
_ENTRYPOINTS = {"integration_audit", "local_runtime", "research_navigation",
                "research_assistant", "local_automation", "system_integration",
                "research_os", "research_os_core", "operations_console"}
# UI/페이지 성격의 백엔드 모듈
_UI_MODULES = {"research_dashboard_backend", "operations_console", "research_api",
               "research_api_gateway", "research_observatory", "research_control_plane"}


def default_root() -> str:
    """jarvis/ 패키지 디렉토리(이 파일의 상위)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def list_modules(root: str) -> list:
    """__init__.py 를 가진 하위 패키지 이름(정렬). tests/__pycache__/_state 제외."""
    out = []
    for entry in sorted(os.listdir(root)):
        d = os.path.join(root, entry)
        if not os.path.isdir(d) or entry in _SKIP_DIRS:
            continue
        if os.path.exists(os.path.join(d, "__init__.py")):
            out.append(entry)
    return out


def module_py_files(root: str, name: str) -> list:
    d = os.path.join(root, name)
    out = []
    for dirpath, dirnames, filenames in os.walk(d):
        dirnames[:] = [x for x in dirnames if x not in _SKIP_DIRS]
        for f in filenames:
            if f.endswith(".py"):
                out.append(os.path.join(dirpath, f))
    return sorted(out)


def classify_pattern(root: str, name: str) -> str:
    d = os.path.join(root, name)
    has = lambda f: os.path.exists(os.path.join(d, f))  # noqa: E731
    if has("engine.py") and has("ledger.py") and has("models.py"):
        return "standard"
    if has("engine.py") or has("models.py"):
        return "partial"
    return "other"


def module_info(root: str, name: str) -> M.ModuleInfo:
    files = module_py_files(root, name)
    d = os.path.join(root, name)
    return M.ModuleInfo(
        name=name, category=M.categorize(name), family=M.family_of(name),
        pattern=classify_pattern(root, name), py_files=len(files),
        has_tests=os.path.isdir(os.path.join(d, "tests")),
        has_cli=os.path.exists(os.path.join(d, "__main__.py")))


def inventory(root: str) -> list:
    return [module_info(root, n) for n in list_modules(root)]


def _imported_packages(path: str) -> set:
    """파일 하나의 AST 를 파싱해 참조하는 jarvis 하위 패키지 이름 집합."""
    try:
        tree = ast.parse(open(path, encoding="utf-8").read())
    except (SyntaxError, ValueError, OSError, UnicodeDecodeError):
        return set()
    out = set()
    for node in ast.walk(tree):
        mod = None
        if isinstance(node, ast.ImportFrom) and node.module:
            mod = node.module
        elif isinstance(node, ast.Import):
            for n in node.names:
                if n.name.startswith("jarvis."):
                    parts = n.name.split(".")
                    if len(parts) >= 2:
                        out.add(parts[1])
            continue
        if mod and mod.startswith("jarvis."):
            parts = mod.split(".")
            if len(parts) >= 2:
                out.add(parts[1])
    return out


def import_edges(root: str) -> list:
    """intra-jarvis 의존성 엣지 (src_pkg, dst_pkg) 집합(정렬). tests 코드는 제외."""
    modules = set(list_modules(root))
    edges = set()
    for src in modules:
        for path in module_py_files(root, src):
            if os.sep + "tests" + os.sep in path:
                continue
            for dst in _imported_packages(path):
                if dst in modules and dst != src:
                    edges.add((src, dst))
    return sorted(edges)


def in_degrees(root: str) -> dict:
    modules = list_modules(root)
    deg = {m: 0 for m in modules}
    for _src, dst in import_edges(root):
        deg[dst] = deg.get(dst, 0) + 1
    return deg


def orphan_modules(root: str) -> list:
    """어떤 모듈에도 import 되지 않는 패키지(엔트리포인트 제외) = 통합/보관 후보."""
    deg = in_degrees(root)
    return sorted(m for m, d in deg.items() if d == 0 and m not in _ENTRYPOINTS)


def name_clusters(modules) -> dict:
    """이름 계열별 그룹 {family: [names...]}. modules 는 이름 리스트 또는 ModuleInfo 리스트."""
    out: dict = {}
    for m in modules:
        name = m.name if hasattr(m, "name") else m
        out.setdefault(M.family_of(name), []).append(name)
    return {k: sorted(v) for k, v in out.items()}


def duplicate_clusters(root: str, min_size: int = 2) -> list:
    """min_size 이상 같은 계열 = 잠재 중복/과중복 클러스터(정렬)."""
    infos = {i.name: i for i in inventory(root)}
    clusters = []
    for fam, members in sorted(name_clusters(list(infos)).items()):
        if len(members) < min_size:
            continue
        cats = {infos[m].category for m in members}
        cat = sorted(cats)[0] if len(cats) == 1 else "MIXED"
        rec = ("동일 카테고리 계열 — 통합 검토 권장" if len(cats) == 1
               else "다중 카테고리 계열 — 책임 경계 재검토")
        clusters.append(M.DuplicateCluster(family=fam, category=cat, members=members,
                                           size=len(members), recommendation=rec))
    return clusters


def ui_pages(root: str) -> list:
    """UI/페이지 성격 백엔드 모듈 인벤토리(카테고리 포함). 별도 프론트엔드 저장소는 이 저장소에 없음."""
    present = [m for m in list_modules(root) if m in _UI_MODULES]
    return [{"module": m, "category": M.categorize(m), "pattern": classify_pattern(root, m)}
            for m in sorted(present)]
