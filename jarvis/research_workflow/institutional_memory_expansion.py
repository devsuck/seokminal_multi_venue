"""Long Term Research Memory Expansion (P157) — 장기 연구 회수를 개선한다. **읽기 전용, 새 메모리 저장 없음.**

**재사용**: rmi_(lessons/successes/failures)·semantic_recall·learning_engine. 추적: research themes·
market cycles·historical periods·successful studies·failed studies. 출력: InstitutionalMemoryReport.
**새 메모리 저장소 없음** — 기존 rmi_ 를 테마/기간별로 재구성(회수 개선).

원칙(문서 §Constitution, §P157): 통합·조율만. 결정적. 거래·집행 없음.
"""
from __future__ import annotations

import re

# 연구 테마 키워드(정적 분류) — 새 저장소 아님, 분류 렌즈
_THEMES = {
    "momentum": ("momentum", "trend", "tsmom", "breakout"),
    "mean_reversion": ("reversion", "mean", "vwap", "pairs"),
    "value": ("value", "quality", "factor", "carry"),
    "volatility": ("vol", "variance", "gamma", "option"),
    "supply_chain": ("supply", "semiconductor", "chip", "tsmc"),
    "macro": ("macro", "rate", "inflation", "regime"),
}


def _read(mod, fn):
    try:
        m = __import__(mod, fromlist=[fn])
        return list(getattr(m, fn)() or [])
    except Exception:  # noqa: BLE001
        return []


def _theme_of(text: str) -> str:
    low = (text or "").lower()
    for theme, kws in _THEMES.items():
        if any(k in low for k in kws):
            return theme
    return "other"


def _period_of(rec: dict) -> str:
    """레코드에서 기간(연도) 추출 — 없으면 'unknown'."""
    text = " ".join(str(v) for v in rec.values())
    m = re.search(r"(19|20)\d{2}", text)
    return m.group(0) if m else "unknown"


def build_institutional_memory() -> dict:
    """InstitutionalMemoryReport(읽기전용) — 테마·사이클·기간·성공/실패 스터디로 재구성. 새 저장소 없음."""
    lessons = _read("jarvis.research_memory_intelligence.ledger", "read_lessons")
    successes = _read("jarvis.research_memory_intelligence.ledger", "read_successes")
    failures = _read("jarvis.research_memory_intelligence.ledger", "read_failures")

    # 테마별 집계
    by_theme: dict = {}
    for coll, kind in ((lessons, "lesson"), (successes, "success"), (failures, "failure")):
        for r in coll:
            text = str(r.get("lesson") or r.get("summary") or r.get("origin", ""))
            th = _theme_of(text)
            slot = by_theme.setdefault(th, {"lessons": 0, "successes": 0, "failures": 0})
            slot[{"lesson": "lessons", "success": "successes", "failure": "failures"}[kind]] += 1

    # 기간별(시장 사이클 근사)
    by_period: dict = {}
    for r in successes + failures:
        p = _period_of(r)
        by_period[p] = by_period.get(p, 0) + 1

    successful_studies = [{"origin": s.get("origin"), "summary": str(s.get("summary", ""))[:120],
                           "theme": _theme_of(str(s.get("summary") or s.get("origin", "")))}
                          for s in successes[:15]]
    failed_studies = [{"origin": f.get("origin"), "summary": str(f.get("summary", ""))[:120],
                       "theme": _theme_of(str(f.get("summary") or f.get("origin", "")))}
                      for f in failures[:15]]

    return {"research_themes": [{"theme": k, **v} for k, v in sorted(by_theme.items())],
            "theme_count": len(by_theme),
            "market_cycles": [{"period": k, "study_count": v} for k, v in sorted(by_period.items())],
            "successful_studies": successful_studies,
            "failed_studies": failed_studies,
            "totals": {"lessons": len(lessons), "successes": len(successes), "failures": len(failures)},
            "report_type": "InstitutionalMemoryReport",
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("InstitutionalMemoryReport(읽기전용) — 테마·사이클·기간·성공/실패 재구성. "
                     "rmi_/semantic_recall/learning_engine 재사용, 새 메모리 저장 없음.")}


def supported_themes() -> list:
    return list(_THEMES)
