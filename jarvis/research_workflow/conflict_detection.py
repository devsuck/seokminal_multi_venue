"""Knowledge Conflict Detection (P135) — 모순되는 결론을 찾는다. **읽기 전용, 결정적.**

예: Study A(모멘텀 작동) vs Study B(모멘텀 실패). Conflict Report {period·market regime·method difference·
possible explanation}. **재사용**: rmi_successes vs rmi_failures(같은 origin)·recall·perspectives(conflicting).
새 저장소 없음.

원칙(문서 §Constitution, §P135): 통합·조율만. 결정적. 거래·집행 없음.
"""
from __future__ import annotations

import re


def _read(mod, fn):
    try:
        m = __import__(mod, fromlist=[fn])
        return list(getattr(m, fn)() or [])
    except Exception:  # noqa: BLE001
        return []


def _norm(origin: str) -> str:
    """origin → 정규화 키(전략/주제 매칭용)."""
    return re.sub(r"[^a-z0-9]", "", (origin or "").lower())


def _extract(text: str, key: str) -> str:
    """텍스트에서 period/regime/method 힌트 추출(결정적, 없으면 '')."""
    low = (text or "").lower()
    if key == "regime":
        for r in ("high_vol", "low_vol", "bull", "bear", "risk_on", "risk_off", "trending", "ranging"):
            if r in low:
                return r
    if key == "period":
        m = re.search(r"(19|20)\d{2}(\s*[-~]\s*(19|20)?\d{2})?", text or "")
        return m.group(0) if m else ""
    if key == "method":
        for meth in ("walk_forward", "in_sample", "out_of_sample", "paper", "backtest", "cross_val"):
            if meth in low:
                return meth
    return ""


def detect_conflicts(*, topic: str = "", limit: int = 20) -> dict:
    """지식 모순 탐지(읽기전용) — 같은 origin 의 success vs failure → Conflict Report. 결정적."""
    t = _norm(topic)
    successes = _read("jarvis.research_memory_intelligence.ledger", "read_successes")
    failures = _read("jarvis.research_memory_intelligence.ledger", "read_failures")

    succ_by: dict = {}
    for s in successes:
        k = _norm(s.get("origin", ""))
        if k and (not t or t in k):
            succ_by.setdefault(k, []).append(s)
    conflicts = []
    for f in failures:
        k = _norm(f.get("origin", ""))
        if not k or (t and t not in k) or k not in succ_by:
            continue
        for s in succ_by[k][:2]:
            s_text = str(s.get("summary", ""))
            f_text = str(f.get("summary", ""))
            conflicts.append({
                "topic": f.get("origin"),
                "study_a": {"conclusion": "WORKED", "ref": s.get("success_id"), "summary": s_text[:140]},
                "study_b": {"conclusion": "FAILED", "ref": f.get("failure_id"), "summary": f_text[:140]},
                "period": _extract(s_text, "period") or _extract(f_text, "period"),
                "market_regime": {"a": _extract(s_text, "regime"), "b": _extract(f_text, "regime")},
                "method_difference": {"a": _extract(s_text, "method"), "b": _extract(f_text, "method")},
                "possible_explanation": _explain(s_text, f_text),
                "requires_human_review": True})
            if len(conflicts) >= limit:
                break
        if len(conflicts) >= limit:
            break

    return {"topic": topic, "conflicts": conflicts, "count": len(conflicts),
            "checked": {"successes": len(successes), "failures": len(failures)},
            "is_advisory": True, "is_decision": False,
            "note": ("Conflict Report(읽기전용) — 같은 주제의 success vs failure 모순. period·regime·method·"
                     "설명 포함. rmi_ 재사용, 새 저장소 없음. 사람 검토 필요.")}


def _explain(a_text: str, b_text: str) -> str:
    """모순의 가능한 설명(결정적) — 레짐/방법 차이 우선."""
    ra, rb = _extract(a_text, "regime"), _extract(b_text, "regime")
    ma, mb = _extract(a_text, "method"), _extract(b_text, "method")
    if ra and rb and ra != rb:
        return f"레짐 차이({ra} vs {rb}) — 조건부 결론일 가능성"
    if ma and mb and ma != mb:
        return f"방법 차이({ma} vs {mb}) — 검증 엄밀성/기간 차이"
    return "기간/표본/비용 가정 차이 가능 — 사람 검토로 조건 확인 필요"
