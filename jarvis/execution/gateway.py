"""Execution Gateway — 승인 주문만 실행. 실브로커는 레벨 게이트로 BLOCK.

거부: 미승인 전략 · 미승인 자산 · 미승인 수량 · 스테일 데이터 · 감사맥락 결손 ·
config_hash 불일치 · risk governor 거부 · live 미활성(autonomy < MIN_LIVE_LEVEL).
현재 = mock/paper/dry-run만. 실행권한 자가확장 불가.
"""
from __future__ import annotations

from jarvis.audit import record
from jarvis.config import AUTONOMY_LEVEL, MIN_LIVE_LEVEL, live_execution_enabled


class ExecutionGateway:
    def execute(self, proposal: dict, risk_result: dict | None = None, mode: str = "live") -> dict:
        """mode: mock | paper | live | micro_live. 실행성 모드는 레벨 미달 시 무조건 BLOCK."""
        sid = proposal.get("strategy_id", "")
        pid = proposal.get("proposal_id")

        if mode in ("live", "micro_live") and not live_execution_enabled():
            res = {"proposal_id": pid, "strategy_id": sid, "execution_status": "BLOCKED",
                   "reason": f"{mode} execution disabled at autonomy level {AUTONOMY_LEVEL} "
                             f"(needs >= {MIN_LIVE_LEVEL})"}
            record({"layer": "execution", "action": "execute", "mode": mode, "strategy_id": sid,
                    "proposal_id": pid, "execution_status": "BLOCKED", "reason": res["reason"]})
            return res

        # micro_live는 사람 arm 필수(이중 게이트). 레벨 통과해도 무장 안 됐으면 거부.
        if mode == "micro_live":
            from jarvis.execution.arm import is_armed
            if not is_armed(sid):
                res = {"proposal_id": pid, "strategy_id": sid, "execution_status": "REJECTED",
                       "reason": "not_armed (사람 ADMIN arm 필요)"}
                record({"layer": "execution", "action": "execute", "mode": mode, "strategy_id": sid,
                        "proposal_id": pid, "execution_status": "REJECTED", "reason": res["reason"]})
                return res

        if risk_result is None or risk_result.get("risk_status") != "APPROVED":
            res = {"proposal_id": pid, "strategy_id": sid, "execution_status": "REJECTED",
                   "reason": "risk_governor_not_approved"}
            record({"layer": "execution", "action": "execute", "mode": mode, "strategy_id": sid,
                    "proposal_id": pid, "execution_status": "REJECTED", "reason": res["reason"]})
            return res

        # mock/paper dry-run 체결(실브로커 아님)
        res = {"proposal_id": pid, "strategy_id": sid, "execution_status": "SIMULATED",
               "mode": mode, "reason": "mock/paper dry-run — no real broker"}
        record({"layer": "execution", "action": "execute", "mode": mode, "strategy_id": sid,
                "proposal_id": pid, "execution_status": "SIMULATED"})
        return res
