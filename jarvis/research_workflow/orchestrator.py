"""Workflow Orchestrator (P64) — 기존 연구 컴포넌트를 **조율**한다(새 지능 없음). **거래·집행 없음.**

파이프라인: Request → Queue → Recall → Council → Design → Backtest → Validation → Portfolio →
Risk → Paper → Decision → Human Decision. 각 단계는 **기존 엔진을 호출**하거나(읽기 전용), 외부 입력이 필요한
단계(Design/Backtest/Paper)는 컨텍스트에 결과가 없으면 BLOCKED(부분 완료) — 오케스트레이터는 이를 실행하지 않는다.
단계 이벤트는 append-only 해시체인(rwf_runs)에 기록(--commit). resume·cancel·retry·부분완료·결정적 실행로그 지원.
**Human Decision 은 사람만** — 엔진은 승인하지 않는다.
"""
from __future__ import annotations

from jarvis.research_workflow import ledger
from jarvis.research_workflow import models as M
from jarvis.research_workflow.models import (
    GENESIS,
    STAGES,
    ST_BLOCKED,
    ST_CANCELLED,
    ST_COMPLETED,
    ST_PENDING,
    ST_SKIPPED,
    StageEvent,
    WorkflowState,
    content_digest,
    content_hash,
    input_digest,
)


class WorkflowCancelledError(Exception):
    """취소된 워크플로에 대한 재개/진행 시도."""


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class WorkflowOrchestrator:
    """연구 워크플로 오케스트레이터 — 기존 서브시스템 조율. 결정/집행 권한 없음."""

    def __init__(self, assistant=None, reader=None) -> None:
        self._assistant = assistant
        self._reader = reader

    def _asst(self):
        if self._assistant is None:
            from jarvis.research_assistant.engine import ResearchAssistantEngine
            self._assistant = ResearchAssistantEngine(self._reader)
        return self._assistant

    def _topic(self, request, context) -> str:
        if context and context.get("topic"):
            return str(context["topic"])
        from jarvis.research_assistant.models import extract_topic
        return extract_topic(request) or str(request or "").strip()

    # ── 이벤트 기록(append-only 해시체인). collected 에 인메모리 누적(드라이런 지원) ──
    def _emit(self, collected, run_id, request, stage, status, from_stage, output, note,
              now, commit) -> dict:
        seq = len(collected)
        eid = M.stage_event_id(run_id, stage, seq)
        rec = StageEvent(
            event_id=eid, run_id=run_id, request=str(request), stage=stage, status=status,
            from_stage=from_stage, output_digest=content_digest(output or {}), note=note,
            occurred_at=now, input_hash=input_digest(run_id, stage, seq)).to_dict()
        prev = collected[-1]["record_hash"] if collected else GENESIS
        sealed = _seal(rec, prev)
        if commit:
            ledger.append_run(sealed)
        collected.append(sealed)
        return sealed

    # ── 단계 핸들러: 기존 엔진 호출 / 외부입력 요구 ──
    def _run_stage(self, stage, request, context) -> tuple:
        """(status, output_summary, note) — 결정적. 외부 입력 없으면 BLOCKED(조작 안 함)."""
        ctx = context or {}
        topic = self._topic(request, ctx)
        asst = self._asst()
        if stage == M.S_QUEUE:
            from jarvis.research_assistant.research_queue import ResearchQueueEngine
            q = ResearchQueueEngine(assistant=asst).generate(
                regime=ctx.get("regime"), events=ctx.get("events"), limit=5)
            return ST_COMPLETED, {"proposals": q.proposal_count}, f"{q.proposal_count} proposals"
        if stage == M.S_RECALL:
            r = asst.recall(topic)
            return ST_COMPLETED, {"hits": r.total_hits, "tried": r.tried_before}, r.headline
        if stage == M.S_COUNCIL:
            from jarvis.research_assistant.council import ResearchCouncilEngine
            memo = ResearchCouncilEngine(assistant=asst).deliberate(topic)
            return ST_COMPLETED, {"recommendation": memo.recommendation,
                                  "conflicts": len(memo.conflicts)}, memo.recommendation
        if stage == M.S_DESIGN:
            if ctx.get("design") or ctx.get("strategy_spec"):
                return ST_COMPLETED, {"design": True}, "design provided"
            return ST_BLOCKED, {}, "awaiting human strategy design (external input)"
        if stage == M.S_BACKTEST:
            if ctx.get("backtest"):
                return ST_COMPLETED, {"backtest": True}, "backtest result provided"
            return ST_BLOCKED, {}, "awaiting backtest result (deterministic harness, not executed here)"
        if stage == M.S_VALIDATION:
            bt = ctx.get("backtest")
            if not bt:
                return ST_BLOCKED, {}, "no backtest to validate"
            from jarvis.research_ingestion.models import validate_backtest
            v = validate_backtest(bt)
            return ST_COMPLETED, {"validation_complete": v["validation_complete"],
                                  "missing": v["missing_validations"]}, \
                ("validation complete" if v["validation_complete"]
                 else f"INCOMPLETE: missing {len(v['missing_validations'])}")
        if stage == M.S_PORTFOLIO:
            if ctx.get("new_strategy") and ctx.get("portfolio"):
                from jarvis.portfolio_research.intelligence import PortfolioIntelligence
                rep = PortfolioIntelligence().exposure_analysis(ctx["new_strategy"], ctx["portfolio"])
                return ST_COMPLETED, {"flags": len(rep.risk_flags),
                                      "correlation": rep.additional_correlation}, rep.verdict
            return ST_SKIPPED, {}, "no portfolio context (skipped)"
        if stage == M.S_RISK:
            from jarvis.research_risk_intelligence.failure_reasoning import StrategyRiskReasoner
            rep = StrategyRiskReasoner().risk_report(
                topic, ctx.get("metrics") or (ctx.get("backtest") or {}).get("metrics"))
            return ST_COMPLETED, {"main_risk": rep.main_risk,
                                  "confidence": rep.confidence}, rep.main_risk_label
        if stage == M.S_PAPER:
            if ctx.get("paper"):
                from jarvis.research_ingestion.paper_feedback import PaperTradingFeedback
                diff = PaperTradingFeedback(assistant=asst).compare(
                    ctx.get("backtest") or {}, ctx["paper"])
                return ST_COMPLETED, {"cause": diff.cause, "severity": diff.severity}, diff.cause
            return ST_BLOCKED, {}, "awaiting paper trading result (paper only; not executed here)"
        if stage == M.S_DECISION:
            from jarvis.research_workflow.decision_support import DecisionSupportEngine
            memo = DecisionSupportEngine(assistant=asst).build_memo(
                request, topic=topic, metrics=ctx.get("metrics"),
                new_strategy=ctx.get("new_strategy"), portfolio=ctx.get("portfolio"),
                strategies=ctx.get("strategies"), backtest=ctx.get("backtest"))
            return ST_COMPLETED, {"recommendation": memo.recommendation,
                                  "confidence": memo.confidence}, "decision package assembled"
        if stage == M.S_HUMAN:
            # 사람 결정 단계 — 엔진은 승인하지 않는다. 사람 기록 대기.
            return ST_PENDING, {}, "requires human decision (record_human_decision)"
        return ST_SKIPPED, {}, "unknown stage"

    # ── 구동 ──
    def _drive(self, collected, run_id, request, context, start_index, now, commit) -> WorkflowState:
        prev = STAGES[start_index - 1] if start_index > 0 else GENESIS
        for i in range(start_index, len(STAGES)):
            stage = STAGES[i]
            status, output, note = self._run_stage(stage, request, context)
            self._emit(collected, run_id, request, stage, status, prev, output, note, now, commit)
            prev = stage
            if status in (ST_BLOCKED, ST_PENDING):
                break
        return self._state_from_events(run_id, collected)

    def start(self, request, *, seed="", now="", commit=False) -> str:
        run_id = M.workflow_id(str(request), seed)
        if not any(e["stage"] == M.S_REQUEST for e in ledger.run_events(run_id)):
            collected = list(ledger.run_events(run_id))
            self._emit(collected, run_id, request, M.S_REQUEST, ST_COMPLETED, GENESIS,
                       {"request": request}, "workflow started", now, commit)
        return run_id

    def run(self, request, context=None, *, seed="", now="", commit=False) -> WorkflowState:
        """워크플로 실행 — REQUEST 이후 단계를 순서대로 조율. BLOCKED/HUMAN 에서 정지(부분완료)."""
        run_id = M.workflow_id(str(request), seed)
        collected = list(ledger.run_events(run_id))
        if any(e.get("status") == ST_CANCELLED for e in collected):
            raise WorkflowCancelledError(run_id)
        if not any(e["stage"] == M.S_REQUEST for e in collected):
            self._emit(collected, run_id, request, M.S_REQUEST, ST_COMPLETED, GENESIS,
                       {"request": request}, "workflow started", now, commit)
        return self._drive(collected, run_id, request, context, 1, now, commit)

    def resume(self, run_id, request, context=None, *, now="", commit=False) -> WorkflowState:
        """마지막 완료 단계 이후부터 재개. BLOCKED 였던 단계는 입력이 생기면 재실행."""
        collected = list(ledger.run_events(run_id))
        if not collected:
            raise ValueError(f"unknown run {run_id}")
        if any(e.get("status") == ST_CANCELLED for e in collected):
            raise WorkflowCancelledError(run_id)
        completed = {e["stage"] for e in collected if e.get("status") == ST_COMPLETED}
        start_index = next((i for i, s in enumerate(STAGES) if s not in completed), len(STAGES))
        if start_index >= len(STAGES):
            return self._state_from_events(run_id, collected)
        return self._drive(collected, run_id, request, context, start_index, now, commit)

    def retry(self, run_id, request, stage, context=None, *, now="", commit=False) -> WorkflowState:
        """특정 단계를 재시도(새 이벤트로 기록). 취소된 워크플로는 불가."""
        collected = list(ledger.run_events(run_id))
        if any(e.get("status") == ST_CANCELLED for e in collected):
            raise WorkflowCancelledError(run_id)
        idx = STAGES.index(stage)
        return self._drive(collected, run_id, request, context, idx, now, commit)

    def cancel(self, run_id, reason="", *, now="", commit=False) -> WorkflowState:
        """워크플로 취소(터미널 이벤트). 이후 run/resume/retry 차단."""
        collected = list(ledger.run_events(run_id))
        request = collected[0].get("request", "") if collected else ""
        self._emit(collected, run_id, request, M.S_HUMAN, ST_CANCELLED, "", {},
                   reason or "cancelled", now, commit)
        return self._state_from_events(run_id, collected)

    def record_human_decision(self, run_id, decision, reviewer, note="", *, now="", commit=False) -> dict:
        """사람 결정 기록(APPROVED/REJECTED/DEFERRED). **reviewer 필수 — 엔진은 승인하지 않는다.**"""
        if not str(reviewer or "").strip():
            raise ValueError("reviewer(사람) 필수 — 엔진은 자동 승인하지 않는다.")
        collected = list(ledger.run_events(run_id))
        request = collected[0].get("request", "") if collected else ""
        dec = str(decision or "").strip().upper()
        rec = self._emit(collected, run_id, request, M.S_HUMAN, ST_COMPLETED, M.S_DECISION,
                         {"decision": dec, "reviewer": reviewer.strip(), "is_human": True},
                         f"human {dec} by {reviewer.strip()}: {note}", now, commit)
        rec = dict(rec)
        rec["decision"] = dec
        rec["is_human"] = True
        return rec

    # ── 상태 폴드(이벤트 → 상태) ──
    def state(self, run_id) -> WorkflowState:
        return self._state_from_events(run_id, ledger.run_events(run_id))

    def _state_from_events(self, run_id, events) -> WorkflowState:
        request = events[0].get("request", "") if events else ""
        completed, log = [], []
        blocked = ""
        cancelled = False
        for e in events:
            log.append({"stage": e["stage"], "status": e["status"], "note": e.get("note", ""),
                        "output_digest": e.get("output_digest", "")})
            if e["status"] == ST_COMPLETED and e["stage"] not in completed:
                completed.append(e["stage"])
            if e["status"] == ST_BLOCKED:
                blocked = e["stage"]
            if e["status"] == ST_CANCELLED:
                cancelled = True
        if blocked in completed:
            blocked = ""
        human_done = any(e["stage"] == M.S_HUMAN and e["status"] == ST_COMPLETED for e in events)
        current = blocked or (STAGES[len(completed)] if len(completed) < len(STAGES) else M.S_HUMAN)
        requires_human = (M.S_DECISION in completed) and not human_done and not cancelled
        return WorkflowState(
            run_id=run_id, request=request, current_stage=current, completed_stages=completed,
            blocked_stage=blocked, cancelled=cancelled, stage_outputs={},
            execution_log=log, requires_human_decision=requires_human)
