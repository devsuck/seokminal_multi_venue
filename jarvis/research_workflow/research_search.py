"""Autonomous Research Search (P172) — 하나의 가설을 **구조화된 연구 탐색 공간**으로 전개한다. **제안만, 실행 없음.**

가설 1건 → 차원별 변형(parameter·universe·sector·country·exchange·timeframe·regime·validation) →
연구 트리 구축 → 브랜치 스코어링 → 약한 브랜치 프루닝 → 중복 병합(ResearchSimilarity 재사용) →
최고가치 후보만 표면화.

**기존 모듈 재사용**: research_similarity(P134, 중복 병합)·sector_intelligence(P153, 섹터 목록)·
research_prioritizer(P76, 스코어 참고). 새 엔진/저장소 없음.

원칙(문서 §Constitution, §P172): 통합·조율만 · 결정적 · 자문 전용 · 연구 자동 실행 없음 ·
거래·집행 없음 · 사람이 모든 결정.
"""
from __future__ import annotations

# 탐색 차원 → 후보 값(결정적, 소규모). 브레인스토밍이 아니라 구조화된 전개.
_DIM_VALUES = {
    "universe": ("KR_equities", "US_equities", "crypto", "futures"),
    "timeframe": ("daily", "weekly", "intraday"),
    "regime": ("trend", "range", "high_vol"),
    "validation": ("walk_forward", "out_of_sample", "cost_stress", "survivorship_control"),
    "parameter": ("lookback_short", "lookback_mid", "lookback_long"),
}
# 차원 가치 가중(결정적) — 정보가치·구현타당성 반영
_DIM_WEIGHT = {"universe": 0.9, "regime": 0.8, "sector": 0.75, "timeframe": 0.6,
               "validation": 0.55, "parameter": 0.5}
_MERGE_THRESHOLD = 0.92     # 유사도 이 이상이면 중복으로 병합
_PRUNE_THRESHOLD = 0.45     # 스코어 이 미만이면 프루닝


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _root_statement(hypothesis) -> str:
    if isinstance(hypothesis, dict):
        return str(hypothesis.get("statement") or hypothesis.get("question") or "")
    return str(hypothesis or "")


def _sectors(limit=3):
    s = _safe(lambda: __import__("jarvis.research_workflow.sector_intelligence",
                                 fromlist=["supported_sectors"]).supported_sectors(), []) or []
    return tuple(str(x) for x in s[:limit])


def _hid(statement):
    return _safe(lambda: __import__("jarvis.research_workflow.models",
                                    fromlist=["hypothesis_id"]).hypothesis_id(statement),
                 "HYP:" + str(abs(hash(statement)) % (10 ** 10)))


def _leaf(root, dim, value, idx):
    """차원=값 리프 후보(결정적 스코어). 인덱스로 소폭 감쇠 → 결정적 순위."""
    stmt = f"{root} | {dim}={value}"
    weight = _DIM_WEIGHT.get(dim, 0.5)
    score = round(weight * (1.0 - 0.05 * idx), 4)
    return {"hypothesis_id": _hid(stmt), "statement": stmt, "dimension": dim, "value": value,
            "score": score, "requires_human_review": True, "is_advisory": True, "is_decision": False}


def _dims(root):
    """탐색 차원 목록(섹터는 sector_intelligence 재사용)."""
    dims = dict(_DIM_VALUES)
    secs = _sectors()
    if secs:
        dims["sector"] = secs
    return dims


def _merge_duplicates(leaves):
    """ResearchSimilarity 로 근접 중복 병합(높은 스코어 유지). 기존 엔진 재사용."""
    sim = _safe(lambda: __import__("jarvis.research_workflow.research_similarity",
                                   fromlist=["ResearchSimilarity"]).ResearchSimilarity())
    kept, merged = [], 0
    for leaf in sorted(leaves, key=lambda x: (-x["score"], x["hypothesis_id"])):
        dup = False
        for k in kept:
            if leaf["statement"] == k["statement"]:
                dup = True
                break
            if sim is not None:
                s = _safe(lambda: sim.compare(leaf["statement"], k["statement"])["similarity_score"], 0.0)
                if s >= _MERGE_THRESHOLD:
                    dup = True
                    break
        if dup:
            merged += 1
        else:
            kept.append(leaf)
    return kept, merged


def build_search_space(hypothesis, *, top_k: int = 12) -> dict:
    """가설 → 연구 트리(차원별 브랜치) → 스코어·프루닝·중복병합 → 최고가치 후보 표면화. 결정적·읽기전용."""
    root = _root_statement(hypothesis)
    dims = _dims(root)

    tree, all_leaves = [], []
    for dim in sorted(dims):
        leaves = [_leaf(root, dim, v, i) for i, v in enumerate(dims[dim])]
        # 브랜치 내 프루닝
        kept = [l for l in leaves if l["score"] >= _PRUNE_THRESHOLD]
        pruned = len(leaves) - len(kept)
        tree.append({"dimension": dim, "weight": _DIM_WEIGHT.get(dim, 0.5),
                     "branches": kept, "pruned": pruned})
        all_leaves += kept

    # 트리 전역 중복 병합 + 최종 순위
    surfaced, merged = _merge_duplicates(all_leaves)
    surfaced.sort(key=lambda x: (-x["score"], x["hypothesis_id"]))
    surfaced = surfaced[:top_k]

    return {"root_hypothesis": root, "root_id": _hid(root),
            "dimensions": sorted(dims), "tree": tree,
            "generated": sum(len(dims[d]) for d in dims),
            "surfaced_count": len(surfaced), "merged_duplicates": merged,
            "highest_value_candidates": surfaced,
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Autonomous Research Search(읽기전용) — 가설→탐색트리→스코어·프루닝·중복병합→표면화. "
                     "구조화된 전개(제안). 연구 자동 실행 없음, 새 엔진/원장 없음. 사람이 모든 결정.")}
