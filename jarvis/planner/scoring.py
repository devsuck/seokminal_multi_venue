"""Planner 결정적 스코어링 (P5) — priority = impact × confidence × evidence_strength.

ML/난수 없음. 모든 인자는 관찰가능·설명가능. 각 인자 [0,1]로 클램프.
"""
from __future__ import annotations


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else (1.0 if x > 1 else float(x))


def score(impact: float, confidence: float, evidence_strength: float) -> dict:
    i, c, e = _clamp01(impact), _clamp01(confidence), _clamp01(evidence_strength)
    return {"priority": round(i * c * e, 6), "impact": round(i, 4),
            "confidence": round(c, 4), "evidence_strength": round(e, 4)}


def saturating(count: float, denom: float) -> float:
    """count/denom, 1.0 상한. denom<=0이면 0."""
    if denom <= 0:
        return 0.0
    return min(1.0, count / denom)
