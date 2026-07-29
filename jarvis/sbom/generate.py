"""SBOM 생성 (P15) — 소프트웨어 부품 목록. **읽기 전용·결정적.**

package·version·license·hash·source·dependency graph 를 포함한 결정적 SBOM(CycloneDX 유사 경량 구조)을 생성한다.
컴포넌트 해시는 (name,version,license,source) 로 결정적으로 계산하며, 직렬 번호는 전체 내용 지문이다. 네트워크·실행 없음.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

SBOM_FORMAT = "jarvis-sbom"
SBOM_SPEC_VERSION = "1.0"


def _sha(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()


def component_hash(name: str, version: str, license: str, source: str) -> str:
    return _sha({"name": name, "version": version, "license": license, "source": source})


@dataclass(frozen=True)
class Component:
    name: str
    version: str
    license: str
    source: str
    hash: str
    depends_on: tuple

    def to_dict(self) -> dict:
        return {**asdict(self), "depends_on": list(self.depends_on)}


def make_component(name: str, version: str = "", license: str = "", source: str = "",
                   depends_on=None) -> Component:
    deps = tuple(sorted(depends_on or ()))
    return Component(name=name, version=version, license=license, source=source,
                     hash=component_hash(name, version, license, source), depends_on=deps)


def generate_sbom(components: list, *, project: str = "jarvis", project_version: str = "",
                  generated_at: str = "") -> dict:
    """컴포넌트 목록 → 결정적 SBOM. components: make_component() 또는 dict."""
    comps = []
    for c in components:
        if isinstance(c, Component):
            comps.append(c.to_dict())
        else:
            comps.append(make_component(
                c.get("name", ""), c.get("version", ""), c.get("license", ""),
                c.get("source", ""), c.get("depends_on")).to_dict())
    comps.sort(key=lambda d: d["name"])
    # 의존성 그래프(name → depends_on)
    graph = {c["name"]: c["depends_on"] for c in comps}
    body = {"format": SBOM_FORMAT, "spec_version": SBOM_SPEC_VERSION, "project": project,
            "project_version": project_version, "components": comps,
            "component_count": len(comps), "dependency_graph": dict(sorted(graph.items()))}
    serial = _sha(body)  # 직렬 번호(내용 지문, 타임스탬프 제외 → 결정적)
    return {**body, "serial_number": serial, "generated_at": generated_at}


def verify_sbom(sbom: dict) -> dict:
    """SBOM 무결성 검증: 각 컴포넌트 해시 재계산 + 직렬 번호 재계산. **읽기 전용.**"""
    issues: list = []
    for c in sbom.get("components", []):
        expect = component_hash(c.get("name", ""), c.get("version", ""), c.get("license", ""),
                                c.get("source", ""))
        if c.get("hash") != expect:
            issues.append({"component": c.get("name"), "issue": "hash_mismatch"})
    body = {k: sbom[k] for k in ("format", "spec_version", "project", "project_version",
                                 "components", "component_count", "dependency_graph")
            if k in sbom}
    serial_ok = _sha(body) == sbom.get("serial_number")
    if not serial_ok:
        issues.append({"component": "*", "issue": "serial_mismatch"})
    return {"ok": not issues, "issues": issues, "verified": len(sbom.get("components", []))}


def sbom_from_dependencies(scan: dict, *, licenses: dict | None = None,
                           versions: dict | None = None, source: str = "pypi",
                           project: str = "jarvis", generated_at: str = "") -> dict:
    """dependency.scan_dependencies 산출 + 라이선스/버전 맵 → SBOM(결정적)."""
    lic = {k.lower(): v for k, v in (licenses or {}).items()}
    ver = {k.lower(): v for k, v in (versions or {}).items()}
    comps = []
    for d in scan.get("dependencies", []):
        name = d.get("canonical", d.get("name", ""))
        comps.append(make_component(name, ver.get(name, d.get("version", "")),
                                    lic.get(name, ""), source))
    return generate_sbom(comps, project=project, generated_at=generated_at)
