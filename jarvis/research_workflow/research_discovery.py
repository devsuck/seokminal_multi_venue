"""Research Discovery (P204) — 가설 발견의 **단일 공개 파사드**. **조율만, 실행 없음.**

실제 연구 과정 = 발견 → 탐색 → 확장 → 비판 → 선택. 이 흐름을 하나의 namespace 로 묶는다:
  generate() · search() · expand() · criticize() · rank() (+ discover() 편의).

밖에서는 이것만 호출. 내부에서만 기존 모듈 조율(모두 **유지·deprecated**, ≥1 릴리스):
  hypothesis_discovery(P183, recall-first) · creative_hypothesis(P171) · hypothesis_generator(P73) ·
  research_search(P172) · research_expansion(P175) · research_critic(P75) · research_priority(P185).

**기존 모듈 삭제 안 함 — 파사드는 조율만.** 새 지능/저장소 없음. 호출 구조는 Call Graph Golden 이 감시.
원칙(§Constitution): 통합·조율만 · 결정적 · 자문 전용 · 거래·집행 없음 · 사람이 결정.
"""
from __future__ import annotations


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def generate(topic: str = "", *, opportunity=None, limit: int = 8, mode: str = "recall_first") -> dict:
    """가설 발견(제안). mode: recall_first(hypothesis_discovery) | creative(creative_hypothesis) |
    template(hypothesis_generator). 기본 recall_first(과거 실패 유사 시 '왜 다른지' 포함). 결정적."""
    m = (mode or "recall_first").lower()
    if m == "creative":
        r = _safe(lambda: __import__("jarvis.research_workflow.creative_hypothesis",
                                     fromlist=["discover_hypotheses"]).discover_hypotheses(topic, limit=limit),
                  {}) or {}
        items = r.get("hypotheses", [])
    elif m == "template":
        r = _safe(lambda: [h.to_dict() for h in __import__(
            "jarvis.research_workflow.hypothesis_generator", fromlist=["HypothesisGenerator"]
        ).HypothesisGenerator().generate(topic, limit=limit)], []) or []
        items = r
    else:
        r = _safe(lambda: __import__("jarvis.research_workflow.hypothesis_discovery",
                                     fromlist=["discover_research"]
                                     ).discover_research(topic, opportunity=opportunity, limit=limit),
                  {}) or {}
        items = r.get("research_hypotheses", [])
    return {"stage": "generate", "mode": m, "topic": topic, "count": len(items), "hypotheses": items,
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": "Research Discovery.generate(읽기전용) — 기존 가설 모듈 조율(제안). 삭제 아님, 파사드."}


def search(hypothesis, *, top_k: int = 12) -> dict:
    """가설 → 구조화된 탐색 트리(research_search 조율). 차원별 변형·스코어·프루닝. 결정적·읽기전용."""
    r = _safe(lambda: __import__("jarvis.research_workflow.research_search",
                                 fromlist=["build_search_space"]).build_search_space(hypothesis, top_k=top_k),
              {}) or {}
    return {"stage": "search", **r,
            "requires_human_review": True, "is_advisory": True, "is_decision": False}


def expand(hypothesis, *, top_k: int = 12, scale: bool = True) -> dict:
    """가설 → 대규모 관련 후보 확장(research_expansion 조율, 계층적 프루닝). scale=False 면 search 트리. 결정적."""
    if not scale:
        return {**search(hypothesis, top_k=top_k), "stage": "expand"}
    r = _safe(lambda: __import__("jarvis.research_workflow.research_expansion",
                                 fromlist=["expand_research"]).expand_research(hypothesis, top_k=top_k),
              {}) or {}
    return {"stage": "expand", "scale": scale, **r,
            "requires_human_review": True, "is_advisory": True, "is_decision": False}


def criticize(item, *, metrics=None) -> dict:
    """가설/스펙 → 8차원 비판(research_critic 조율). verdict PASS/WARN/BLOCK. 자동 수용 없음. 결정적."""
    spec = item
    if isinstance(item, dict) and not (item.get("strategy_name") or item.get("feature_set")):
        # 가설 dict → 최소 스펙으로 변환(비판 입력)
        spec = {"strategy_name": item.get("question") or item.get("statement") or "hypothesis",
                "feature_set": item.get("evidence_used") or item.get("required_test") or [],
                "metrics": metrics or {}}
    r = _safe(lambda: __import__("jarvis.research_workflow.research_critic",
                                 fromlist=["ResearchCritic"]).ResearchCritic().critique(spec, metrics),
              None)
    report = r.to_dict() if hasattr(r, "to_dict") else (r or {})
    return {"stage": "criticize", "critique": report, "verdict": report.get("verdict"),
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": "Research Discovery.criticize(읽기전용) — research_critic 조율. 약한 연구 BLOCK, 자동 수용 없음."}


def rank(candidates, *, limit: int = 10) -> dict:
    """후보 → Research Priority 순위(research_priority 조율). 추천만. 결정적."""
    r = _safe(lambda: __import__("jarvis.research_workflow.research_priority",
                                 fromlist=["prioritize_research"]).prioritize_research(candidates, limit=limit),
              {}) or {}
    return {"stage": "rank", **r,
            "requires_human_review": True, "is_advisory": True, "is_decision": False}


def discover(topic: str = "", *, opportunity=None, limit: int = 8) -> dict:
    """편의 전 흐름 — generate → rank(제안). 발견 후 우선순위까지. 결정적·읽기전용."""
    gen = generate(topic, opportunity=opportunity, limit=limit)
    ranked = rank(gen.get("hypotheses", []), limit=limit)
    return {"topic": topic, "generated": gen.get("count", 0),
            "research_queue": ranked.get("research_queue", []), "top": ranked.get("top", {}),
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Research Discovery.discover(읽기전용) — generate→rank 단일 파사드. "
                     "내부 모듈 조율(삭제 아님, deprecated). 연구 자동 실행 없음. 사람이 결정.")}
