"""문서 매니페스트 (P16) — 필수 문서 목록·다이어그램·API 커버리지 정의. **정의·조회 전용.**

P16 문서 트리(top-level `documentation/`)의 정본 구조를 선언한다. 검증기·테스트가 이 목록을 기준으로 완전성·링크·
다이어그램·API 커버리지를 판정한다. 기존 코드/원장/문서를 변경하지 않는다(완전 additive, 기존 docs/ 와 별도 네임스페이스).
"""
from __future__ import annotations

import os


def repo_root() -> str:
    # jarvis/documentation/manifest.py → repo root
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def doc_root() -> str:
    return os.path.join(repo_root(), "documentation")


# ── 필수 문서(문서 루트 상대 경로) ──
ROOT_DOCS = ("README.md", "CHANGELOG.md", "INDEX.md")

ARCHITECTURE_DOCS = (
    "architecture/overview.md",
    "architecture/layers.md",
    "architecture/ownership-boundaries.md",
    "architecture/read-only-boundaries.md",
    "architecture/ledger-ownership-map.md",
    "architecture/data-flow.md",
    "architecture/dependency-map.md",
)

ADR_DOCS = (
    "adr/README.md",
    "adr/0001-append-only-ledgers.md",
    "adr/0002-hash-chain-integrity.md",
    "adr/0003-research-only-architecture.md",
    "adr/0004-no-live-execution.md",
    "adr/0005-namespace-strategy.md",
    "adr/0006-replay-system.md",
    "adr/0007-knowledge-graph.md",
    "adr/0008-automation-pipeline.md",
    "adr/0009-security-architecture.md",
    "adr/0010-decision-intelligence.md",
    "adr/0011-simulation-environment.md",
)

API_DOCS = (
    "api/overview.md",
    "api/reference.md",     # 자동 생성
    "api/cli.md",
    "api/configuration.md",
)

DIAGRAM_DOCS = (
    "diagrams/system-architecture.md",
    "diagrams/package-and-layers.md",
    "diagrams/pipelines.md",
    "diagrams/data-and-ledgers.md",
    "diagrams/security-and-recovery.md",
    "diagrams/sequences.md",
)

DEVELOPER_GUIDE_DOCS = (
    "developer_guide/getting-started.md",
    "developer_guide/repository-structure.md",
    "developer_guide/coding-standards.md",
    "developer_guide/testing-guide.md",
    "developer_guide/replay-guide.md",
    "developer_guide/ledger-guide.md",
    "developer_guide/extension-guide.md",
    "developer_guide/contribution-guide.md",
)

OPERATIONS_DOCS = (
    "operations/installation.md",
    "operations/configuration.md",
    "operations/running-tests.md",
    "operations/running-replay.md",
    "operations/running-benchmarks.md",
    "operations/generating-reports.md",
    "operations/validation-workflow.md",
    "operations/troubleshooting.md",
)

USER_GUIDE_DOCS = (
    "user_guide/research-workflow.md",
    "user_guide/strategy-lifecycle.md",
    "user_guide/simulation-workflow.md",
    "user_guide/decision-workflow.md",
    "user_guide/knowledge-graph.md",
    "user_guide/automation.md",
    "user_guide/report-generation.md",
)

REQUIRED_DOCS = (ROOT_DOCS + ARCHITECTURE_DOCS + ADR_DOCS + API_DOCS + DIAGRAM_DOCS
                 + DEVELOPER_GUIDE_DOCS + OPERATIONS_DOCS + USER_GUIDE_DOCS)

# 다이어그램(최소 1개 mermaid 블록 필수)
MERMAID_DOCS = DIAGRAM_DOCS

# API 참조가 반드시 다뤄야 하는 P14/P15 신규 패키지(핵심 커버리지 게이트)
CORE_DOCUMENTED_PACKAGES = (
    # P14 Production Hardening
    "benchmark", "cache", "concurrency", "resilience", "profiling", "diagnostics",
    # P15 Security & Compliance
    "security", "compliance", "integrity", "sbom", "dependency", "license", "threat_model",
    # P13 Research OS
    "autonomous_research_os",
)


def discover_packages() -> list:
    """jarvis 하위의 공개 서브패키지(__init__.py 보유) 목록(정렬, 결정적)."""
    jarvis_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pkgs = []
    for name in sorted(os.listdir(jarvis_dir)):
        d = os.path.join(jarvis_dir, name)
        if (os.path.isdir(d) and os.path.exists(os.path.join(d, "__init__.py"))
                and not name.startswith("_") and name != "tests"):
            pkgs.append(name)
    return pkgs
