"""API 문서 자동 생성 (P16) — 공개 모듈·클래스·함수·CLI 인트로스펙션. **읽기 전용·결정적.**

jarvis 하위 패키지를 정적 인트로스펙션(importlib + inspect)하여 공개 심볼과 docstring 요약을 결정적 마크다운으로
생성한다. 코드를 실행하지 않고 임포트·조회만 한다. 기존 코드/원장을 변경하지 않는다(완전 additive).
"""
from __future__ import annotations

import importlib
import inspect
import os

from jarvis.documentation import manifest as M


def _summary(obj) -> str:
    doc = inspect.getdoc(obj) or ""
    first = doc.strip().splitlines()[0] if doc.strip() else ""
    return first.strip()


def introspect_package(name: str) -> dict:
    """단일 패키지 인트로스펙션 → {module, doc, functions[], classes[], has_cli}."""
    modname = f"jarvis.{name}"
    try:
        mod = importlib.import_module(modname)
    except Exception as e:  # 임포트 실패 시 요약만
        return {"package": name, "module": modname, "doc": "", "functions": [], "classes": [],
                "has_cli": _has_cli(name), "error": type(e).__name__}
    functions = []
    classes = []
    exported = getattr(mod, "__all__", None)
    for attr in sorted(dir(mod)):
        if attr.startswith("_"):
            continue
        if exported is not None and attr not in exported:
            # __all__ 없는 경우는 전부, 있는 경우는 노출 심볼만
            pass
        obj = getattr(mod, attr)
        if inspect.isfunction(obj):
            functions.append({"name": attr, "summary": _summary(obj)})
        elif inspect.isclass(obj):
            methods = [m for m in sorted(dir(obj))
                       if not m.startswith("_") and callable(getattr(obj, m, None))]
            classes.append({"name": attr, "summary": _summary(obj), "methods": methods})
    return {"package": name, "module": modname, "doc": _summary(mod),
            "functions": functions, "classes": classes, "has_cli": _has_cli(name)}


def _has_cli(name: str) -> bool:
    jarvis_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.exists(os.path.join(jarvis_dir, name, "__main__.py"))


def generate_reference(packages: list | None = None) -> str:
    """전체 패키지 API 참조 마크다운(결정적, 패키지명 정렬)."""
    pkgs = sorted(packages if packages is not None else M.discover_packages())
    lines = [
        "# API Reference",
        "",
        "> 자동 생성(`python -m jarvis.documentation gen`) — 공개 모듈·클래스·함수·CLI 인트로스펙션.",
        "> 관찰·분석·기록 전용. 실행·거래·배포 API 없음.",
        "",
        f"Total packages: **{len(pkgs)}**",
        "",
    ]
    for name in pkgs:
        info = introspect_package(name)
        lines.append(f"## jarvis.{name}")
        lines.append("")
        if info["doc"]:
            lines.append(f"{info['doc']}")
            lines.append("")
        cli = " · CLI: `python -m jarvis.%s`" % name if info["has_cli"] else ""
        lines.append(f"- module: `{info['module']}`{cli}")
        if info["classes"]:
            lines.append("- classes: " + ", ".join(f"`{c['name']}`" for c in info["classes"]))
        if info["functions"]:
            lines.append("- functions: " + ", ".join(f"`{fn['name']}`" for fn in info["functions"]))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_reference(path: str | None = None, packages: list | None = None) -> str:
    """API 참조를 documentation/api/reference.md 에 기록. 반환: 경로."""
    path = path or os.path.join(M.doc_root(), "api", "reference.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(generate_reference(packages))
    return path


def cli_inventory() -> list:
    """CLI(`__main__.py`) 보유 패키지 목록(정렬)."""
    return sorted(p for p in M.discover_packages() if _has_cli(p))
