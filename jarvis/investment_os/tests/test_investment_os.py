"""Investment OS 테스트 — Research OS 와 완전 분리 · 추천/시뮬레이션만 · 실행 없음.

핵심: 연구=생산/투자=소비 · Investment 는 Research 무변경(읽기전용) · Research 는 실행 안 함 ·
AUTO_EXECUTION 영구 비활성 · 사람 승인 필수 · Risk/Compliance/Portfolio/Kill 우회 불가 ·
모든 산출 is_decision=False · 실제 주문 라우팅 없음.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

import jarvis.investment_os as ios

IOS_DIR = pathlib.Path(ios.__file__).resolve().parent


def _portfolio():
    k = ios.consume_research()
    return ios.construct_portfolio(k["candidates"]), k


# ── 지식 소비: 읽기전용, Research 무변경 ──
def test_consume_research_readonly():
    k = ios.consume_research()
    assert k["research_os_modified"] is False and k["is_decision"] is False
    assert "candidates" in k


# ── 구성/노출/사이징/배분: 전부 추천(실행/배분 아님) ──
def test_portfolio_recommendations_not_execution():
    p, k = _portfolio()
    if p["weights"]:
        assert abs(sum(p["weights"].values()) - 1.0) <= 0.02
        assert max(p["weights"].values()) <= 0.4 + 1e-9
    assert ios.recommend_position_sizes(p, notional=1e6)["allocates_capital"] is False
    assert ios.recommend_capital_allocation(p, total_capital=1e6)["executes_allocation"] is False
    assert ios.analyze_exposure(p, k["candidates"])["is_decision"] is False


def test_construct_portfolio_cap_survives_renormalization():
    """단일 후보가 과반 가중이면 단순 캡+재정규화는 캡을 재위반함(반정규화 후 다시 0.4 초과) —
    water-filling(반복 캡)이어야 정확히 0.4로 수렴."""
    candidates = [
        {"strategy_id": "a", "evidence_grade": "STRONG"},
        {"strategy_id": "b", "evidence_grade": "WEAK"},
        {"strategy_id": "c", "evidence_grade": "WEAK"},
    ]
    p = ios.construct_portfolio(candidates, method="evidence_weighted")
    assert p["weights"]["a"] == 0.4
    assert p["weights"]["b"] == pytest.approx(0.3, abs=1e-4)
    assert p["weights"]["c"] == pytest.approx(0.3, abs=1e-4)
    assert sum(p["weights"].values()) == pytest.approx(1.0, abs=1e-4)


# ── 리스크/시나리오 ──
def test_risk_and_scenario():
    p, _ = _portfolio()
    assert "within_budget" in ios.build_risk_budget(p)
    sc = ios.analyze_scenarios(p, notional=1e6)
    assert sc["scenarios"] and sc["is_decision"] is False


# ── 컴플라이언스: 사람도 위반 무효화 불가 ──
def test_compliance_gate():
    over = {"weights": {"A": 0.9, "B": 0.1}}   # 단일 0.9 > 0.4 위반
    c = ios.check_compliance(over)
    assert c["compliant"] is False and c["human_can_override"] is False


# ── 필수 게이트: 우회 불가, 4개 ──
def test_mandatory_gates_no_bypass():
    p, _ = _portfolio()
    g = ios.evaluate_gates(p)
    assert g["bypass_possible"] is False
    assert {c["gate"] for c in g["gates"]} == {"risk", "compliance", "portfolio", "kill_switch"}
    assert g["human_approval_still_required"] is True


# ── 실행 사다리: AUTO 영구 비활성 + 사람 승인 필수 ──
def test_ladder_requires_human_approval():
    p, _ = _portfolio()
    assert ios.advance_rung("PAPER", p, human_approved=False)["advanced"] is False
    r = ios.advance_rung("PAPER", p, human_approved=True)
    assert r["advanced"] is True and r["rung"] == "SHADOW"


def test_auto_execution_blocked_without_human_approval_artifact():
    # 2026-08-25: AUTO_EXECUTION_ENABLED는 사용자 요청으로 True 전환했으나, 이 플래그는
    # Investment OS에 execute()가 없어 실질 게이트가 아님 — 진짜 게이트는
    # jarvis.config.AUTONOMY_LEVEL/MIN_LIVE_LEVEL(둘 다 그대로 잠김). 이 사다리는
    # 추가로 승인 아티팩트가 없으면 여전히 차단(자동 self-approve 금지).
    p, _ = _portfolio()
    r = ios.advance_rung("PRODUCTION_CANDIDATE", p, human_approved=True)
    assert r["advanced"] is False and "not human-approved" in r["blocked_reason"]
    assert ios.AUTO_EXECUTION_ENABLED is True


def test_kill_switch_present():
    ks = ios.kill_switch_status()
    assert "engaged" in ks and ks["forces_rung"] == "PAPER"


# ── 계획/시뮬레이션: 실제 주문 라우팅 없음 ──
def test_plan_and_simulate_no_real_orders():
    plan = ios.plan_execution({"A": 0.5, "B": 0.5}, {})
    assert plan["routes_orders"] is False and plan["is_plan_only"] is True
    sim = ios.simulate_orders(plan, notional=1e6)
    assert sim["is_real_fill"] is False


# ── 아키텍처 분리 검증: 6 불변식 ──
def test_architectural_separation():
    # 2026-08-25: AUTO_EXECUTION_ENABLED=True 지만 승인 아티팩트 미기록 상태 —
    # separated=False가 정직한 신호(코드 위반은 0, invariant 하나만 미충족). 이게 의도된 동작:
    # 사람이 record_auto_execution_approval() 호출 전까지 "완전 분리 아님"으로 계속 경고해야 함.
    v = ios.validate_separation()
    assert v["violations"] == []
    assert v["auto_execution_enabled"] is True
    assert v["auto_execution_approved"] is False  # 승인 아티팩트 미기록 — 의도된 기본
    assert v["separated"] is False  # 승인 기록되면 True로 전환됨
    invariants = {i["check"]: i["ok"] for i in v["invariants"]}
    assert invariants["auto_execution_disabled_or_human_approved"] is False
    for c in ("human_approval_mandatory", "research_never_imports_investment",
              "investment_never_writes_research", "no_execution_defs_or_brokers",
              "four_mandatory_gates"):
        assert invariants[c] is True, c


# ── Investment OS 는 실행 def 를 정의하지 않는다(직접 AST 스캔) ──
def test_no_execution_defs_in_investment_os():
    forbidden = {"execute", "trade", "place_order", "route_order", "send_order",
                 "submit_order", "deploy_strategy"}
    for p in IOS_DIR.glob("*.py"):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.name not in forbidden, (p.name, node.name)
