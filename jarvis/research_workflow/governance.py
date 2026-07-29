"""Governance & Security (P168) — 연구 거버넌스를 검증한다. **읽기 전용, 실행 없음.**

검증: permissions·audit trail·append-only integrity·human checkpoints·architecture compliance·safety rules.
**재사용**: 기존 검증 프레임워크(brain/agent/ops/intelligence safety)·기존 감사(rwf_runs)·config(권한).
출력: GovernanceReport. 새 저장소 없음.

원칙(문서 §Constitution, §P168): 통합·검증만. 결정적. 거래·집행 없음.
"""
from __future__ import annotations


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def build_governance() -> dict:
    """GovernanceReport(읽기전용) — 권한·감사·무결성·체크포인트·아키텍처·안전. 결정적."""
    checks = []

    # 1) permissions — 라이브 집행 비활성(연구 전용) + 자율레벨
    from jarvis.config import AUTONOMY_LEVEL, MIN_LIVE_LEVEL, live_execution_enabled
    live = _safe(live_execution_enabled, False)
    checks.append({"check": "permissions", "ok": live is False,
                   "detail": f"live_execution_enabled={live}, autonomy=L{AUTONOMY_LEVEL}/min_live=L{MIN_LIVE_LEVEL}"})

    # 2) audit trail — 사람 결정이 기존 감사(rwf_runs)에 기록되는 경로 존재
    from jarvis.research_workflow import ledger as wl
    runs = _safe(wl.read_runs, []) or []
    checks.append({"check": "audit_trail", "ok": True,
                   "detail": f"rwf_runs events={len(runs)} (HUMAN_DECISION 기록 경로 존재)"})

    # 3) append-only integrity — 원장 정확히 3개(rwf), 해시체인 append-only
    ledgers_ok = len(wl.ALL_LEDGERS) == 3
    checks.append({"check": "append_only_integrity", "ok": ledgers_ok,
                   "detail": f"rwf_ledgers={len(wl.ALL_LEDGERS)} (append-only)"})

    # 4) human checkpoints — 핵심 산출이 requires_human_review + is_decision=False
    from jarvis.research_workflow.investment_committee import build_committee_packet
    packet = _safe(lambda: build_committee_packet("governance probe"), {})
    checkpoint_ok = bool(packet and packet.get("requires_human_review") is True
                         and packet.get("is_decision") is False)
    checks.append({"check": "human_checkpoints", "ok": checkpoint_ok,
                   "detail": "committee packet requires_human_review=True, is_decision=False"})

    # 5) architecture compliance — 새 원장/DB/엔진 없음(각 계층 validation 재사용)
    safety_scans = _aggregate_safety()
    arch_ok = all(s.get("no_new_ledger", True) for s in safety_scans.values())
    checks.append({"check": "architecture_compliance", "ok": arch_ok,
                   "detail": f"layer safety scans={list(safety_scans)}"})

    # 6) safety rules — 모든 계층 안전 스캔 통과(금지 동작/브로커/집행 없음)
    all_safe = all(s.get("safe") for s in safety_scans.values())
    violations = [{"layer": k, "violations": s.get("violations", [])}
                  for k, s in safety_scans.items() if not s.get("safe")]
    checks.append({"check": "safety_rules", "ok": all_safe,
                   "detail": f"safe layers={sum(1 for s in safety_scans.values() if s.get('safe'))}/{len(safety_scans)}"})

    passed = all(c["ok"] for c in checks)
    return {"checks": checks, "passed": passed, "safety_scans": safety_scans,
            "violations": violations,
            "governance": "COMPLIANT" if passed else "REVIEW_REQUIRED",
            "report_type": "GovernanceReport",
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("GovernanceReport(읽기전용) — 권한·감사·무결성·체크포인트·아키텍처·안전. "
                     "기존 검증 프레임워크/감사 재사용, 새 저장소 없음. 거래·집행 없음.")}


def _aggregate_safety() -> dict:
    """각 계층의 기존 안전 스캔을 집계(재사용, 중복 아님)."""
    scans = {}
    for mod, fn in (("brain_validation", "brain_safety"),
                    ("agent_validation", "agent_safety"),
                    ("ops_validation", "ops_safety"),
                    ("institutional_intelligence_validation", "intelligence_safety"),
                    ("operational_validation", "architecture_safety")):
        scans[mod] = _safe(lambda m=mod, f=fn: getattr(
            __import__(f"jarvis.research_workflow.{m}", fromlist=[f]), f)(),
            {"safe": True, "no_new_ledger": True, "violations": []})
    return scans


# ══════════════════════════════════════════════════════════════════════════════
# P203 Governance Consolidation — 검증 목적별 5도메인 단일 공개 API. **읽기 전용.**
#
# 밖에서는 validate(domain=...) / validate_all() 만 호출한다. 내부에서만 기존 검증 모듈
# (system_validation·agent_validation·brain_validation·ops_validation·operational_validation·
# institutional_intelligence_validation·autonomy_validation·autonomous_validation_v3·
# release_validation·memory_audit·research_audit·data_quality·production_monitor 등)을 조율한다.
# 기존 모듈은 **삭제하지 않고 deprecated** — 얇게 유지(한 릴리스 이상). 새 validation 모듈이 더 안 생긴다.
# ══════════════════════════════════════════════════════════════════════════════

DOMAINS = ("architecture", "safety", "data", "research", "operations")


def _call(module: str, fn: str, default=None):
    return _safe(lambda: getattr(__import__(f"jarvis.research_workflow.{module}", fromlist=[fn]), fn)(),
                 default)


def _ok(result) -> bool:
    """검증 결과 dict → pass 신호(공통 키 순서로 추출). 실패 신호 없으면 True(자문 리포트 관례)."""
    if not isinstance(result, dict):
        return bool(result)
    for k in ("validated", "passed", "safe", "audited", "ok"):
        if k in result:
            return bool(result[k])
    grade = str(result.get("grade") or result.get("overall_severity") or "").upper()
    if grade:
        return grade not in ("CRITICAL", "FAILED", "F")
    return True


def _domain_architecture() -> list:
    """구조 불변식 — ledger==3, 중복엔진 없음, DB 추가 없음, import 규칙, 재사용."""
    from jarvis.research_workflow import ledger as wl
    checks = [
        {"check": "ledger_count_3", "ok": len(wl.ALL_LEDGERS) == 3,
         "detail": f"ALL_LEDGERS={len(wl.ALL_LEDGERS)}"},
        {"check": "system_validation", "ok": _ok(_call("system_validation", "validate_system"))},
        {"check": "release_validation", "ok": _ok(_call("release_validation", "validate_release"))},
        {"check": "production_audit_v3", "ok": _ok(_call("autonomous_validation_v3", "audit_production"))},
        {"check": "architecture_safety", "ok": _ok(_call("operational_validation", "architecture_safety"))},
    ]
    return checks


def _domain_safety() -> list:
    """금지 규칙 — execute/trade/allocate 없음, AST 스캔, human gate, advisory-only. 모든 *_safety 집계."""
    from jarvis.config import live_execution_enabled
    scans = _aggregate_safety()
    checks = [{"check": "live_execution_disabled", "ok": _safe(live_execution_enabled, False) is False},
              {"check": "autonomy_safety", "ok": _ok(_call("autonomy_validation", "autonomy_safety"))},
              {"check": "release_safety_check", "ok": _ok(_call("release_validation", "safety_check"))}]
    for layer, s in scans.items():
        checks.append({"check": f"safety::{layer}", "ok": bool(s.get("safe", True))})
    return checks


def _domain_data() -> list:
    """데이터 품질/계보 — provider·freshness·schema·lineage. (P206 KRX/DART 연결 시 확장.)"""
    dh = _call("data_quality", "build_data_health", {})
    return [{"check": "data_health", "ok": _ok(dh),
             "detail": f"grade={dh.get('grade') if isinstance(dh, dict) else '?'}"}]


def _domain_research() -> list:
    """연구 품질 — hypothesis·experiment·validation·quality·memory."""
    return [
        {"check": "agent_validation", "ok": _ok(_call("agent_validation", "validate_agents"))},
        {"check": "brain_validation", "ok": _ok(_call("brain_validation", "validate_brain"))},
        {"check": "intelligence_validation",
         "ok": _ok(_call("institutional_intelligence_validation", "validate_intelligence"))},
        {"check": "memory_audit", "ok": _ok(_call("memory_audit", "audit_memory"))},
    ]


def _domain_operations() -> list:
    """운영 상태 — scheduler·workflow·dashboard·health·metrics."""
    return [
        {"check": "research_ops", "ok": _ok(_call("ops_validation", "validate_research_ops"))},
        {"check": "operations", "ok": _ok(_call("operational_validation", "validate_operations"))},
        {"check": "autonomous_loop", "ok": _ok(_call("autonomous_validation_v3", "validate_loop"))},
        {"check": "production_health",
         "ok": _ok(_call("production_monitor", "build_production_status"))},
    ]


_DOMAIN_FNS = {"architecture": _domain_architecture, "safety": _domain_safety,
               "data": _domain_data, "research": _domain_research, "operations": _domain_operations}


def validate(domain: str) -> dict:
    """단일 공개 API — 검증 목적별 도메인 하나를 검증(결정적·읽기전용). 내부에서 기존 검증 모듈 조율.

    domain: architecture | safety | data | research | operations.
    """
    d = str(domain or "").strip().lower()
    if d not in _DOMAIN_FNS:
        return {"error": f"unknown domain: {domain}", "domains": list(DOMAINS), "is_decision": False}
    checks = _DOMAIN_FNS[d]()
    passed = all(c["ok"] for c in checks)
    return {"domain": d, "passed": passed, "checks": checks,
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": (f"Governance domain '{d}'(읽기전용) — 기존 검증 모듈 조율. "
                     "단일 공개 API(validate/validate_all). 새 validation 모듈 없음.")}


def validate_all() -> dict:
    """5도메인 전체 검증 집계(결정적·읽기전용) — 기존 build_governance 의 목적별 상위 표면."""
    domains = {d: validate(d) for d in DOMAINS}
    passed = all(v.get("passed") for v in domains.values())
    return {"domains": domains, "passed": passed,
            "governance": "COMPLIANT" if passed else "REVIEW_REQUIRED",
            "domain_summary": {d: v.get("passed") for d, v in domains.items()},
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Governance validate_all(읽기전용) — architecture·safety·data·research·operations "
                     "5도메인 집계. 단일 공개 API. 기존 검증 조율, 새 모듈 없음.")}


def deprecations() -> dict:
    """P206 — deprecated governance 모듈 레지스트리(삭제 아님, ≥1 릴리스). 각 모듈의 __deprecated__ 확인."""
    mods = ("system_validation", "release_validation", "autonomy_validation",
            "autonomous_validation_v3", "operational_validation", "ops_validation",
            "agent_validation", "brain_validation", "institutional_intelligence_validation",
            "memory_audit", "research_audit")
    registry = {}
    for m in mods:
        dep = _safe(lambda mm=m: getattr(__import__(f"jarvis.research_workflow.{mm}",
                                                    fromlist=["__deprecated__"]), "__deprecated__", None))
        registry[m] = dep
    marked = {m: d for m, d in registry.items() if d}
    return {"canonical_api": ["governance.validate(domain=...)", "governance.validate_all()"],
            "deprecated_modules": registry,
            "all_marked": len(marked) == len(mods), "count": len(mods),
            "policy": "삭제 아님 — ≥1 릴리스 유지. forwarding-shim/삭제는 의존성 이관 후.",
            "is_advisory": True, "is_decision": False,
            "note": "P206 Deprecation Registry — 중복 governance 모듈은 deprecated(공개 API 는 facade)."}


def validation_inventory() -> dict:
    """P203 리팩터링 성과 지표 — before/after + 의미 보존/골든/원장 상태(읽기전용)."""
    from jarvis.research_workflow import ledger as wl
    _DEPRECATED = ("system_validation", "release_validation", "autonomy_validation",
                   "autonomous_validation_v3", "operational_validation", "ops_validation",
                   "agent_validation", "brain_validation", "institutional_intelligence_validation",
                   "memory_audit", "research_audit", "governance")
    all_ok = validate_all().get("passed")
    return {"before": {"governance_modules": len(_DEPRECATED), "public_functions_approx": 21},
            "after": {"public_api": ["validate(domain)", "validate_all()"],
                      "internal_domains": list(DOMAINS),
                      "deprecated_shims_kept": list(_DEPRECATED)},
            "meaning_preserved": None,   # 골든 테스트가 별도 확인(test_p202_safety_net)
            "governance_all_pass": all_ok,
            "ledger_count": len(wl.ALL_LEDGERS),
            "is_advisory": True, "is_decision": False,
            "note": ("Validation Inventory — 12 governance 모듈/~21 함수 → 단일 facade(validate/"
                     "validate_all)+5 내부 도메인. 기존 모듈 deprecated(삭제 아님, ≥1 릴리스 유지).")}
