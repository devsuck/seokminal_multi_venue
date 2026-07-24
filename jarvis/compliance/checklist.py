"""컴플라이언스 체크리스트 (P15) — 보안·저장소·릴리스·재현성. **평가·보고 전용·결정적.**

증거(evidence) 딕셔너리에 대해 결정적 체크 항목을 평가한다. 자동 승인·게이트 통과를 강제하지 않는다 — 결과만 보고한다.
기존 모듈/원장을 변경하지 않는다(완전 additive).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class CheckItem:
    id: str
    description: str
    passed: bool
    required: bool

    def to_dict(self) -> dict:
        return asdict(self)


def _item(cid, desc, passed, required=True) -> CheckItem:
    return CheckItem(id=cid, description=desc, passed=bool(passed), required=required)


def security_checklist(ev: dict) -> list:
    """보안 체크리스트."""
    return [
        _item("SEC-1", "no hardcoded secrets", ev.get("secret_findings", 1) == 0),
        _item("SEC-2", "no critical static findings", ev.get("static_critical", 1) == 0),
        _item("SEC-3", "no forbidden execution capability", ev.get("execution_capability", True) is False),
        _item("SEC-4", "live_execution disabled by default", ev.get("live_execution_enabled", True) is False),
        _item("SEC-5", "dependency audit clean", ev.get("dependency_ok", False) is True),
        _item("SEC-6", "SBOM generated", ev.get("sbom_present", False) is True, required=False),
    ]


def repository_checklist(ev: dict) -> list:
    """저장소 체크리스트."""
    return [
        _item("REPO-1", "tests present", ev.get("test_count", 0) > 0),
        _item("REPO-2", "full regression green", ev.get("regression_pass", False) is True),
        _item("REPO-3", "additive only (no modified files)", ev.get("modified_files", 1) == 0),
        _item("REPO-4", "license inventory available", ev.get("license_inventory", False) is True,
              required=False),
        _item("REPO-5", "pyproject present", ev.get("pyproject_present", False) is True),
    ]


def release_checklist(ev: dict) -> list:
    """릴리스 체크리스트."""
    return [
        _item("REL-1", "version set", bool(ev.get("version"))),
        _item("REL-2", "ledger integrity verified", ev.get("ledger_ok", False) is True),
        _item("REL-3", "artifacts validated", ev.get("artifacts_ok", False) is True),
        _item("REL-4", "no open critical findings", ev.get("open_critical", 1) == 0),
        _item("REL-5", "changelog/commit recorded", ev.get("commit_recorded", False) is True,
              required=False),
    ]


def reproducibility_checklist(ev: dict) -> list:
    """재현성 체크리스트."""
    return [
        _item("REPRO-1", "deterministic replay", ev.get("replay_deterministic", False) is True),
        _item("REPRO-2", "benchmark reproducible", ev.get("benchmark_reproducible", False) is True),
        _item("REPRO-3", "hash-chained ledgers", ev.get("hash_chained", False) is True),
        _item("REPRO-4", "no wall-clock in identifiers", ev.get("no_clock_ids", True) is True,
              required=False),
    ]


_CHECKLISTS = {
    "security": security_checklist,
    "repository": repository_checklist,
    "release": release_checklist,
    "reproducibility": reproducibility_checklist,
}


def run_checklist(name: str, ev: dict) -> dict:
    """단일 체크리스트 실행 → 결정적 결과."""
    items = [i.to_dict() for i in _CHECKLISTS[name](ev)]
    required_failed = [i for i in items if i["required"] and not i["passed"]]
    passed = sum(1 for i in items if i["passed"])
    return {"name": name, "items": items, "total": len(items), "passed": passed,
            "required_failed": [i["id"] for i in required_failed],
            "compliant": not required_failed,
            "pass_rate": round(passed / len(items), 6) if items else 1.0}


def run_compliance(ev: dict) -> dict:
    """전체 컴플라이언스 실행(4개 체크리스트) → 결정적 집계."""
    results = {name: run_checklist(name, ev) for name in sorted(_CHECKLISTS)}
    compliant = all(r["compliant"] for r in results.values())
    total = sum(r["total"] for r in results.values())
    passed = sum(r["passed"] for r in results.values())
    return {"compliant": compliant, "checklists": results, "total_checks": total,
            "total_passed": passed,
            "pass_rate": round(passed / total, 6) if total else 1.0,
            "failed_checklists": sorted(n for n, r in results.items() if not r["compliant"])}
