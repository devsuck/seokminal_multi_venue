"""Institutional Research Planning (P177) — 일/주/월 아젠다 + 분기 로드맵을 생성한다. **계획만, 실행 없음.**

기존 research_scheduler(P141, daily/weekly/monthly 사이클)를 재사용하고 **분기 로드맵**을 추가한다.
계획 입력(모두 기존 모듈 재사용): continuous_queue(P173, 백로그)·experiment_prioritization(P174, 다음 실험)·
knowledge_graph(커버리지·갭)·research_ingestion(최근 실패/성공)·regime(현 레짐).

원칙(문서 §Constitution, §P177): 통합·조율만 · 결정적 · 계획만 · 자문 전용 · 거래·집행 없음 · 사람 결정.
"""
from __future__ import annotations

_QUARTERLY_THEMES = (
    "지식 갭 축소 — 커버리지 낮은 영역 우선 연구",
    "반복 실패 카테고리 근절 — 실패지능 기반 재설계",
    "검증 품질 상향 — INCOMPLETE 실험의 완전 검증",
    "레짐 강건성 — 현 레짐 밖 재현성 확인",
)


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _cycle(cycle_type):
    return _safe(lambda: __import__("jarvis.research_workflow.research_scheduler",
                                    fromlist=["plan_cycle"]).plan_cycle(cycle_type),
                {"tasks": [], "cadence": ""}) or {}


def _backlog(topic, limit):
    return _safe(lambda: __import__("jarvis.research_workflow.continuous_queue",
                                    fromlist=["build_continuous_queue"]
                                    ).build_continuous_queue(topic=topic).get("backlog", [])[:limit],
                []) or []


def _next_experiments(topic, limit):
    return _safe(lambda: __import__("jarvis.research_workflow.experiment_prioritization",
                                    fromlist=["prioritize_experiments"]
                                    ).prioritize_experiments(topic=topic, limit=limit
                                                             ).get("recommendations", []),
                []) or []


def _regime_label():
    r = _safe(lambda: __import__("jarvis.research_workflow.regime",
                                 fromlist=["detect_regime"]).detect_regime(), {}) or {}
    return str(r.get("regime") or r.get("label") or "UNKNOWN")


def _recent_outcomes():
    s = _safe(lambda: __import__("jarvis.research_ingestion.engine",
                                 fromlist=["ResearchIngestionEngine"]
                                 ).ResearchIngestionEngine().summary(), None)
    return (getattr(s, "by_outcome", None) or {}) if s else {}


def _agenda(items, key):
    return [{"item": (it.get("statement") or it.get("task") or str(it))[:100], "source": key}
            for it in items]


def build_research_plan(*, topic: str = "", horizon: str = "all") -> dict:
    """일/주/월 아젠다 + 분기 로드맵(계획, 자문). 결정적·읽기전용. 실행 없음.

    horizon: "all" | "daily" | "weekly" | "monthly" | "quarterly".
    """
    regime = _regime_label()
    outcomes = _recent_outcomes()
    backlog = _backlog(topic, limit=8)
    next_exp = _next_experiments(topic, limit=5)

    plans = {}
    if horizon in ("all", "daily"):
        c = _cycle("daily")
        plans["daily"] = {"cadence": c.get("cadence"),
                          "agenda": _agenda(next_exp[:3], "prioritized_experiment")
                                    + _agenda([{"task": t.get("task")} for t in c.get("tasks", [])],
                                              "scheduler_task")}
    if horizon in ("all", "weekly"):
        c = _cycle("weekly")
        plans["weekly"] = {"cadence": c.get("cadence"),
                           "agenda": _agenda(backlog[:5], "backlog")
                                     + _agenda([{"task": t.get("task")} for t in c.get("tasks", [])],
                                               "scheduler_task")}
    if horizon in ("all", "monthly"):
        c = _cycle("monthly")
        plans["monthly"] = {"cadence": c.get("cadence"),
                            "agenda": _agenda([{"task": t.get("task")} for t in c.get("tasks", [])],
                                              "scheduler_task")
                                      + ([{"item": "반복 실패 카테고리 리뷰", "source": "failure_intel"}]
                                         if outcomes.get("FAILURE") else [])}
    if horizon in ("all", "quarterly"):
        themes = list(_QUARTERLY_THEMES)
        plans["quarterly"] = {"cadence": "0 8 1 */3 *",
                              "roadmap": [{"theme": t, "quarter_slot": i + 1}
                                          for i, t in enumerate(themes)]}

    return {"topic": topic, "current_regime": regime,
            "planning_inputs": {"backlog_size": len(backlog), "next_experiments": len(next_exp),
                                "recent_outcomes": outcomes},
            "plans": plans,
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Institutional Research Planning(읽기전용) — 일/주/월 아젠다 + 분기 로드맵. "
                     "계획만(실행 없음), 기존 스케줄러 재사용, 새 원장 없음. 사람이 모든 결정.")}
