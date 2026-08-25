"""복수 전략 합의 판단 — 단일 전략 단독 실행 금지(사용자 명시: "하나로만 가는건 너무 위험").

Tier A(base) = arm_criteria.py의 동결 GO 기준을 통과하고 사람이 arm()한 전략.
  base 신호 없으면 아무 것도 안 함 — Tier B는 절대 단독 트리거 불가.
Tier B(booster) = draft 상태 + 실데이터(data_version 있음) + sanity_only 아님인
  후보. base와 같은 방향으로 ≥2개 동의하면 사이즈 30% 부스트(상한 고정, 그 이상
  없음). 이 모듈은 arm_criteria.py를 절대 수정하지 않는다 — 그 결과를 그대로
  소비만 한다.
"""
from __future__ import annotations

from jarvis.execution.arm import is_armed
from jarvis.execution.arm_criteria import evaluate as _arm_criteria_evaluate
from jarvis.registry import StrategyRegistry

BOOST_MULTIPLIER = 1.3
MIN_TIER_B_AGREEING = 2


def base_signal(strategy_id: str, edge: dict, paper_months: float, direction: str) -> dict | None:
    """base 신호 자격 판정. armed + arm_criteria GO 둘 다면 신호 반환, 아니면 None."""
    if not is_armed(strategy_id):
        return None
    decision = _arm_criteria_evaluate(edge, paper_months)
    if decision["decision"] != "GO":
        return None
    return {"strategy_id": strategy_id, "direction": direction, "arm_criteria": decision}


def tier_b_signal(strategy_id: str, direction: str) -> dict | None:
    """draft + 실데이터 + sanity_only 아님이면 신호 반환. 호출부가 후보 목록을
    명시로 넘겨야 함(암묵 매칭 금지 — jarvis.execution.agent_gate와 동일 원칙)."""
    st = StrategyRegistry().state(strategy_id)
    if st is None or st["status"] != "draft":
        return None
    if not st.get("data_version") or st["data_version"] == "unknown":
        return None
    if "sanity_only" in (st.get("flags") or []):
        return None
    return {"strategy_id": strategy_id, "direction": direction}


def evaluate(base: dict | None, tier_b_candidates: list[dict]) -> dict:
    """base: base_signal()의 반환값(또는 None). tier_b_candidates: tier_b_signal()
    반환값 리스트(None 제외하고 호출부가 필터링해서 넘김).
    반환: {action: "none"|"trade", direction, size_multiplier, agreeing_tier_b}."""
    if base is None:
        return {"action": "none", "reason": "no_base_signal"}

    agreeing = [c for c in tier_b_candidates if c["direction"] == base["direction"]]
    boosted = len(agreeing) >= MIN_TIER_B_AGREEING
    return {
        "action": "trade",
        "strategy_id": base["strategy_id"],
        "direction": base["direction"],
        "size_multiplier": BOOST_MULTIPLIER if boosted else 1.0,
        "agreeing_tier_b": [c["strategy_id"] for c in agreeing],
    }
