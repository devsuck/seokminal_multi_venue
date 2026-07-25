"""Executive Research Cockpit (P85) — 최종 홈 화면 데이터. **읽기 전용, 새 저장소 없음.**

기존 모든 표면을 하나로 합친다: 오늘의 연구·현재 루프·상위 기회·최상위 리스크·포트폴리오 노출·연구 건강·
지식 성장·페이퍼 성과·Decision Memo·타임라인·지식 그래프·연구 큐·사람 검토 큐·최근 세션·빠른 재개/회상.
모두 기존 엔진/원장 조율 — 새 로직 없음.

원칙(문서 §Constitution, §P85): 통합·시각화만. 결정적. 거래·집행 없음. 사람 결정.
"""
from __future__ import annotations


def _safe(fn, default):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def build_cockpit() -> dict:
    """Executive cockpit 집계(읽기 전용). 기존 orchestration 모듈 재사용."""
    from jarvis.research_assistant.engine import ResearchAssistantEngine
    asst = ResearchAssistantEngine()

    research = _safe(lambda: {
        "total_records": asst.daily_summary().total_records,
        "experiment_runs": asst.experiment_summary().run_count,
        "active_sources": asst.daily_summary().active_sources}, {})

    def _loop():
        from jarvis.research_workflow import ledger as wl
        from jarvis.research_workflow.autonomous_loop import AutonomousResearchLoop
        loop = AutonomousResearchLoop()
        ids = []
        seen = set()
        for e in wl.read_loops():
            lid = e.get("loop_id")
            if lid and lid not in seen:
                seen.add(lid)
                ids.append(lid)
        if not ids:
            return {}
        st = loop.state(ids[-1])
        return {"loop_id": st.loop_id, "idea": st.idea, "current_stage": st.current_stage,
                "completed": st.completed_stages, "blocked_stage": st.blocked_stage,
                "requires_human_checkpoint": st.requires_human_checkpoint}
    current_loop = _safe(_loop, {})

    opportunities = _safe(lambda: [
        {"name": p.name, "kind": p.kind, "confidence": p.confidence, "expected_value": p.expected_value}
        for p in __import__("jarvis.research_assistant.research_queue",
                            fromlist=["ResearchQueueEngine"]).ResearchQueueEngine()
        .generate(limit=5).proposals], [])

    risks = _safe(lambda: {
        "total_failures": asst.failure_intelligence().total_failures,
        "top_category": asst.failure_intelligence().top_category,
        "by_category": asst.failure_intelligence().by_category}, {})

    exposure = _safe(lambda: (lambda pos, cap: {
        "capital": cap, "gross_exposure": round(sum(abs(float(p.get("market_value", 0.0))) for p in pos), 2),
        "n_positions": len(pos)})(
        list(__import__("jarvis.paper_execution.ledger", fromlist=["current_positions"])
             .current_positions().values()),
        __import__("jarvis.paper_execution.models", fromlist=["PAPER_CAPITAL"]).PAPER_CAPITAL), {})

    from jarvis.research_workflow.health_monitor import build_health
    from jarvis.research_workflow.timeline import build_timeline
    from jarvis.research_workflow.knowledge_graph import build_knowledge_graph
    from jarvis.research_workflow.continuous_learning import learning_status
    health = _safe(build_health, {})
    timeline = _safe(lambda: build_timeline(limit=12), {"entries": []})
    graph = _safe(lambda: build_knowledge_graph(limit=60), {"node_count": 0, "edge_count": 0})
    learning = _safe(learning_status, {})

    def _human_queue():
        from jarvis.research_workflow import ledger as wl
        runs = wl.read_runs()
        ids = {e.get("run_id") for e in runs}
        out = []
        for rid in ids:
            evs = [e for e in runs if e.get("run_id") == rid]
            dec = any(e.get("stage") == "DECISION" and e.get("status") == "COMPLETED" for e in evs)
            hum = any(e.get("stage") == "HUMAN_DECISION" and e.get("status") == "COMPLETED" for e in evs)
            if dec and not hum:
                out.append({"run_id": rid, "request": evs[0].get("request", "")})
        return out
    human_review_queue = _safe(_human_queue, [])

    sessions = _safe(lambda: __import__("jarvis.research_workflow.session_manager",
                                        fromlist=["ResearchSessionManager"])
                     .ResearchSessionManager().list_sessions()[:6], [])

    return {
        "research": research, "current_loop": current_loop, "top_opportunities": opportunities,
        "highest_risks": risks, "portfolio_exposure": exposure, "research_health": health,
        "knowledge_growth": {"total": learning.get("total", 0), "channels": learning.get("channels", {}),
                             "graph_nodes": graph.get("node_count", 0), "graph_edges": graph.get("edge_count", 0)},
        "timeline": timeline.get("entries", []),
        "knowledge_graph": {"node_count": graph.get("node_count", 0), "edge_count": graph.get("edge_count", 0),
                            "node_types": graph.get("node_types", {})},
        "research_queue": opportunities,
        "human_review_queue": human_review_queue,
        "recent_sessions": sessions,
        "quick_resume": [{"session_id": s.get("session_id"), "goal": s.get("goal"), "state": s.get("state")}
                         for s in sessions if s.get("state") in ("PAUSED", "ACTIVE")][:4],
        "health_score": health.get("overall_health_score", 0),
        "is_advisory": True, "is_decision": False,
        "disclaimer": ("Executive Research Cockpit — READ ONLY. 모든 기존 역량의 통합 뷰. "
                       "분석·추천·요약만, 자동 거래·집행·자본배분·배포 승인 없음. 사람이 모든 결정을 한다.")}
