"""Compliance — 필수 컴플라이언스 점검(우회 불가 게이트). **점검만, 실행 없음.**

규칙(결정적): 단일 전략 집중 한도 · 총 비중(레버리지) 한도 · 제한종목(restricted list) · 최소 분산.
위반 시 non-compliant → 게이트 blocked. 사람 승인이 위반을 무효화하지 못한다.
"""
from __future__ import annotations

_MAX_SINGLE_WEIGHT = 0.4
_MAX_GROSS = 1.0          # 레버리지 금지(합<=1.0)
_MIN_POSITIONS = 1
_RESTRICTED = ()          # 제한종목(주입 가능) — 기본 없음


def check_compliance(portfolio: dict, *, restricted=None) -> dict:
    """컴플라이언스 점검(결정적) — 집중·레버리지·제한종목·분산. 위반 = non-compliant(게이트 blocked)."""
    weights = (portfolio or {}).get("weights") or {}
    restricted = set(restricted or _RESTRICTED)
    violations = []
    for sid, w in weights.items():
        if float(w) > _MAX_SINGLE_WEIGHT:
            violations.append({"rule": "single_weight_limit", "strategy": sid, "value": round(float(w), 4),
                               "limit": _MAX_SINGLE_WEIGHT})
        if sid in restricted:
            violations.append({"rule": "restricted_list", "strategy": sid})
    gross = round(sum(float(w) for w in weights.values()), 4)
    if gross > _MAX_GROSS + 0.02:
        violations.append({"rule": "leverage_limit", "gross": gross, "limit": _MAX_GROSS})
    if weights and len(weights) < _MIN_POSITIONS:
        violations.append({"rule": "min_positions", "n": len(weights)})
    compliant = not violations
    return {"compliant": compliant, "violations": violations,
            "rules_checked": ["single_weight_limit", "leverage_limit", "restricted_list", "min_positions"],
            "gross_exposure": gross, "human_can_override": False,   # 사람도 위반 무효화 불가
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Compliance(필수 게이트) — 집중·레버리지·제한종목·분산. 위반 = blocked. "
                     "사람 승인이 위반을 무효화하지 못한다. 실행 없음.")}
