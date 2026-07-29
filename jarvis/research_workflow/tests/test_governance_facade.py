"""P203 Governance Consolidation 테스트 — 검증 목적별 5도메인 단일 공개 API.

핵심: validate(domain)/validate_all() 하나로 통합 · 5 도메인(architecture/safety/data/research/
operations) · 기존 build_governance + 12 모듈 backward-compat(deprecated 유지, 삭제 아님) ·
meaning==meaning(golden) 보존 · 새 원장 없음.
"""
from __future__ import annotations

from jarvis.research_workflow import characterization as ch
from jarvis.research_workflow import governance as gv
from jarvis.research_workflow import ledger as wl


# ── 5 도메인 단일 API ──
def test_five_domains_validate():
    assert set(gv.DOMAINS) == {"architecture", "safety", "data", "research", "operations"}
    for d in gv.DOMAINS:
        r = gv.validate(d)
        assert r["domain"] == d and isinstance(r["checks"], list) and r["checks"]
        assert r["is_decision"] is False


def test_validate_all_aggregates_and_compliant():
    va = gv.validate_all()
    assert set(va["domains"]) == set(gv.DOMAINS)
    assert va["governance"] == "COMPLIANT" and va["passed"] is True
    assert va["is_decision"] is False


def test_unknown_domain_rejected():
    assert "error" in gv.validate("bogus")


# ── 목적별 분류가 실제로 반영됐는지 ──
def test_safety_domain_aggregates_all_safety_scans():
    safety = gv.validate("safety")
    names = {c["check"] for c in safety["checks"]}
    # 모든 *_safety 계층 + live_execution_disabled 포함
    assert "live_execution_disabled" in names
    assert any(n.startswith("safety::") for n in names)


def test_architecture_domain_has_ledger_invariant():
    arch = gv.validate("architecture")
    names = {c["check"] for c in arch["checks"]}
    assert "ledger_count_3" in names


# ── backward-compat: 기존 공개 함수 그대로 동작(deprecated, 삭제 아님) ──
def test_backward_compat_build_governance():
    g = gv.build_governance()
    assert g["governance"] == "COMPLIANT"
    names = {c["check"] for c in g["checks"]}
    assert names == {"permissions", "audit_trail", "append_only_integrity", "human_checkpoints",
                     "architecture_compliance", "safety_rules"}


def test_backward_compat_old_validation_modules_still_importable():
    # 콘솔/테스트/__init__ 가 의존 — deprecated 지만 살아있어야 함
    from jarvis.research_workflow.system_validation import validate_system
    from jarvis.research_workflow.autonomy_validation import validate_autonomy
    from jarvis.research_workflow.autonomous_validation_v3 import audit_production
    assert validate_system()["validated"] is True
    assert validate_autonomy()["validated"] is True
    assert audit_production()["audited"] is True


# ── meaning == meaning 보존(리팩터링 안전망) ──
def test_meaning_preserved_after_consolidation():
    import json
    import pathlib
    golden = json.loads((pathlib.Path(__file__).resolve().parent / "golden" /
                         "research_meaning.json").read_text(encoding="utf-8"))
    cmp = ch.compare_to_golden(golden)
    assert cmp["meaning_preserved"] is True, cmp["composed_checks"]


# ── Validation Inventory ──
def test_validation_inventory():
    inv = gv.validation_inventory()
    assert inv["before"]["governance_modules"] == 12
    assert inv["after"]["public_api"] == ["validate(domain)", "validate_all()"]
    assert set(inv["after"]["internal_domains"]) == set(gv.DOMAINS)
    assert inv["governance_all_pass"] is True and inv["ledger_count"] == 3


# ── 새 원장 없음 ──
def test_no_new_ledger():
    assert len(wl.ALL_LEDGERS) == 3
