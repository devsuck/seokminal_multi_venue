"""의존성 감사 (P15) — 스캔·미사용·구버전·중복·그래프·리포트. **읽기 전용·결정적.**

설치·업그레이드·네트워크 조회를 하지 않는다. '구버전'은 주입된 latest_versions 맵으로, '미사용'은 주입된 임포트
집합으로 결정적으로 판정한다. 기존 모듈/원장을 변경하지 않는다(완전 additive).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from jarvis.dependency.manifest import Requirement, canonicalize, parse_pyproject


@dataclass(frozen=True)
class DependencyFinding:
    code: str
    severity: str            # INFO / WARNING
    package: str
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


def scan_dependencies(pyproject_text: str) -> dict:
    """pyproject 의존성 스캔 → 정규화 목록(결정적, 정렬)."""
    parsed = parse_pyproject(pyproject_text)
    deps = parsed["dependencies"]
    rows = sorted(({"name": r.name, "canonical": r.canonical, "operator": r.operator,
                    "version": r.version, "pinned": r.operator == "=="} for r in deps),
                  key=lambda d: d["canonical"])
    optional = {k: sorted(canonicalize(r.name) for r in v)
                for k, v in sorted(parsed["optional"].items())}
    return {"count": len(rows), "dependencies": rows, "optional": optional,
            "unpinned": sorted(d["canonical"] for d in rows if not d["pinned"])}


def detect_duplicates(pyproject_text: str) -> list:
    """중복 의존성(정규화 이름 기준, main+optional 전반) 탐지."""
    parsed = parse_pyproject(pyproject_text)
    seen: dict = {}
    for r in parsed["dependencies"]:
        seen.setdefault(r.canonical, []).append("main")
    for extra, reqs in parsed["optional"].items():
        for r in reqs:
            seen.setdefault(r.canonical, []).append(extra)
    dups = []
    for name, where in sorted(seen.items()):
        if len(where) > 1:
            dups.append(DependencyFinding("DUPLICATE_DEP", "WARNING", name,
                                          f"declared in: {sorted(where)}").to_dict())
    return dups


def detect_unused(pyproject_text: str, imported_modules, *, mapping: dict | None = None) -> list:
    """미사용 의존성(선언되었으나 임포트 집합에 없음) 탐지. mapping: dist→import 이름 보정."""
    parsed = parse_pyproject(pyproject_text)
    imported = {canonicalize(m) for m in imported_modules}
    mp = {canonicalize(k): canonicalize(v) for k, v in (mapping or {}).items()}
    out = []
    for r in sorted(parsed["dependencies"], key=lambda x: x.canonical):
        import_name = mp.get(r.canonical, r.canonical)
        if import_name not in imported:
            out.append(DependencyFinding("UNUSED_DEP", "INFO", r.canonical,
                                         "declared but not imported").to_dict())
    return out


def detect_outdated(pyproject_text: str, latest_versions: dict) -> list:
    """구버전 의존성(선언 version < latest_versions[name]) 탐지. 결정적 문자열 비교(튜플화)."""
    parsed = parse_pyproject(pyproject_text)
    latest = {canonicalize(k): v for k, v in latest_versions.items()}
    out = []
    for r in sorted(parsed["dependencies"], key=lambda x: x.canonical):
        lv = latest.get(r.canonical)
        if lv and r.version and _vt(r.version) < _vt(lv):
            out.append(DependencyFinding("OUTDATED_DEP", "WARNING", r.canonical,
                                         f"{r.version} < {lv}").to_dict())
    return out


def _vt(v: str) -> tuple:
    """버전 문자열 → 비교 가능한 정수 튜플(비숫자 파트는 0)."""
    parts = []
    for p in str(v).replace("-", ".").split("."):
        num = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(num) if num else 0)
    return tuple(parts)


def dependency_graph(edges: list) -> dict:
    """의존성 그래프(node→deps) 구성 + 순환 탐지. edges: [(pkg, dep), ...]."""
    graph: dict = {}
    nodes: set = set()
    for a, b in edges:
        graph.setdefault(canonicalize(a), set()).add(canonicalize(b))
        nodes.add(canonicalize(a))
        nodes.add(canonicalize(b))
    adj = {n: sorted(graph.get(n, set())) for n in sorted(nodes)}
    return {"nodes": sorted(nodes), "edges": adj, "node_count": len(nodes),
            "has_cycle": _has_cycle(graph, nodes)}


def _has_cycle(graph: dict, nodes: set) -> bool:
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {}

    def dfs(n) -> bool:
        color[n] = GRAY
        for m in sorted(graph.get(n, ())):
            c = color.get(m, WHITE)
            if c == GRAY:
                return True
            if c == WHITE and dfs(m):
                return True
        color[n] = BLACK
        return False

    for n in sorted(nodes):
        if color.get(n, WHITE) == WHITE and dfs(n):
            return True
    return False


def build_report(pyproject_text: str, *, imported_modules=None, latest_versions=None,
                 edges=None, mapping=None) -> dict:
    """전체 의존성 감사 리포트(결정적 집계)."""
    scan = scan_dependencies(pyproject_text)
    findings = detect_duplicates(pyproject_text)
    if imported_modules is not None:
        findings += detect_unused(pyproject_text, imported_modules, mapping=mapping)
    if latest_versions is not None:
        findings += detect_outdated(pyproject_text, latest_versions)
    findings.sort(key=lambda f: (f["code"], f["package"]))
    graph = dependency_graph(edges) if edges is not None else None
    by_code: dict = {}
    for f in findings:
        by_code[f["code"]] = by_code.get(f["code"], 0) + 1
    return {"scan": scan, "findings": findings, "finding_count": len(findings),
            "by_code": dict(sorted(by_code.items())), "graph": graph,
            "ok": all(f["severity"] != "CRITICAL" for f in findings)}
