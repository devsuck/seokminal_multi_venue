"""Research Operation Scheduler (P141) — 반복 연구 사이클을 관리한다. **자동 투자 행위 없음.**

지원: Daily Research Cycle·Weekly Review Cycle·Monthly Strategy Review. 흐름: Schedule → Research Director →
Agent Assignment → Research Tasks → Review Queue. **재사용**: research_director(P122)·research_feed(P117)·
ops_events(P107). 출력: ResearchOperationPlan {cycle_type, tasks, assigned_agents, status, human_review_required}.

주의: 실제 주기 실행(백그라운드 루프)은 없다 — 결정적 계획 생성기이며 주기는 외부(cron/사람)가 호출.
원칙(문서 §Constitution, §P141): 통합·조율만. 결정적. 거래·집행 없음. 사람 결정.
"""
from __future__ import annotations

# 사이클 정의(결정적) — cadence + 기본 태스크 셋
CYCLES = {
    "daily": {"cadence": "0 8 * * 1-5", "tasks": ["research_ledger_sync", "morning_briefing",
                                                  "company_monitor", "opportunity_scan",
                                                  "review_queue_refresh"]},
    "weekly": {"cadence": "0 8 * * 1", "tasks": ["strategy_health", "weekly_letter",
                                                 "knowledge_health", "conflict_scan"]},
    "monthly": {"cadence": "0 8 1 * *", "tasks": ["strategy_review", "agent_performance",
                                                  "research_accuracy", "memory_audit"]},
}
STATUS = ("PLANNED", "AGENTS_ASSIGNED", "IN_REVIEW", "ARCHIVED")


class ResearchScheduler:
    """연구 운영 스케줄러 — 사이클 → 연구 계획(태스크·배정·검토큐). RESEARCH_ONLY. 실행하지 않는다."""

    def plan_cycle(self, cycle_type: str, *, objective: str = "", assistant=None) -> dict:
        """사이클 유형 → ResearchOperationPlan(태스크·배정·상태·검토큐). 결정적·읽기전용."""
        ct = (cycle_type or "daily").lower()
        cyc = CYCLES.get(ct, CYCLES["daily"])
        obj = (objective or f"{ct} research cycle").strip()

        # Research Director → 전문가 배정(워크플로 선택)
        assigned = []
        try:
            from jarvis.research_workflow.research_director import ResearchDirector
            plan = ResearchDirector(assistant=assistant).plan(obj)
            assigned = plan.get("assigned_agents", [])
        except Exception:  # noqa: BLE001
            pass

        tasks = [{"task": t, "cycle": ct, "status": "PLANNED"} for t in cyc["tasks"]]
        return {"cycle_type": ct, "cadence": cyc["cadence"], "objective": obj,
                "tasks": tasks, "assigned_agents": assigned,
                "status": "AGENTS_ASSIGNED" if assigned else "PLANNED",
                "human_review_required": True, "auto_execution": False,
                "review_queue": [{"task": t["task"], "requires_human_review": True} for t in tasks],
                "is_advisory": True, "is_decision": False,
                "note": ("ResearchOperationPlan(읽기전용) — Schedule→Director→Assignment→Tasks→Review Queue. "
                         "주기는 메타(외부 호출). 자동 투자 행위 없음, 새 원장 없음.")}

    def schedule(self) -> dict:
        """전체 사이클 스케줄 메타(읽기전용) — daily/weekly/monthly cadence."""
        return {"cycles": {k: {"cadence": v["cadence"], "tasks": v["tasks"]} for k, v in CYCLES.items()},
                "status_flow": list(STATUS), "auto_execution": False,
                "is_advisory": True, "is_decision": False,
                "note": "연구 운영 스케줄(읽기전용) — 실제 주기 실행은 외부(cron/사람). 자동 투자 없음."}


def plan_cycle(cycle_type: str, *, objective: str = "", assistant=None) -> dict:
    """모듈 진입점 — ResearchScheduler.plan_cycle 래퍼."""
    return ResearchScheduler().plan_cycle(cycle_type, objective=objective, assistant=assistant)
