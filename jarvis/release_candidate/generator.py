"""Release 산출물 생성기 (P40) — 7개 릴리스 문서 결정적 생성. **실행 없음, 문서만.**

release/ 하위 VERSION·릴리스 노트·아키텍처 요약·기능 인벤토리·테스트 요약·보안 요약·알려진 한계를 결정적으로 생성한다.
상위 계층은 READ ONLY.
"""
from __future__ import annotations

import os

from jarvis.release_candidate import models as M
from jarvis.system_integration.models import LAYER_REGISTRY

_JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_JARVIS_ROOT)

# 파이널라이제이션 계층(P35~P40)
_FINALIZATION = ("system_integration (P35)", "architecture_docs (P36)", "performance (P37)",
                 "security_audit (P38)", "production_review (P39)", "release_candidate (P40)")


def _version() -> str:
    return M.VERSION + "\n"


def _release_notes() -> str:
    lines = [f"# {M.PLATFORM_NAME} — v{M.VERSION} Release Notes", "", "## Status", ""]
    lines += [f"- {s}" for s in M.STATUS_STATEMENTS]
    lines += ["", "## Highlights", "",
              f"- {len(LAYER_REGISTRY)} institutional research layers (P21–P34).",
              "- 6 finalization layers (P35–P40): integration, docs, performance, security, "
              "readiness, release.",
              "- Append-only, SHA256 hash-chained, deterministic, replayable throughout.",
              "- Zero execution / trading / deployment authority by design."]
    return "\n".join(lines) + "\n"


def _architecture_summary() -> str:
    lines = [f"# {M.PLATFORM_NAME} — Architecture Summary (v{M.VERSION})", "",
             "## Research layers (P21–P34)", ""]
    for l in LAYER_REGISTRY:
        lines.append(f"- **{l['phase']}** `{l['package']}` (`{l['prefix']}`)")
    lines += ["", "## Finalization layers (P35–P40)", ""]
    for f in _FINALIZATION:
        lines.append(f"- {f}")
    return "\n".join(lines) + "\n"


def _feature_inventory() -> str:
    lines = [f"# {M.PLATFORM_NAME} — Feature Inventory (v{M.VERSION})", "",
             "Every layer is observation / record / analysis only.", ""]
    from jarvis.architecture_docs.models import LAYER_RESPONSIBILITIES
    for l in LAYER_REGISTRY:
        resp = LAYER_RESPONSIBILITIES.get(l["package"], "")
        lines.append(f"- `{l['package']}`: {resp}")
    lines += ["", "**Not included (by design):** trade execution, order placement, capital",
              "allocation, strategy deployment, live activation, broker connectivity."]
    return "\n".join(lines) + "\n"


def _test_summary() -> str:
    return (f"# {M.PLATFORM_NAME} — Test Summary (v{M.VERSION})\n\n"
            "- Every layer ships unit + integration tests (isolated `_state/`, deterministic).\n"
            "- Coverage: lifecycle transitions, hash-chain verify, tamper detection, replay,\n"
            "  READ ONLY protection, forbidden-import/method scans, CLI, end-to-end.\n"
            "- Full repository regression is run and required green after every phase.\n"
            "- Run: `python -m pytest jarvis -q`\n")


def _security_summary() -> str:
    lines = [f"# {M.PLATFORM_NAME} — Security Summary (v{M.VERSION})", "",
             "Final security audit (P38) covers ledger, architecture, and runtime security", ""]
    lines += [f"- {s}" for s in M.STATUS_STATEMENTS]
    lines += ["", "**Forbidden everywhere:** execute_trade, place_order, allocate_capital,",
              "deploy_strategy, activate_live, approve_for_trading; imports of",
              "execution/broker/live_trading/portfolio_execution. Engines expose none of",
              "execute/trade/deploy/allocate/approve.", "",
              "Run: `python -m jarvis.security_audit audit`"]
    return "\n".join(lines) + "\n"


def _known_limitations() -> str:
    lines = [f"# {M.PLATFORM_NAME} — Known Limitations (v{M.VERSION})", ""]
    lines += [f"- {k}" for k in M.KNOWN_LIMITATIONS]
    return "\n".join(lines) + "\n"


def generate_artifacts() -> dict:
    """7개 릴리스 산출물 결정적 생성 → {name: content}. **파일 쓰기 없음(순수).**"""
    return {
        "VERSION": _version(),
        "RELEASE_NOTES.md": _release_notes(),
        "ARCHITECTURE_SUMMARY.md": _architecture_summary(),
        "FEATURE_INVENTORY.md": _feature_inventory(),
        "TEST_SUMMARY.md": _test_summary(),
        "SECURITY_SUMMARY.md": _security_summary(),
        "KNOWN_LIMITATIONS.md": _known_limitations(),
    }


def release_dir() -> str:
    return os.path.join(_REPO_ROOT, "release")


def write_artifacts() -> list:
    d = release_dir()
    os.makedirs(d, exist_ok=True)
    written = []
    for name, content in generate_artifacts().items():
        path = os.path.join(d, name)
        with open(path, "w") as f:
            f.write(content)
        written.append(path)
    return written
