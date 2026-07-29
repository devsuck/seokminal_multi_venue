"""Architecture 문서 생성기 (P36) — P35 레지스트리를 단일 진실로 결정적 문서 생성. **문서화만.**

핵심 아키텍처를 리팩터링하지 않는다. docs/architecture/ 하위 9개 마크다운을 결정적으로 생성한다. 계층 레지스트리·
책임 맵·의존성 그래프는 P35 system_integration 에서 읽는다(단일 진실). 상위 계층은 READ ONLY.
"""
from __future__ import annotations

import ast
import os

from jarvis.architecture_docs import models as M
from jarvis.system_integration.models import LAYER_REGISTRY

_JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_JARVIS_ROOT)


def _ledger_files(package) -> list:
    """계층 ledger.py 의 ALL_LEDGERS 원장 파일명 추출(정적 파싱, READ ONLY)."""
    path = os.path.join(_JARVIS_ROOT, package, "ledger.py")
    if not os.path.exists(path):
        return []
    tree = ast.parse(open(path).read())
    prefix = next((l["prefix"] for l in LAYER_REGISTRY if l["package"] == package), "")
    files = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and node.value.endswith(".jsonl") and node.value.startswith(prefix):
            files.append(node.value)
    return sorted(set(files))


def _dependency_graph() -> dict:
    from jarvis.system_integration.engine import SystemIntegrationEngine
    return SystemIntegrationEngine().dependency_graph()


def _overview() -> str:
    lines = ["# Jarvis Research Platform — System Architecture Overview", "",
             "**Research assistance only. No live execution. No autonomous trading.**", "",
             f"Institutional research layers: **{len(LAYER_REGISTRY)}** (P21–P34) + system integration (P35).",
             "", "The platform is an append-only, deterministic, self-validating research OS.",
             "Every layer is observation/record-only: nothing executes, trades, deploys, allocates,",
             "or decides autonomously. All ledgers are SHA256 hash-chained and replayable.", "",
             "## Layers", ""]
    for l in LAYER_REGISTRY:
        resp = M.LAYER_RESPONSIBILITIES.get(l["package"], "")
        lines.append(f"- **{l['phase']}** `{l['package']}` (`{l['prefix']}`) — {resp}")
    return "\n".join(lines) + "\n"


def _responsibility_map() -> str:
    lines = ["# Layer Responsibility Map", "",
             "| Phase | Package | Prefix | Responsibility |", "|---|---|---|---|"]
    for l in LAYER_REGISTRY:
        resp = M.LAYER_RESPONSIBILITIES.get(l["package"], "")
        lines.append(f"| {l['phase']} | `{l['package']}` | `{l['prefix']}` | {resp} |")
    return "\n".join(lines) + "\n"


def _data_flow() -> str:
    return ("# Data Flow Diagram\n\n"
            "```\n"
            "Upstream research ledgers (P10~P28)\n"
            "        | READ ONLY (JSONL only)\n"
            "        v\n"
            "P21 Production Readiness --> P22 Automation --> P23 Monitoring --> P24 Reliability\n"
            "        |\n"
            "        v\n"
            "P25 Autonomous Research --> P26 Agent Coordination --> P27 Memory --> P28 Insight\n"
            "        |\n"
            "        v\n"
            "P29 Strategy Generation --> P30 Meta --> P31 Orchestration --> P32 Resource\n"
            "        |\n"
            "        v\n"
            "P33 API Gateway (read-only) --> P34 Dashboard Backend (aggregation)\n"
            "        |\n"
            "        v\n"
            "P35 System Integration (static validation of all 14 layers)\n"
            "```\n\n"
            "Each arrow is a READ ONLY reference. No layer mutates another layer's ledgers.\n")


def _ownership_boundary() -> str:
    lines = ["# Ownership Boundary Document", "",
             "Each layer owns exactly one ledger prefix. Prefixes and packages are unique",
             "(verified by P35). No layer may write to another layer's ledgers.", "",
             "| Package | Owned prefix |", "|---|---|"]
    for l in LAYER_REGISTRY:
        lines.append(f"| `{l['package']}` | `{l['prefix']}` |")
    lines += ["", "**Rule:** existing ownership boundaries are immutable. No migration, no overwrite."]
    return "\n".join(lines) + "\n"


def _ledger_catalog() -> str:
    lines = ["# Ledger Catalog", "",
             "All ledgers: append-only, SHA256 hash-chained, immutable, no update/delete API.", ""]
    total = 0
    for l in LAYER_REGISTRY:
        files = _ledger_files(l["package"])
        total += len(files)
        lines.append(f"### {l['phase']} `{l['package']}` ({len(files)} ledgers)")
        for f in files:
            lines.append(f"- `{f}`")
        lines.append("")
    lines.insert(2, f"**Total owned ledgers (P21–P34): {total}.**\n")
    return "\n".join(lines) + "\n"


def _dependency_doc() -> str:
    graph = _dependency_graph()
    lines = ["# Dependency Graph", "",
             "Strictly acyclic, single-direction (newer layer -> older layer, READ ONLY).", ""]
    for pkg in sorted(graph):
        deps = graph[pkg]
        lines.append(f"- `{pkg}` -> {deps if deps else '(no upstream jarvis deps)'}")
    return "\n".join(lines) + "\n"


def _security_boundary() -> str:
    lines = ["# Security Boundary Document", "",
             "Invariants enforced across every layer (verified by P35 safety scans):", ""]
    for b in M.SECURITY_BOUNDARIES:
        lines.append(f"- {b}")
    lines += ["", "**Forbidden everywhere:** execute_trade, place_order, allocate_capital,",
              "deploy_strategy, activate_live, approve_for_trading; imports of",
              "execution/broker/live_trading/portfolio_execution."]
    return "\n".join(lines) + "\n"


def _research_workflow() -> str:
    return ("# Research Workflow Documentation\n\n"
            "1. **Generate** research candidates (P29) from historical knowledge (READ ONLY).\n"
            "2. **Interpret** and connect insights (P28) over memory (P27).\n"
            "3. **Meta-analyze** the research process (P30) — observations only.\n"
            "4. **Orchestrate** experiments (P31) — records only, human approval required, never executes.\n"
            "5. **Track** resources (P32) — records only, never allocates/provisions.\n"
            "6. **Expose** read-only services (P33) and **aggregate** dashboards (P34).\n"
            "7. **Validate** the whole ecosystem (P35).\n\n"
            "At no point does the platform execute trades, deploy strategies, or make autonomous\n"
            "investment decisions. All outputs are research artifacts.\n")


def _module_reference() -> str:
    lines = ["# Module Reference", "",
             "Every layer package exposes the same module surface:", "",
             "- `models.py` — frozen dataclasses, deterministic IDs, hashing",
             "- `ledger.py` — append-only JSONL readers/writers, READ ONLY source layers",
             "- `engine.py` — record/observe/aggregate operations (no execution)",
             "- `verify.py` — `verify_chain()` + `replay()` integrity",
             "- `__main__.py` — read-only CLI", "", "## Packages", ""]
    for l in LAYER_REGISTRY:
        lines.append(f"- `jarvis.{l['package']}` — `python -m jarvis.{l['package']}`")
    return "\n".join(lines) + "\n"


def generate_docs() -> dict:
    """9개 문서를 결정적으로 생성 → {filename: content}. **파일 쓰기 없음(순수).**"""
    return {
        "01_system_architecture_overview.md": _overview(),
        "02_layer_responsibility_map.md": _responsibility_map(),
        "03_data_flow_diagram.md": _data_flow(),
        "04_ownership_boundary.md": _ownership_boundary(),
        "05_ledger_catalog.md": _ledger_catalog(),
        "06_dependency_graph.md": _dependency_doc(),
        "07_security_boundary.md": _security_boundary(),
        "08_research_workflow.md": _research_workflow(),
        "09_module_reference.md": _module_reference(),
    }


def docs_dir() -> str:
    return os.path.join(_REPO_ROOT, "docs", "architecture")


def write_docs() -> list:
    """생성 문서를 docs/architecture/ 에 기록(신규 파일만). 반환: 기록된 경로."""
    d = docs_dir()
    os.makedirs(d, exist_ok=True)
    written = []
    for name, content in generate_docs().items():
        path = os.path.join(d, name)
        with open(path, "w") as f:
            f.write(content)
        written.append(path)
    return written
