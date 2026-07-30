"""Portfolio Construction — 구성·노출·포지션사이징·자본배분 **추천**. **추천만, 실행/배분 없음.**

모든 산출은 **추천(recommendation)** — 실제 배분(allocate)·주문·집행이 아니다. 사람이 결정.
근거 등급(evidence grade)로 가중, 동일가중 폴백. is_decision=False.
"""
from __future__ import annotations

_GRADE_WEIGHT = {"STRONG": 1.0, "MEDIUM": 0.6, "WEAK": 0.3, "REJECTED": 0.0, "UNKNOWN": 0.4}
_MAX_WEIGHT = 0.4   # 단일 전략 최대 추천 비중(집중 제한)


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def construct_portfolio(candidates=None, *, method: str = "evidence_weighted") -> dict:
    """연구 후보 → **추천** 포트폴리오 가중치(합=1). 근거등급 가중 또는 동일가중. 실제 배분 아님."""
    if candidates is None:
        candidates = _safe(lambda: __import__("jarvis.investment_os.knowledge_consumer",
                                              fromlist=["consume_research"]).consume_research().get("candidates", []),
                           []) or []
    cands = [c for c in candidates if str(c.get("evidence_grade")) != "REJECTED"]
    if not cands:
        return {"weights": {}, "method": method, "count": 0,
                "requires_human_review": True, "is_advisory": True, "is_decision": False,
                "note": "구성할 후보 없음 — 연구 지식 축적 필요."}
    raw = {}
    for c in cands:
        sid = c.get("strategy_id", "")
        w = _GRADE_WEIGHT.get(str(c.get("evidence_grade")), 0.4) if method == "evidence_weighted" else 1.0
        raw[sid] = w
    total = sum(raw.values()) or 1.0
    weights = {k: v / total for k, v in raw.items()}
    # 집중 제한 water-filling(반복 캡+재정규화) — 단일 패스는 재정규화 후 캡 재위반 가능
    ids = list(weights.keys())
    fixed: dict[str, float] = {}
    for _ in range(len(ids) + 1):
        free = [k for k in ids if k not in fixed]
        if not free:
            break
        rem = 1.0 - sum(fixed.values())
        s = sum(weights[k] for k in free) or 1.0
        changed = False
        for k in free:
            nv = weights[k] / s * rem
            if nv > _MAX_WEIGHT + 1e-9:
                weights[k] = _MAX_WEIGHT
                fixed[k] = _MAX_WEIGHT
                changed = True
        if not changed:
            for k in free:
                weights[k] = weights[k] / s * rem
            break
    weights = {k: round(v, 4) for k, v in weights.items()}
    return {"weights": weights, "method": method, "count": len(weights),
            "max_weight_cap": _MAX_WEIGHT,
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Portfolio Construction(추천) — 근거등급 가중 추천 비중(합=1). 실제 배분/집행 아님. "
                     "사람이 결정.")}


def analyze_exposure(portfolio: dict, candidates=None) -> dict:
    """추천 포트폴리오의 노출 분석 — family/asset_class/집중도. 읽기전용."""
    weights = (portfolio or {}).get("weights") or {}
    meta = {c.get("strategy_id"): c for c in (candidates or [])}
    by_family: dict = {}
    by_asset: dict = {}
    for sid, w in weights.items():
        c = meta.get(sid, {})
        by_family[c.get("family") or "?"] = round(by_family.get(c.get("family") or "?", 0.0) + w, 4)
        by_asset[c.get("asset_class") or "?"] = round(by_asset.get(c.get("asset_class") or "?", 0.0) + w, 4)
    max_w = max(weights.values(), default=0.0)
    return {"by_family": dict(sorted(by_family.items())), "by_asset_class": dict(sorted(by_asset.items())),
            "concentration": {"max_weight": round(max_w, 4), "n_positions": len(weights),
                              "herfindahl": round(sum(w * w for w in weights.values()), 4)},
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": "Exposure Analysis(읽기전용) — family/asset/집중도. 추천 관점, 실행 없음."}


def recommend_position_sizes(portfolio: dict, *, notional: float = 0.0, vol_target: float = 0.1) -> dict:
    """포지션 사이징 **추천** — 추천 비중 × notional(입력값). 실제 자본 배분 아님. 사람이 결정."""
    weights = (portfolio or {}).get("weights") or {}
    sizes = {sid: round(w * (notional or 0.0), 2) for sid, w in weights.items()}
    return {"recommended_sizes": sizes, "notional_basis": notional, "vol_target": vol_target,
            "is_recommendation": True, "allocates_capital": False,
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Position Sizing(추천) — 추천 비중 × 입력 notional. 실제 자본 배분/주문 아님. 사람이 결정.")}


def recommend_capital_allocation(portfolio: dict, *, total_capital: float = 0.0) -> dict:
    """자본 배분 **추천** — 추천 비중 기반 자본 %(추천). 실제 배분(allocate) 아님. 사람이 결정."""
    weights = (portfolio or {}).get("weights") or {}
    rec = {sid: {"weight": w, "capital_pct": round(w * 100, 2),
                 "capital_amount": round(w * (total_capital or 0.0), 2)}
           for sid, w in weights.items()}
    return {"recommended_allocation": rec, "total_capital_basis": total_capital,
            "is_recommendation": True, "executes_allocation": False,
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Capital Allocation(추천) — 추천 비중 기반 자본 %. 실제 배분/집행 아님(사람 결정). "
                     "Investment OS 는 자본을 움직이지 않는다.")}
