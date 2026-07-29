"""라이선스 감사 (P15) — 인벤토리·호환성·서드파티 고지. **읽기 전용·결정적.**

SPDX 유사 식별자를 카테고리(permissive/weak-copyleft/strong-copyleft/proprietary/unknown)로 분류하고, 프로젝트
라이선스와의 배포 호환성을 결정적 규칙으로 판정한다. 네트워크·실행을 하지 않는다(완전 additive).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

# ── SPDX(유사) → 카테고리 ──
PERMISSIVE = "permissive"
WEAK_COPYLEFT = "weak-copyleft"
STRONG_COPYLEFT = "strong-copyleft"
PROPRIETARY = "proprietary"
UNKNOWN = "unknown"

_LICENSE_CATEGORY = {
    "MIT": PERMISSIVE, "BSD-2-CLAUSE": PERMISSIVE, "BSD-3-CLAUSE": PERMISSIVE, "BSD": PERMISSIVE,
    "APACHE-2.0": PERMISSIVE, "APACHE": PERMISSIVE, "ISC": PERMISSIVE, "PSF": PERMISSIVE,
    "PYTHON-2.0": PERMISSIVE, "ZLIB": PERMISSIVE, "UNLICENSE": PERMISSIVE, "0BSD": PERMISSIVE,
    "MPL-2.0": WEAK_COPYLEFT, "LGPL-2.1": WEAK_COPYLEFT, "LGPL-3.0": WEAK_COPYLEFT,
    "LGPL": WEAK_COPYLEFT, "EPL-2.0": WEAK_COPYLEFT, "CDDL-1.0": WEAK_COPYLEFT,
    "GPL-2.0": STRONG_COPYLEFT, "GPL-3.0": STRONG_COPYLEFT, "GPL": STRONG_COPYLEFT,
    "AGPL-3.0": STRONG_COPYLEFT, "AGPL": STRONG_COPYLEFT,
    "PROPRIETARY": PROPRIETARY, "COMMERCIAL": PROPRIETARY,
}


def normalize_license(lic: str) -> str:
    return (lic or "").strip().upper().replace(" ", "-")


def categorize(lic: str) -> str:
    """라이선스 → 카테고리(미상 시 unknown)."""
    return _LICENSE_CATEGORY.get(normalize_license(lic), UNKNOWN)


@dataclass(frozen=True)
class LicenseEntry:
    package: str
    version: str
    license: str
    category: str

    def to_dict(self) -> dict:
        return asdict(self)


def build_inventory(packages: list) -> dict:
    """라이선스 인벤토리. packages: [{name, version, license}, ...] → 정렬·카테고리 집계."""
    entries = []
    for p in packages:
        entries.append(LicenseEntry(package=p.get("name", ""), version=p.get("version", ""),
                                    license=p.get("license", ""),
                                    category=categorize(p.get("license", ""))).to_dict())
    entries.sort(key=lambda e: e["package"])
    by_cat: dict = {}
    for e in entries:
        by_cat[e["category"]] = by_cat.get(e["category"], 0) + 1
    return {"count": len(entries), "entries": entries, "by_category": dict(sorted(by_cat.items())),
            "unknown": sorted(e["package"] for e in entries if e["category"] == UNKNOWN)}


# ── 배포 호환성 규칙(결정적): (project_cat, dep_cat) → 판정 ──
_COMPATIBLE = "COMPATIBLE"
_REVIEW = "REVIEW"
_CONFLICT = "CONFLICT"


def _verdict(project_cat: str, dep_cat: str) -> str:
    if dep_cat == PERMISSIVE:
        return _COMPATIBLE
    if dep_cat == UNKNOWN:
        return _REVIEW
    if dep_cat == WEAK_COPYLEFT:
        return _REVIEW if project_cat == PROPRIETARY else _COMPATIBLE
    if dep_cat == STRONG_COPYLEFT:
        return _COMPATIBLE if project_cat == STRONG_COPYLEFT else _CONFLICT
    if dep_cat == PROPRIETARY:
        return _COMPATIBLE if project_cat == PROPRIETARY else _REVIEW
    return _REVIEW


def compatibility_report(project_license: str, packages: list) -> dict:
    """프로젝트 라이선스 대비 각 의존성의 배포 호환성 판정(결정적)."""
    pcat = categorize(project_license)
    rows = []
    for p in sorted(packages, key=lambda x: x.get("name", "")):
        dcat = categorize(p.get("license", ""))
        rows.append({"package": p.get("name", ""), "license": p.get("license", ""),
                     "category": dcat, "verdict": _verdict(pcat, dcat)})
    conflicts = [r["package"] for r in rows if r["verdict"] == _CONFLICT]
    reviews = [r["package"] for r in rows if r["verdict"] == _REVIEW]
    return {"project_license": project_license, "project_category": pcat, "rows": rows,
            "conflicts": sorted(conflicts), "reviews": sorted(reviews),
            "ok": not conflicts}


def third_party_notice(packages: list) -> str:
    """서드파티 고지문 생성(결정적, 정렬)."""
    lines = ["THIRD-PARTY SOFTWARE NOTICES", "=" * 32, ""]
    for p in sorted(packages, key=lambda x: x.get("name", "")):
        lines.append(f"- {p.get('name', '')} {p.get('version', '')} "
                     f"— {p.get('license', 'UNKNOWN')}")
    lines.append("")
    lines.append(f"Total: {len(packages)} components")
    return "\n".join(lines)
