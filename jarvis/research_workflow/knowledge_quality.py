"""Knowledge Quality Monitor (P139) — 지식의 품질을 감시한다. **읽기 전용, 새 저장소 없음.**

점검: duplicate lessons·outdated knowledge·contradictions·missing evidence. 산출: Knowledge Health Score.
**재사용**: rmi_lessons·conflict_detection(P135)·knowledge_recap. 새 저장소 없음 — 기존 메모리 감시.

원칙(문서 §Constitution, §P139): 통합·조율만. 결정적. 거래·집행 없음.
"""
from __future__ import annotations

import re


def _read(mod, fn):
    try:
        m = __import__(mod, fromlist=[fn])
        return list(getattr(m, fn)() or [])
    except Exception:  # noqa: BLE001
        return []


def _sig(text: str) -> str:
    """교훈 텍스트 → 중복 판정 시그니처(정규화 토큰셋 해시)."""
    toks = sorted(set(re.findall(r"[a-z0-9]+", (text or "").lower())))
    return " ".join(toks[:20])


def build_knowledge_health() -> dict:
    """Knowledge Health Score(읽기전용) — 중복·노후·모순·근거누락 점검. 결정적."""
    lessons = _read("jarvis.research_memory_intelligence.ledger", "read_lessons")
    n = len(lessons)

    # 1) 중복 교훈 — 시그니처 충돌
    seen: dict = {}
    duplicates = 0
    for lo in lessons:
        s = _sig(lo.get("lesson", ""))
        if s in seen:
            duplicates += 1
        else:
            seen[s] = lo.get("lesson_id")

    # 2) 노후 지식 — created_at 이 오래된 비율(타임스탬프 있으면). 결정적 근사: 빈 created_at=미상
    dated = [lo for lo in lessons if lo.get("created_at")]
    outdated = sum(1 for lo in dated if str(lo.get("created_at", ""))[:4].isdigit()
                   and str(lo.get("created_at"))[:4] < "2025")

    # 3) 모순 — conflict_detection 재사용
    conflicts = _safe(lambda: __import__("jarvis.research_workflow.conflict_detection",
                                         fromlist=["detect_conflicts"]).detect_conflicts(),
                      {"count": 0})
    n_conflicts = conflicts.get("count", 0)

    # 4) 근거 누락 — evidence 가 비어있는 교훈
    missing_evidence = sum(1 for lo in lessons if not (lo.get("evidence") or {}))

    # Knowledge Health Score(0..100) — 이슈가 많을수록 감점
    if n == 0:
        score, grade = 0.0, "EMPTY"
    else:
        penalty = (duplicates / n) * 30 + (outdated / max(n, 1)) * 20 + \
                  min(n_conflicts / max(n, 1), 1.0) * 30 + (missing_evidence / n) * 20
        score = round(max(0.0, 100.0 - penalty), 1)
        grade = ("HEALTHY" if score >= 80 else "FAIR" if score >= 60 else "DEGRADED")

    return {"health_score": score, "grade": grade, "total_lessons": n,
            "issues": {"duplicate_lessons": duplicates, "outdated_knowledge": outdated,
                       "contradictions": n_conflicts, "missing_evidence": missing_evidence},
            "checks": ["duplicate_lessons", "outdated_knowledge", "contradictions", "missing_evidence"],
            "is_advisory": True, "is_decision": False,
            "note": ("Knowledge Health(읽기전용) — 중복·노후·모순·근거누락. conflict_detection/rmi_ 재사용. "
                     "새 저장소 없음.")}


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default
