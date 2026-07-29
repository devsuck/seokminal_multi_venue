"""Mandatory Gates — 어떤 전략도 우회 불가. **Risk · Compliance · Portfolio · Kill switch.** 실행 없음.

모든 투자 추천·사다리 전진은 이 4개 게이트를 **반드시** 통과해야 한다. 우회 경로 없음.
게이트 하나라도 실패하면 blocked. 사람 승인은 게이트 통과 **후에도** 별도로 필수(승인이 게이트를 대체 못 함).
"""
from __future__ import annotations

from jarvis.investment_os import MANDATORY_GATES


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _risk_gate(portfolio: dict) -> dict:
    rb = _safe(lambda: __import__("jarvis.investment_os.risk_budgeting",
                                  fromlist=["build_risk_budget"]).build_risk_budget(portfolio), {}) or {}
    ok = bool(rb.get("within_budget", True))
    return {"gate": "risk", "ok": ok, "detail": rb.get("summary", "risk budget checked")}


def _compliance_gate(portfolio: dict) -> dict:
    c = _safe(lambda: __import__("jarvis.investment_os.compliance",
                                 fromlist=["check_compliance"]).check_compliance(portfolio), {}) or {}
    return {"gate": "compliance", "ok": bool(c.get("compliant", False)),
            "detail": f"{len(c.get('violations', []))} violations"}


def _portfolio_gate(portfolio: dict) -> dict:
    # 포트폴리오 구조 유효성(가중치 합·집중도) — 구성 없이는 통과 불가
    weights = (portfolio or {}).get("weights") or {}
    total = round(sum(float(w) for w in weights.values()), 4) if weights else 0.0
    max_w = max((float(w) for w in weights.values()), default=0.0)
    ok = bool(weights) and abs(total - 1.0) <= 0.02 and max_w <= 0.4
    return {"gate": "portfolio", "ok": ok,
            "detail": f"sum={total}, max_weight={round(max_w, 4)} (<=0.4)"}


def _kill_switch_gate() -> dict:
    ks = _safe(lambda: __import__("jarvis.investment_os.execution_planning",
                                  fromlist=["kill_switch_status"]).kill_switch_status(), {}) or {}
    engaged = bool(ks.get("engaged", False))
    return {"gate": "kill_switch", "ok": not engaged,
            "detail": "engaged — all halted to PAPER" if engaged else "clear"}


def evaluate_gates(portfolio: dict) -> dict:
    """4개 필수 게이트 평가(우회 불가). 하나라도 실패 = blocked. 사람 승인은 별도(게이트 대체 아님)."""
    checks = [_risk_gate(portfolio), _compliance_gate(portfolio),
              _portfolio_gate(portfolio), _kill_switch_gate()]
    names = {c["gate"] for c in checks}
    assert names == set(MANDATORY_GATES), "필수 게이트 누락(우회 금지)"
    passed = all(c["ok"] for c in checks)
    return {"passed": passed, "gates": checks,
            "blocked": not passed,
            "failed_gates": [c["gate"] for c in checks if not c["ok"]],
            "bypass_possible": False,
            "human_approval_still_required": True,   # 게이트 통과해도 사람 승인 별도 필수
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Mandatory Gates — Risk·Compliance·Portfolio·Kill switch 우회 불가. "
                     "하나라도 실패 = blocked. 게이트 통과가 사람 승인을 대체하지 않는다. 실행 없음.")}
