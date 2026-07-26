"""Large Scale Research Expansion (P175) — 가설 1건 → 수백 관련 후보. **제안만, 실행 없음.**

브루트포스 금지. **계층적 프루닝**으로 확장한다: 1차 차원 리프(research_search P172 재사용) →
상위 리프만 2차 차원으로 확장 → 중복 탐지(research_similarity P134 재사용) → 최고가치만 표면화.
전량(cartesian)이 아니라 유망 가지만 깊게.

**기존 모듈 재사용**: research_search(P172, 차원·리프·병합)·research_similarity(P134, 중복).
새 엔진/저장소 없음.

원칙(문서 §Constitution, §P175): 통합·조율만 · 결정적 · 자문 전용 · 연구 자동 실행 없음 ·
거래·집행 없음 · 사람이 모든 결정.
"""
from __future__ import annotations

_SECOND_DIMS = ("regime", "timeframe", "validation")   # 2차 전개 차원(결정적)
_EXPAND_TOP = 6                                          # 1차 상위 몇 개만 2차 전개(계층적 프루닝)
_MERGE_THRESHOLD = 0.9


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _hid(statement):
    return _safe(lambda: __import__("jarvis.research_workflow.models",
                                    fromlist=["hypothesis_id"]).hypothesis_id(statement),
                 "HYP:" + str(abs(hash(statement)) % (10 ** 10)))


def _search(hypothesis, top_k):
    def _go():
        from jarvis.research_workflow.research_search import build_search_space
        return build_search_space(hypothesis, top_k=top_k)
    return _safe(_go, {"highest_value_candidates": [], "tree": []}) or {}


def _second_values():
    from jarvis.research_workflow.research_search import _DIM_VALUES
    return {d: _DIM_VALUES.get(d, ()) for d in _SECOND_DIMS}


def _dedupe(candidates):
    """research_similarity 로 근접 중복 제거(높은 스코어 유지)."""
    sim = _safe(lambda: __import__("jarvis.research_workflow.research_similarity",
                                   fromlist=["ResearchSimilarity"]).ResearchSimilarity())
    kept, removed = [], 0
    for c in sorted(candidates, key=lambda x: (-x["score"], x["hypothesis_id"])):
        dup = False
        for k in kept:
            if c["statement"] == k["statement"]:
                dup = True
                break
            if sim is not None:
                s = _safe(lambda: sim.compare(c["statement"], k["statement"])["similarity_score"], 0.0)
                if s >= _MERGE_THRESHOLD:
                    dup = True
                    break
        if dup:
            removed += 1
        else:
            kept.append(c)
    return kept, removed


def expand_research(hypothesis, *, top_k: int = 25) -> dict:
    """가설 → 대규모 후보(계층적 프루닝 + 중복탐지). 결정적·읽기전용. 연구 자동 실행 없음.

    수백 후보를 생성 가능하되 브루트포스 대신 상위 가지만 깊게 전개 → 정보가치 높은 것만 남긴다.
    """
    root = hypothesis.get("statement") if isinstance(hypothesis, dict) else str(hypothesis or "")

    # 1차 전개(research_search 재사용)
    first = _search(root, top_k=40)
    level1 = list(first.get("highest_value_candidates", []))

    # 2차 전개 — 1차 상위 _EXPAND_TOP 개만 2차 차원으로 곱한다(계층적 프루닝)
    second_vals = _second_values()
    generated = len(level1)
    level2 = []
    for parent in level1[:_EXPAND_TOP]:
        for dim, values in second_vals.items():
            for i, v in enumerate(values):
                if parent.get("dimension") == dim:      # 같은 차원 재전개 방지
                    continue
                stmt = f"{parent['statement']} & {dim}={v}"
                generated += 1
                score = round(float(parent.get("score", 0.5)) * (0.9 - 0.03 * i), 4)
                level2.append({"hypothesis_id": _hid(stmt), "statement": stmt,
                               "dimension": f"{parent.get('dimension')}+{dim}", "value": v,
                               "score": score, "depth": 2,
                               "requires_human_review": True, "is_advisory": True, "is_decision": False})

    for c in level1:
        c.setdefault("depth", 1)
    combined = level1 + level2

    deduped, removed = _dedupe(combined)
    deduped.sort(key=lambda x: (-x["score"], x["hypothesis_id"]))
    surfaced = deduped[:top_k]

    return {"root_hypothesis": root, "root_id": _hid(root),
            "generated": generated, "after_dedupe": len(deduped),
            "duplicates_removed": removed, "surfaced_count": len(surfaced),
            "expansion_strategy": "hierarchical_pruning (1차 전량 → 상위 %d개만 2차 전개)" % _EXPAND_TOP,
            "depth_breakdown": {"level_1": len(level1), "level_2": len(level2)},
            "highest_value_candidates": surfaced,
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Large Scale Research Expansion(읽기전용) — 계층적 프루닝 + 중복탐지(유사도 재사용). "
                     "브루트포스 아님. 연구 자동 실행 없음, 새 엔진/원장 없음. 사람이 모든 결정.")}
