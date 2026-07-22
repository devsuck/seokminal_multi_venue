"""Production Monitor (P6.1) — 프로덕션 경계 상태 추적. 트레이딩 지표 없음.

읽기 전용 집계(원장 폴드). 게이트 재실행 안 함(감사 스팸 방지) — 저장된 결정 사용.
"""
from __future__ import annotations

from jarvis.config import AUTONOMY_LEVEL, MIN_LIVE_LEVEL, live_execution_enabled
from jarvis.production.approval import proposal_status, read_approvals, read_proposals
from jarvis.production.gate import read_gate_decisions
from jarvis.production.models import FRESHNESS_HOURS, hours_between


class ProductionMonitor:
    def snapshot(self, now: str) -> dict:
        proposals = read_proposals()
        approvals = read_approvals()
        gate_decisions = read_gate_decisions()

        by_status: dict = {}
        stale = 0
        for p in proposals:
            by_status[proposal_status(p, approvals, now)] = \
                by_status.get(proposal_status(p, approvals, now), 0) + 1
            age = hours_between(p.get("created_at", ""), now)
            if age is not None and age > FRESHNESS_HOURS:
                stale += 1

        blocked_reasons: dict = {}
        risk_warnings = 0
        for d in gate_decisions:
            if d.get("decision") == "BLOCK":
                for fc in d.get("failed_checks", []):
                    key = fc.split(":")[0].split("(")[0]
                    blocked_reasons[key] = blocked_reasons.get(key, 0) + 1
                    if key == "risk_governor":
                        risk_warnings += 1

        health = {
            "autonomy_level": AUTONOMY_LEVEL,
            "min_live_level": MIN_LIVE_LEVEL,
            "live_execution_enabled": live_execution_enabled(),
            "production_boundary": "OPEN" if live_execution_enabled() else "CLOSED",
            "risk_governor": "dry_run (advisory)",
            "status": "OK" if not live_execution_enabled() else "LIVE_ENABLED",
        }
        return {
            "timestamp": now,
            "proposal_count": len(proposals),
            "by_status": by_status,
            "blocked_reasons": blocked_reasons,
            "stale_data": stale,
            "risk_warnings": risk_warnings,
            "gate_decisions_recorded": len(gate_decisions),
            "system_health": health,
        }
