"""Research Similarity Engine (P134) — 연구/전략/실험/기업 유사도를 측정한다. **읽기 전용, 결정적.**

비교: research questions·strategies·experiments·companies → similarity score. **기존 메타데이터·피처·관계
사용**(토큰 Jaccard + 공유 피처/관계). **블랙박스 임베딩 불필요.** 전략 비교는 strategy_lab.find_similar 재사용.
새 저장소/모델 없음.

원칙(문서 §Constitution, §P134): 통합·조율만. 결정적. 거래·집행 없음.
"""
from __future__ import annotations

import re

_STOP = {"the", "a", "an", "in", "of", "on", "to", "for", "and", "or", "is", "are", "does", "do",
         "under", "with", "how", "what", "why", "current", "work", "works"}


def _tokens(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in _STOP and len(w) > 1}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return round(len(a & b) / len(a | b), 4)


class ResearchSimilarity:
    """연구 유사도 — 토큰/피처/관계 기반 결정적 스코어. 임베딩 없음. 실행 권한 없음."""

    def compare(self, a, b, *, kind: str = "question") -> dict:
        """두 항목(질문/전략/실험/기업) → 유사도(결정적). a,b: 문자열 또는 dict(features/universe 등)."""
        ta, tb = _text_of(a), _text_of(b)
        tok = _jaccard(_tokens(ta), _tokens(tb))
        # 피처 겹침(dict 인 경우)
        fa, fb = _features(a), _features(b)
        feat = _jaccard(fa, fb) if (fa or fb) else None
        score = round((tok if feat is None else 0.6 * tok + 0.4 * feat), 4)
        return {"kind": kind, "a": ta[:80], "b": tb[:80], "token_similarity": tok,
                "feature_similarity": feat, "similarity_score": score,
                "shared_tokens": sorted(_tokens(ta) & _tokens(tb))[:10],
                "is_advisory": True, "is_decision": False}

    def rank(self, query, candidates, *, kind: str = "question", top_k: int = 5) -> dict:
        """query 대비 후보 유사도 순위(결정적)."""
        scored = [{**self.compare(query, c, kind=kind), "candidate": _text_of(c)[:80]}
                  for c in (candidates or [])]
        scored.sort(key=lambda x: x["similarity_score"], reverse=True)
        return {"query": _text_of(query)[:80], "kind": kind, "ranked": scored[:top_k],
                "count": len(scored), "is_advisory": True, "is_decision": False,
                "note": "연구 유사도 순위(읽기전용) — 메타데이터/피처/관계 기반, 임베딩 없음."}

    def similar_strategies(self, name: str, *, candidates=None) -> dict:
        """전략 유사도 — 기존 strategy_lab.find_similar 재사용(리스크 프로파일/DNA 기반)."""
        try:
            from jarvis.research_workflow.strategy_lab import find_similar
            return find_similar(name, candidates=candidates)
        except Exception as e:  # noqa: BLE001
            return {"strategy": name, "similar": [], "error": str(e),
                    "is_advisory": True, "is_decision": False}


def _text_of(x) -> str:
    if isinstance(x, dict):
        return str(x.get("statement") or x.get("question") or x.get("name") or x.get("company")
                   or x.get("strategy_name") or x.get("text") or "")
    return str(x or "")


def _features(x) -> set:
    if not isinstance(x, dict):
        return set()
    feats = set()
    for key in ("feature_set", "features"):
        for f in (x.get(key) or []):
            feats.add(str(f).lower())
    for key in ("universe", "timeframe", "rebalance", "sector"):
        if x.get(key):
            feats.add(f"{key}:{str(x[key]).lower()}")
    return feats


def compare(a, b, *, kind: str = "question") -> dict:
    """모듈 진입점 — ResearchSimilarity.compare 래퍼."""
    return ResearchSimilarity().compare(a, b, kind=kind)
