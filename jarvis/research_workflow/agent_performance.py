"""Agent Effectiveness Analysis (P148) — 에이전트 효과성을 측정한다. **읽기 전용, 자율 자기수정 아님.**

측정: Research Director(task quality)·Analyst(evidence quality)·Critic(issue detection)·Writer(report usefulness).
출력: Agent Performance Report. 목적: 연구 프로세스 개선(사람이 판단) — **자율 자기수정 아님.** 새 저장소 없음.
**재사용**: multi_agent_workflow(P128) 산출을 결정적으로 채점.

원칙(문서 §Constitution, §P148): 통합·조율만. 결정적. 거래·집행 없음. 사람 결정.
"""
from __future__ import annotations


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _score(x, lo, hi) -> float:
    return round(max(0.0, min(1.0, (x - lo) / (hi - lo) if hi > lo else 0.0)), 3)


class AgentPerformanceMonitor:
    """에이전트 성과 모니터 — 디렉터/분석/비평/작성 품질 채점. RESEARCH_ONLY. 자율 자기수정 아님."""

    def report(self, *, workflow: dict | None = None, objective: str = "") -> dict:
        """다중에이전트 산출 → Agent Performance Report(결정적 채점). 읽기전용."""
        wf = workflow
        if wf is None:
            wf = _safe(lambda: __import__("jarvis.research_workflow.multi_agent_workflow",
                                          fromlist=["run"]).run(objective or "momentum research"), {})
        director = wf.get("director_plan", {}) or {}
        memos = wf.get("specialist_memos", {}) or {}
        review = wf.get("review", {}) or {}
        report = wf.get("report", {}) or {}

        # Director: task quality — 가설 + 배정 + 검증계획 충실도
        d_quality = _score(len(director.get("assigned_agents", [])) +
                           (1 if director.get("hypothesis") else 0) +
                           min(len(director.get("validation_plan", [])), 3), 0, 7)
        # Analyst: evidence quality — 메모의 근거 충실도
        analyst_evidence = sum(len((m or {}).get("relevant_events", []) or (m or {}).get("fundamentals", []))
                               for m in memos.values() if isinstance(m, dict))
        a_quality = _score(analyst_evidence, 0, 8)
        # Critic: issue detection — 비판 차원 수 + 판정
        n_crit = len(review.get("critique", {}).get("critiques", []))
        c_quality = _score(n_crit + (2 if review.get("verdict") in ("WARN", "BLOCK") else 0), 0, 10)
        # Writer: report usefulness — 섹션 완비 + 신뢰도 + 한계
        secs = len(report.get("report", {}))
        w_quality = _score(secs + (1 if report.get("confidence") else 0) +
                           min(len(report.get("limitations", [])), 3), 0, 11)

        agents = {
            "ResearchDirector": {"metric": "task_quality", "score": d_quality},
            "AnalystAgents": {"metric": "evidence_quality", "score": a_quality},
            "ResearchReviewer": {"metric": "issue_detection", "score": c_quality},
            "ResearchWriter": {"metric": "report_usefulness", "score": w_quality},
        }
        overall = round(sum(a["score"] for a in agents.values()) / len(agents), 3)
        improvements = [f"{k}: {a['metric']} 낮음 — 프로세스 개선 검토(사람)"
                        for k, a in agents.items() if a["score"] < 0.5]
        return {"objective": objective or wf.get("objective", ""),
                "agents": agents, "overall_effectiveness": overall,
                "improvement_suggestions": improvements,
                "autonomous_self_modification": False,
                "report_type": "Agent Performance Report",
                "requires_human_review": True, "is_advisory": True, "is_decision": False,
                "note": ("Agent Performance Report(읽기전용) — 디렉터/분석/비평/작성 품질. 프로세스 개선용(사람 판단). "
                         "자율 자기수정 아님, 새 저장소 없음.")}


def report(*, workflow=None, objective="") -> dict:
    """모듈 진입점 — AgentPerformanceMonitor.report 래퍼."""
    return AgentPerformanceMonitor().report(workflow=workflow, objective=objective)
