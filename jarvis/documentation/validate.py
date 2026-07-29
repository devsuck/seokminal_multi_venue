"""문서 검증 (P16) — 마크다운 유효성·링크 무결성·다이어그램·완전성·API 커버리지. **읽기 전용·결정적.**

문서 파일을 파싱해 구조·내부 링크·mermaid 다이어그램·필수 문서 존재·API 커버리지를 검증한다. 파일을 수정하지 않는다
(완전 additive). 기존 코드/원장/문서를 변경하지 않는다.
"""
from __future__ import annotations

import os
import re

from jarvis.documentation import manifest as M

_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_HEADING_RE = re.compile(r"^(#{1,6})(\s|$)")


def read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def validate_markdown(text: str) -> dict:
    """단일 마크다운 유효성: H1 존재·헤딩 형식·코드펜스 짝·비어있지 않음."""
    issues: list = []
    if not text.strip():
        issues.append("empty")
    lines = text.splitlines()
    # H1 존재(첫 비어있지 않은 헤딩이 '# ')
    h1 = any(ln.startswith("# ") for ln in lines)
    if not h1:
        issues.append("missing_h1")
    # 헤딩 뒤 공백
    for i, ln in enumerate(lines):
        if ln.startswith("#") and not _HEADING_RE.match(ln):
            issues.append(f"bad_heading:{i + 1}")
    # 코드펜스 짝수
    fences = sum(1 for ln in lines if ln.strip().startswith("```"))
    if fences % 2 != 0:
        issues.append("unbalanced_code_fence")
    return {"ok": not issues, "issues": issues}


def extract_links(text: str) -> list:
    """내부 상대 마크다운 링크(.md) 목록. 외부(http)·앵커(#)·mailto 제외."""
    out = []
    for _label, target in _LINK_RE.findall(text):
        t = target.strip()
        if t.startswith(("http://", "https://", "#", "mailto:")):
            continue
        # 앵커 분리
        t = t.split("#", 1)[0]
        if t:
            out.append(t)
    return out


def validate_links(path: str, text: str) -> dict:
    """내부 링크가 실제 파일로 해석되는지 검증(파일 위치 기준 상대 경로)."""
    base = os.path.dirname(path)
    broken = []
    for link in extract_links(text):
        target = os.path.normpath(os.path.join(base, link))
        if not os.path.exists(target):
            broken.append(link)
    return {"ok": not broken, "broken": sorted(set(broken))}


def count_mermaid_blocks(text: str) -> int:
    """```mermaid 펜스 블록 수."""
    return len(re.findall(r"^```mermaid\s*$", text, flags=re.MULTILINE))


def validate_diagram(text: str) -> dict:
    """다이어그램 문서: 최소 1개의 비어있지 않은 mermaid 블록."""
    blocks = re.findall(r"```mermaid\s*\n(.*?)```", text, flags=re.DOTALL)
    nonempty = [b for b in blocks if b.strip()]
    return {"ok": bool(nonempty), "block_count": len(nonempty)}


def check_completeness(root: str | None = None) -> dict:
    """필수 문서 존재 검증."""
    root = root or M.doc_root()
    missing = [rel for rel in M.REQUIRED_DOCS if not os.path.exists(os.path.join(root, rel))]
    return {"ok": not missing, "missing": sorted(missing),
            "total": len(M.REQUIRED_DOCS), "present": len(M.REQUIRED_DOCS) - len(missing)}


def check_api_coverage(root: str | None = None) -> dict:
    """API 참조가 핵심 문서화 대상 패키지를 모두 다루는지 검증."""
    root = root or M.doc_root()
    ref = os.path.join(root, "api/reference.md")
    if not os.path.exists(ref):
        return {"ok": False, "missing": list(M.CORE_DOCUMENTED_PACKAGES), "reason": "no_reference"}
    text = read(ref)
    missing = [pkg for pkg in M.CORE_DOCUMENTED_PACKAGES
               if f"jarvis.{pkg}" not in text]
    return {"ok": not missing, "missing": sorted(missing),
            "covered": len(M.CORE_DOCUMENTED_PACKAGES) - len(missing)}


def validate_all(root: str | None = None) -> dict:
    """전체 문서 검증 집계(결정적)."""
    root = root or M.doc_root()
    comp = check_completeness(root)
    md_issues: dict = {}
    link_issues: dict = {}
    for rel in M.REQUIRED_DOCS:
        p = os.path.join(root, rel)
        if not os.path.exists(p):
            continue
        text = read(p)
        mv = validate_markdown(text)
        if not mv["ok"]:
            md_issues[rel] = mv["issues"]
        lv = validate_links(p, text)
        if not lv["ok"]:
            link_issues[rel] = lv["broken"]
    diagram_issues = {}
    for rel in M.MERMAID_DOCS:
        p = os.path.join(root, rel)
        if os.path.exists(p):
            dv = validate_diagram(read(p))
            if not dv["ok"]:
                diagram_issues[rel] = "no_mermaid_block"
    api = check_api_coverage(root)
    ok = (comp["ok"] and not md_issues and not link_issues and not diagram_issues and api["ok"])
    return {"ok": ok, "completeness": comp, "markdown_issues": md_issues,
            "link_issues": link_issues, "diagram_issues": diagram_issues, "api_coverage": api}
