"""Research Capture Runbook (P201-ops) — 현재 연구 판단을 예측 레지스트리로 흘려보낸다. **기록만, 실행 없음.**

목적: "시계 시작". 추적 중인 전략(paper_active·watchlist·paper_candidate)의 **현재 위원회 평가**를
예측 스냅샷으로 박제한다. 이래야 horizon 후 P205 Validation Score 가 실제 숫자를 낼 수 있다.

**재사용**: prediction_capture_hook(P202)·investment_committee(P161)·registry. 새 원장 없음(rmi_ 재사용).
**중복 방지**: 같은 (strategy_id, thesis) 예측이 이미 있으면 skip(coverage audit 의 duplicate 와 정합).
원칙(§Constitution): 통합·기록만 · 결정적 · 자문 전용 · 거래·집행·포트폴리오 없음 · 사람이 결정.
"""
from __future__ import annotations

# 추적 대상 상태(실제 검토 중인 전략만 — 노이즈 최소)
TRACKED_STATES = ("paper_active", "watchlist", "paper_candidate")
# 전략명 키워드 → strategy_family(evaluation_framework 결정적 유도용)
_FAMILY_HINTS = (
    ("momentum", "momentum"), ("tsmom", "momentum"), ("reversal", "momentum"),
    ("buyback", "event"), ("dart", "event"), ("bonus", "event"), ("cb_", "event"),
    ("turn_of_month", "event"), ("insider", "event"), ("earnings", "event"),
    ("funding", "market_neutral"), ("pairs", "market_neutral"), ("statarb", "market_neutral"),
    ("carry", "market_neutral"), ("cross_sectional", "factor"), ("factor", "factor"),
    ("size", "factor"), ("low_vol", "factor"), ("illiq", "factor"), ("regime", "macro"),
)


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _infer_family(strategy_id: str, registry_family: str = "") -> str:
    if registry_family:
        return str(registry_family).lower()
    s = (strategy_id or "").lower()
    for kw, fam in _FAMILY_HINTS:
        if kw in s:
            return fam
    return ""   # → baseline_relative 기본


def _tracked_strategies() -> list:
    reg = _safe(lambda: __import__("jarvis.registry", fromlist=["StrategyRegistry"]
                                   ).StrategyRegistry().all_current(), []) or []
    return [s for s in reg if str(s.get("status")) in TRACKED_STATES]


def _existing_keys() -> set:
    preds = _safe(lambda: __import__("jarvis.research_workflow.prediction_registry",
                                     fromlist=["list_predictions"]).list_predictions(), []) or []
    return {(p.get("strategy_id"), str(p.get("thesis", "")).strip().lower()) for p in preds}


def capture_tracked_research(*, now: str = "", commit: bool = False, limit: int = 50) -> dict:
    """추적 전략의 현재 위원회 평가 → 예측 사전등록(중복 skip). 결정적·멱등(내용 중복 skip).

    commit=False = 미리보기(원장 무변경). 이것이 예측 데이터 축적의 단일 진입점.
    """
    from jarvis.research_workflow import prediction_capture_hook as hook

    tracked = _tracked_strategies()[:limit]
    existing = _existing_keys()
    captured, skipped = 0, 0
    by_family: dict = {}
    records = []
    for s in tracked:
        sid = s.get("strategy_id", "")
        family = _infer_family(sid, s.get("family", ""))
        packet = _safe(lambda ss=s: __import__("jarvis.research_workflow.investment_committee",
                                               fromlist=["build_committee_packet"]
                                               ).build_committee_packet(f"Does {ss.get('strategy_id')} have durable edge?"),
                       {}) or {}
        thesis = str(packet.get("research_summary") or f"{sid} durable edge assessment")
        key = (sid, thesis.strip().lower())
        if key in existing:
            skipped += 1
            continue
        snap = hook.capture_from_committee(packet, strategy_id=sid, strategy_family=family,
                                           now=now, commit=commit)
        existing.add(key)
        captured += 1
        by_family[family or "_default"] = by_family.get(family or "_default", 0) + 1
        records.append({"strategy_id": sid, "family": family, "confidence": snap.get("confidence"),
                        "framework": snap.get("evaluation_framework", {}).get("framework")})

    return {"committed": bool(commit), "tracked_strategies": len(tracked),
            "captured": captured, "skipped_duplicates": skipped,
            "by_family": dict(sorted(by_family.items())), "sample": records[:8],
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Research Capture(기록만) — 추적 전략의 현재 평가를 예측으로 박제. 중복 skip(멱등). "
                     "지금 기록해야 horizon 후 P205 점수 산출 가능. 새 원장 없음, 거래·포트폴리오 없음.")}
