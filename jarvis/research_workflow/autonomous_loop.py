"""Autonomous Research Loop (P72) — 결정적 자율 연구 루프. **조율만, 실행/결정/집행 없음.**

Idea → Hypothesis → Experiment Design → Backtest → Validation → Failure Analysis → Lesson →
Updated Hypothesis → Next Experiment. 각 단계는 기존 엔진을 호출한다: HypothesisGenerator(P73)·
ExperimentPlanner(P74)·research_ingestion.validate(검증)·ResearchCritic(P75)·rmi_(교훈)·
ResearchPrioritizer(P76). Backtest 는 **외부 입력**(사람 체크포인트) — 없으면 BLOCKED(실행하지 않음).
이벤트는 append-only 해시체인(rwf_loops)에 페이로드와 함께 기록 → 감사 추적·pause·resume·재개.

원칙(문서 §Constitution, §P72): 새 저장소 없음(rwf_loops 는 루프 상태 전용) · 새 지능 없음 · 결정적 ·
거래·집행·자본배분 없음 · 사람 결정. AI 는 제안·비판·우선순위·학습만 한다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from jarvis.research_workflow import ledger
from jarvis.research_workflow import models as M
from jarvis.research_workflow.models import (
    GENESIS,
    LOOP_STAGES,
    ST_BLOCKED,
    ST_CANCELLED,
    ST_COMPLETED,
    ST_SKIPPED,
    content_digest,
    content_hash,
    input_digest,
)

PAUSED = "PAUSED"


class LoopCancelledError(Exception):
    """취소된 루프에 대한 재개 시도."""


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


@dataclass(frozen=True)
class LoopState:
    loop_id: str
    idea: str
    current_stage: str
    completed_stages: list
    blocked_stage: str
    cancelled: bool
    paused: bool
    artifacts: dict               # hypothesis/spec/critique/validation/lesson/next
    audit_trail: list             # 단계별 이벤트 로그(감사)
    requires_human_checkpoint: bool
    is_advisory: bool = True
    is_decision: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class AutonomousResearchLoop:
    """자율 연구 루프 오케스트레이터. 기존 P73~P76 + 검증/메모리 조율. 결정/집행 권한 없음."""

    def __init__(self, assistant=None, reader=None, memory_engine=None) -> None:
        self._assistant = assistant
        self._reader = reader
        self._mem = memory_engine

    def _asst(self):
        if self._assistant is None:
            from jarvis.research_assistant.engine import ResearchAssistantEngine
            self._assistant = ResearchAssistantEngine(self._reader)
        return self._assistant

    def _memory(self):
        if self._mem is None:
            from jarvis.research_memory_intelligence.engine import ResearchMemoryIntelligenceEngine
            self._mem = ResearchMemoryIntelligenceEngine()
        return self._mem

    # ── 이벤트(페이로드 인라인 + 해시체인) ──
    def _emit(self, collected, loop_id, idea, stage, status, from_stage, payload, note, now, commit) -> dict:
        seq = len(collected)
        rec = {"event_id": M.loop_event_id(loop_id, stage, seq), "loop_id": loop_id,
               "idea": str(idea), "stage": stage, "status": status, "from_stage": from_stage,
               "output_digest": content_digest(payload or {}), "note": note,
               "occurred_at": now, "input_hash": input_digest(loop_id, stage, seq),
               "payload": payload or {}}
        prev = collected[-1]["record_hash"] if collected else GENESIS
        sealed = _seal(rec, prev)
        if commit:
            ledger.append_loop(sealed)
        collected.append(sealed)
        return sealed

    def _artifacts(self, events) -> dict:
        art: dict = {}
        for e in events:
            for k, v in (e.get("payload") or {}).items():
                art[k] = v
        return art

    # ── 단계 핸들러 ──
    def _run_stage(self, stage, idea, context, carry) -> tuple:
        ctx = context or {}
        asst = self._asst()
        if stage == M.L_IDEA:
            return ST_COMPLETED, {"idea": str(idea)}, "idea recorded"

        if stage == M.L_HYPOTHESIS:
            from jarvis.research_workflow.hypothesis_generator import HypothesisGenerator
            from jarvis.research_workflow.research_prioritizer import ResearchPrioritizer
            gen = HypothesisGenerator(assistant=asst, memory_engine=self._mem)
            hyps = gen.generate(topic=idea, regime=ctx.get("regime"),
                                portfolio=ctx.get("portfolio"), events=ctx.get("events"), limit=6)
            if not hyps:
                return ST_BLOCKED, {}, "no hypotheses — seed memory or provide context"
            pri = ResearchPrioritizer(assistant=asst)
            top = pri.recommend_next([h.to_dict() for h in hyps])
            chosen = next((h for h in hyps if h.hypothesis_id == top.get("hypothesis_id")), hyps[0])
            gen.store(chosen, now=ctx.get("_now", ""), commit=ctx.get("_commit", False))
            return ST_COMPLETED, {"hypothesis": chosen.to_dict(),
                                  "candidates": [h.to_dict() for h in hyps]}, chosen.statement

        if stage == M.L_DESIGN:
            hyp = carry.get("hypothesis")
            if not hyp:
                return ST_SKIPPED, {}, "no hypothesis to design"
            from jarvis.research_workflow.experiment_planner import ExperimentPlanner
            spec = ExperimentPlanner().plan(hyp)
            return ST_COMPLETED, {"spec": spec.to_dict()}, spec.spec_hash

        if stage == M.L_BACKTEST:
            if ctx.get("backtest"):
                return ST_COMPLETED, {"backtest": True}, "backtest result provided (external)"
            return ST_BLOCKED, {}, "human checkpoint: run backtest for the spec (not executed here)"

        if stage == M.L_VALIDATION:
            bt = ctx.get("backtest")
            if not bt:
                return ST_BLOCKED, {}, "no backtest to validate"
            from jarvis.research_ingestion.models import validate_backtest
            v = validate_backtest(bt)
            return ST_COMPLETED, {"validation": v}, \
                ("validation complete" if v["validation_complete"] else "INCOMPLETE")

        if stage == M.L_FAILURE:
            from jarvis.research_workflow.research_critic import ResearchCritic
            spec = carry.get("spec") or {}
            metrics = (ctx.get("backtest") or {}).get("metrics") or {}
            rep = ResearchCritic().critique(spec, metrics=metrics)
            return ST_COMPLETED, {"critique": rep.to_dict()}, f"verdict {rep.verdict}"

        if stage == M.L_LESSON:
            crit = carry.get("critique") or {}
            val = carry.get("validation") or {}
            verdict = crit.get("verdict", "PASS")
            blockers = crit.get("blocking_dimensions") or []
            name = crit.get("subject", str(idea))
            lesson = (f"AUTONOMOUS LESSON [{name}] — critic verdict {verdict}"
                      + (f", blocked on {blockers}" if blockers else "")
                      + (f"; validation {'complete' if val.get('validation_complete') else 'incomplete'}"
                         if val else ""))
            self._memory().record_lesson(origin=str(idea), lesson=lesson,
                                         evidence={"critique": crit, "validation": val},
                                         impact="autonomous_loop", now=ctx.get("_now", ""),
                                         commit=ctx.get("_commit", False))
            return ST_COMPLETED, {"lesson": lesson}, lesson

        if stage == M.L_UPDATE:
            crit = carry.get("critique") or {}
            base = (carry.get("hypothesis") or {}).get("statement", str(idea))
            weak = crit.get("blocking_dimensions") or [c["dimension"] for c in crit.get("critiques", [])
                                                       if c.get("severity") == "WARN"][:2] or ["identified weaknesses"]
            statement = f"{base} — hardened against {', '.join(weak)}"
            updated = {"hypothesis_id": M.hypothesis_id(statement), "statement": statement,
                       "rationale": f"이전 실험 비판({weak})을 반영한 갱신 가설.",
                       "expected_edge": "MEDIUM", "source": "autonomous_update", "confidence": "MEDIUM",
                       "assumptions": ["교정이 원 엣지를 보존한다"],
                       "invalidation_conditions": ["동일 약점이 재발한다"]}
            from jarvis.research_workflow.hypothesis_generator import Hypothesis, HypothesisGenerator
            HypothesisGenerator(assistant=asst, memory_engine=self._mem).store(
                Hypothesis(**{k: updated[k] for k in ("hypothesis_id", "statement", "rationale",
                            "expected_edge", "assumptions", "invalidation_conditions", "source",
                            "confidence")}), now=ctx.get("_now", ""), commit=ctx.get("_commit", False))
            return ST_COMPLETED, {"updated_hypothesis": updated}, statement

        if stage == M.L_NEXT:
            from jarvis.research_workflow.research_prioritizer import ResearchPrioritizer
            cands = list(carry.get("candidates") or [])
            upd = carry.get("updated_hypothesis")
            if upd:
                cands = [c for c in cands if c.get("hypothesis_id") != (carry.get("hypothesis") or {}).get("hypothesis_id")]
                cands.append(upd)
            nxt = ResearchPrioritizer(assistant=asst).recommend_next(cands) if cands else {}
            return ST_COMPLETED, {"next": nxt}, nxt.get("statement", "no next candidate")

        return ST_SKIPPED, {}, "unknown stage"

    # ── 구동 ──
    def _drive(self, collected, loop_id, idea, context, start_index, now, commit) -> LoopState:
        ctx = dict(context or {})
        ctx["_now"], ctx["_commit"] = now, commit
        prev = LOOP_STAGES[start_index - 1] if start_index > 0 else GENESIS
        for i in range(start_index, len(LOOP_STAGES)):
            stage = LOOP_STAGES[i]
            carry = self._artifacts(collected)
            status, payload, note = self._run_stage(stage, idea, ctx, carry)
            self._emit(collected, loop_id, idea, stage, status, prev, payload, note, now, commit)
            prev = stage
            if status == ST_BLOCKED:
                break
        return self._state_from_events(loop_id, collected)

    def run(self, idea, context=None, *, seed="", now="", commit=False) -> LoopState:
        """자율 루프 실행 — IDEA 부터 순서대로 조율. Backtest 외부입력 없으면 BLOCKED(사람 체크포인트)."""
        loop_id = M.loop_id(str(idea), seed)
        collected = list(ledger.loop_events(loop_id))
        if any(e.get("status") == ST_CANCELLED for e in collected):
            raise LoopCancelledError(loop_id)
        return self._drive(collected, loop_id, idea, context, len(self._completed(collected)), now, commit)

    def resume(self, loop_id, idea, context=None, *, now="", commit=False) -> LoopState:
        """마지막 완료 단계 이후부터 재개(BLOCKED 였던 단계는 입력이 생기면 재실행)."""
        collected = list(ledger.loop_events(loop_id))
        if not collected:
            raise ValueError(f"unknown loop {loop_id}")
        if any(e.get("status") == ST_CANCELLED for e in collected):
            raise LoopCancelledError(loop_id)
        completed = {e["stage"] for e in collected if e.get("status") == ST_COMPLETED}
        start = next((i for i, s in enumerate(LOOP_STAGES) if s not in completed), len(LOOP_STAGES))
        if start >= len(LOOP_STAGES):
            return self._state_from_events(loop_id, collected)
        return self._drive(collected, loop_id, idea, context, start, now, commit)

    def pause(self, loop_id, idea="", note="", *, now="", commit=False) -> LoopState:
        """루프 일시정지(감사 이벤트). resume 으로 재개."""
        collected = list(ledger.loop_events(loop_id))
        self._emit(collected, loop_id, idea, LOOP_STAGES[0], PAUSED, "", {}, note or "paused", now, commit)
        return self._state_from_events(loop_id, collected)

    def cancel(self, loop_id, reason="", *, now="", commit=False) -> LoopState:
        collected = list(ledger.loop_events(loop_id))
        self._emit(collected, loop_id, "", M.L_NEXT, ST_CANCELLED, "", {}, reason or "cancelled", now, commit)
        return self._state_from_events(loop_id, collected)

    def _completed(self, events) -> list:
        out = []
        for e in events:
            if e.get("status") == ST_COMPLETED and e["stage"] not in out:
                out.append(e["stage"])
        return out

    def state(self, loop_id) -> LoopState:
        return self._state_from_events(loop_id, ledger.loop_events(loop_id))

    def _state_from_events(self, loop_id, events) -> LoopState:
        idea = events[0].get("idea", "") if events else ""
        completed, trail = [], []
        blocked = ""
        cancelled = paused = False
        for e in events:
            trail.append({"stage": e["stage"], "status": e["status"], "note": e.get("note", "")})
            if e["status"] == ST_COMPLETED and e["stage"] not in completed:
                completed.append(e["stage"])
            blocked = e["stage"] if e["status"] == ST_BLOCKED else blocked
            if e["status"] == ST_CANCELLED:
                cancelled = True
            paused = e["status"] == PAUSED
        if blocked in completed:
            blocked = ""
        current = blocked or (LOOP_STAGES[len(completed)] if len(completed) < len(LOOP_STAGES) else M.L_NEXT)
        art = self._artifacts(events)
        for k in ("_now", "_commit"):
            art.pop(k, None)
        requires_human = (M.L_NEXT in completed or bool(blocked)) and not cancelled
        return LoopState(
            loop_id=loop_id, idea=idea, current_stage=current, completed_stages=completed,
            blocked_stage=blocked, cancelled=cancelled, paused=paused, artifacts=art,
            audit_trail=trail, requires_human_checkpoint=requires_human)
