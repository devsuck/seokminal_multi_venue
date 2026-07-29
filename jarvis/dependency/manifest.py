"""의존성 매니페스트 파서 (P15) — pyproject.toml 의존성 파싱. **읽기 전용·결정적.**

정규식 기반 경량 파서로 PEP 508 유사 요구사항을 (name, operator, version, extras) 로 분해한다. 외부 네트워크·설치·
실행을 하지 않는다. 기존 모듈/원장을 변경하지 않는다(완전 additive).
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

_OPERATORS = (">=", "<=", "==", "!=", "~=", ">", "<", "===")
_REQ_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9._-]+)"
    r"(?:\[(?P<extras>[A-Za-z0-9,._-]+)\])?"
    r"\s*(?P<op>>=|<=|==|!=|~=|===|>|<)?\s*"
    r"(?P<version>[A-Za-z0-9._*+!-]+)?\s*$")


@dataclass(frozen=True)
class Requirement:
    name: str
    canonical: str            # 정규화 이름(소문자, - 통일)
    operator: str
    version: str
    extras: tuple

    def to_dict(self) -> dict:
        return {**asdict(self), "extras": list(self.extras)}


def canonicalize(name: str) -> str:
    """PEP 503 정규화: 소문자 + [-_.]+ → '-'."""
    return re.sub(r"[-_.]+", "-", (name or "").strip().lower())


def parse_requirement(spec: str) -> Requirement | None:
    """단일 요구사항 문자열 파싱. 파싱 불가 시 None."""
    if not spec or spec.strip().startswith("#"):
        return None
    m = _REQ_RE.match(spec.strip())
    if not m:
        return None
    name = m.group("name")
    extras = tuple(sorted(e.strip() for e in (m.group("extras") or "").split(",") if e.strip()))
    return Requirement(name=name, canonical=canonicalize(name), operator=m.group("op") or "",
                       version=m.group("version") or "", extras=extras)


def _extract_array(text: str, key: str) -> list[str]:
    """pyproject 의 `key = [ ... ]` 배열에서 문자열 항목 추출(경량, TOML 서브셋)."""
    # key 위치 탐색
    idx = text.find(key)
    if idx < 0:
        return []
    start = text.find("[", idx)
    if start < 0:
        return []
    depth = 0
    end = start
    for i in range(start, len(text)):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                end = i
                break
    body = text[start + 1:end]
    return re.findall(r'"([^"]*)"', body) + re.findall(r"'([^']*)'", body)


def parse_pyproject(text: str) -> dict:
    """pyproject.toml 텍스트에서 의존성 파싱 → {dependencies, optional{extra:[...]}}. 결정적."""
    deps = [r for r in (parse_requirement(s) for s in _extract_array(text, "dependencies"))
            if r is not None]
    optional: dict = {}
    # [project.optional-dependencies] 블록
    opt_idx = text.find("optional-dependencies")
    if opt_idx >= 0:
        block = text[opt_idx:]
        # 다음 섹션 헤더 이전까지
        nxt = re.search(r"\n\[", block)
        if nxt:
            block = block[:nxt.start()]
        for key in re.findall(r"\n?\s*([A-Za-z0-9_-]+)\s*=\s*\[", block):
            items = _extract_array(block, key)
            reqs = [r for r in (parse_requirement(s) for s in items) if r is not None]
            if reqs:
                optional[key] = reqs
    return {"dependencies": deps, "optional": optional}
