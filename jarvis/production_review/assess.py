"""Production Readiness 평가 (P39) — 재현성·복구성·관측성·유지보수성 정적 평가. **평가만, 배포 없음.**

프로덕션 배포를 하지 않는다. 준비성만 평가한다(파일 읽기·정적 검사·기존 계층 재현 호출). READ ONLY.
"""
from __future__ import annotations

import os

from jarvis.production_review import generator, models as M
from jarvis.system_integration.models import LAYER_REGISTRY

_JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _has_module(package, module) -> bool:
    return os.path.exists(os.path.join(_JARVIS_ROOT, package, module))


def _has_symbol(package, module, symbol) -> bool:
    path = os.path.join(_JARVIS_ROOT, package, module)
    return os.path.exists(path) and symbol in open(path).read()


def assess_reproducibility() -> dict:
    """재현성: 모든 계층이 verify.py 에 replay() 노출(결정적 재현 보장)."""
    missing = [l["package"] for l in LAYER_REGISTRY
               if not _has_symbol(l["package"], "verify.py", "def replay(")]
    return {"dimension": "REPRODUCIBILITY", "ok": not missing, "missing": missing}


def assess_recoverability() -> dict:
    """복구성: 신뢰성 계층(P24) 존재 + 복구 절차 문서 + verify_chain 노출."""
    reliability = "research_reliability" in [l["package"] for l in LAYER_REGISTRY]
    recovery_doc = "04_recovery_procedures.md" in generator.generate_docs()
    verify_all = all(_has_symbol(l["package"], "verify.py", "def verify_chain(")
                     for l in LAYER_REGISTRY)
    ok = reliability and recovery_doc and verify_all
    return {"dimension": "RECOVERABILITY", "ok": ok, "reliability_layer": reliability,
            "recovery_doc": recovery_doc, "verify_all": verify_all}


def assess_observability() -> dict:
    """관측성: 모니터링(P23)·대시보드(P34)·메타(P30) 계층 존재 + 모니터링 문서."""
    pkgs = {l["package"] for l in LAYER_REGISTRY}
    monitoring = "research_monitoring" in pkgs
    dashboard = "research_dashboard_backend" in pkgs
    meta = "meta_research_intelligence" in pkgs
    doc = "06_monitoring_checklist.md" in generator.generate_docs()
    ok = monitoring and dashboard and meta and doc
    return {"dimension": "OBSERVABILITY", "ok": ok, "monitoring": monitoring,
            "dashboard": dashboard, "meta": meta}


def assess_maintainability() -> dict:
    """유지보수성: 모든 계층이 일관된 모듈 구조(models/ledger/engine/verify/__main__)."""
    required = ("models.py", "ledger.py", "engine.py", "verify.py", "__main__.py")
    incomplete = [l["package"] for l in LAYER_REGISTRY
                  if not all(_has_module(l["package"], m) for m in required)]
    return {"dimension": "MAINTAINABILITY", "ok": not incomplete, "incomplete": incomplete}


def run_readiness_assessment() -> dict:
    """전체 준비성 평가(4차원). **평가만 — 배포 없음.**"""
    checks = [assess_reproducibility(), assess_recoverability(), assess_observability(),
              assess_maintainability()]
    return {"ready": all(c["ok"] for c in checks), "dimensions": checks,
            "deployment_performed": False}


def docs_complete() -> dict:
    """8개 운영 문서 완비·비어있지 않음."""
    docs = generator.generate_docs()
    ok = set(docs) == set(M.PRODUCTION_DOCS) and all(len(c) > 0 for c in docs.values())
    return {"check": "docs_complete", "ok": ok, "count": len(docs)}
