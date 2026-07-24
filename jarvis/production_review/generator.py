"""Production Review 문서 생성기 (P39) — 8개 운영 문서 결정적 생성. **배포 없음, 문서·평가만.**

production_review/ 하위 8개 마크다운을 P35 레지스트리·P39 상수로부터 결정적으로 생성한다. 상위 계층은 READ ONLY.
"""
from __future__ import annotations

import os

from jarvis.production_review import models as M
from jarvis.system_integration.models import LAYER_REGISTRY

_JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_JARVIS_ROOT)


def _bullets(items) -> str:
    return "\n".join(f"- {i}" for i in items)


def _deployment_checklist() -> str:
    return ("# Deployment Checklist\n\n"
            "**No production deployment performed. Readiness assessment only.**\n\n"
            + _bullets(f"[ ] {c}" for c in M.DEPLOYMENT_CHECKLIST) + "\n")


def _environment_requirements() -> str:
    return "# Environment Requirements\n\n" + _bullets(M.ENVIRONMENT_REQUIREMENTS) + "\n"


def _configuration_review() -> str:
    return ("# Configuration Review\n\n"
            "- Ledger root resolved via `jarvis.config.state_path` (shared `_state/`).\n"
            "- No secrets, credentials, tokens, or broker endpoints required or stored.\n"
            "- All layers deterministic given identical ledger state (no wall-clock in IDs).\n"
            f"- {len(LAYER_REGISTRY)} research layers + finalization layers, each self-contained.\n")


def _recovery_procedures() -> str:
    return ("# Recovery Procedures\n\n"
            "1. Detect: run each layer's `verify_chain()` — reports tamper / broken chain / dup.\n"
            "2. Isolate: append-only ledgers mean the last valid record is always recoverable.\n"
            "3. Restore: replay from the last intact `record_hash`; no in-place mutation needed.\n"
            "4. Record: P24 research_reliability captures incidents, recovery plans, postmortems\n"
            "   (records only — recovery is research-process recovery, never live-system).\n")


def _backup_strategy() -> str:
    return ("# Backup Strategy\n\n"
            "- Ledgers are append-only JSONL files under `_state/` — copy-on-write friendly.\n"
            "- SHA256 hash-chaining makes any post-backup tampering detectable on restore.\n"
            "- Deterministic replay allows verification that a restored backup is intact.\n"
            "- Recommended: periodic snapshot of `_state/` + verify_chain before and after.\n")


def _monitoring_checklist() -> str:
    return ("# Monitoring Checklist\n\n"
            "- [ ] P23 research_monitoring health checks green\n"
            "- [ ] P23 anomaly ledger reviewed (detection only)\n"
            "- [ ] P24 reliability incidents triaged (records only)\n"
            "- [ ] P30 meta metrics within expected ranges (observations only)\n"
            "- [ ] P34 dashboard aggregations reviewed (no decision authority)\n"
            "- [ ] P38 security audit shows 0 failed findings\n")


def _failure_scenarios() -> str:
    return "# Failure Scenarios\n\n" + _bullets(M.FAILURE_SCENARIOS) + "\n"


def _operational_procedures() -> str:
    return ("# Operational Procedures\n\n"
            "- **Run validation:** `python -m jarvis.system_integration validate`\n"
            "- **Run security audit:** `python -m jarvis.security_audit audit`\n"
            "- **Assess readiness:** `python -m jarvis.production_review assess`\n"
            "- **Regenerate docs:** `python -m jarvis.architecture_docs generate`\n"
            "- Every layer CLI is read-only; none can execute, trade, deploy, or allocate.\n"
            "- **Escalation:** all layers are observation/record-only; no automated action fires.\n")


def generate_docs() -> dict:
    """8개 운영 문서 결정적 생성 → {filename: content}. **파일 쓰기 없음(순수).**"""
    return {
        "01_deployment_checklist.md": _deployment_checklist(),
        "02_environment_requirements.md": _environment_requirements(),
        "03_configuration_review.md": _configuration_review(),
        "04_recovery_procedures.md": _recovery_procedures(),
        "05_backup_strategy.md": _backup_strategy(),
        "06_monitoring_checklist.md": _monitoring_checklist(),
        "07_failure_scenarios.md": _failure_scenarios(),
        "08_operational_procedures.md": _operational_procedures(),
    }


def docs_dir() -> str:
    return os.path.join(_REPO_ROOT, "production_review")


def write_docs() -> list:
    d = docs_dir()
    os.makedirs(d, exist_ok=True)
    written = []
    for name, content in generate_docs().items():
        path = os.path.join(d, name)
        with open(path, "w") as f:
            f.write(content)
        written.append(path)
    return written
