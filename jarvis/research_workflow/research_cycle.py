"""Autonomous Research Cycle Manager (P181) — 전체 연구 루프 **상태**를 관리한다. **상태 관리만, 실행 없음.**

Lifecycle(결정적 상태기계):
  CREATED → OBSERVING → DISCOVERING → GENERATING → PRIORITIZING → WAITING_HUMAN →
  EXTERNAL_VALIDATION → ANALYZING → LEARNING → COMPLETED.

**반드시**: 자동 백테스트 실행 금지 · WAITING_HUMAN 체크포인트 유지(사람 승인 없이 EXTERNAL_VALIDATION 진입 불가).

**재사용**: market_observation(P182)·opportunity_discovery(P92)·hypothesis_discovery(P183)·
research_priority(P185)·research_scheduler(P141). 새 원장 없음(상태는 반환값으로만 — append-only 원장 미생성).

원칙(문서 §Constitution, §P181): 통합·조율만 · 결정적 · 자문 전용 · 자동 실행 없음 · 거래·집행 없음 · 사람 결정.
"""
from __future__ import annotations

LIFECYCLE = ("CREATED", "OBSERVING", "DISCOVERING", "GENERATING", "PRIORITIZING",
             "WAITING_HUMAN", "EXTERNAL_VALIDATION", "ANALYZING", "LEARNING", "COMPLETED")
# 사람 승인 없이 넘어갈 수 없는 체크포인트
HUMAN_CHECKPOINT = "WAITING_HUMAN"
# 자동으로 진입 불가한 상태(사람 승인 필요)
_HUMAN_GATED = ("EXTERNAL_VALIDATION",)


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _cid(topic):
    import hashlib
    return "CYCLE:" + hashlib.sha1((topic or "cycle").encode()).hexdigest()[:12]


class ResearchCycleManager:
    """연구 루프 상태기계 — 관찰→발견→생성→우선순위→[사람]→검증→분석→학습. 실행 권한 없음."""

    def create_cycle(self, topic: str = "") -> dict:
        return {"cycle_id": _cid(topic), "topic": topic, "state": "CREATED",
                "history": ["CREATED"], "outputs": {}, "human_checkpoint_pending": False,
                "requires_human_review": True, "is_advisory": True, "is_decision": False}

    def _next(self, state):
        i = LIFECYCLE.index(state)
        return LIFECYCLE[i + 1] if i + 1 < len(LIFECYCLE) else state

    def advance(self, cycle: dict, *, human_approved: bool = False) -> dict:
        """다음 상태로 전이(결정적). WAITING_HUMAN 에서는 human_approved 없이 진입 금지."""
        cyc = dict(cycle)
        state = cyc.get("state", "CREATED")
        nxt = self._next(state)
        # 사람 게이트: WAITING_HUMAN → EXTERNAL_VALIDATION 은 승인 필수
        if nxt in _HUMAN_GATED and not human_approved:
            cyc["human_checkpoint_pending"] = True
            cyc["note"] = "WAITING_HUMAN 체크포인트 — 사람 승인 없이 EXTERNAL_VALIDATION 진입 불가."
            return cyc
        cyc["state"] = nxt
        cyc["history"] = list(cyc.get("history", [])) + [nxt]
        cyc["human_checkpoint_pending"] = (nxt == HUMAN_CHECKPOINT)
        return cyc

    def run_to_checkpoint(self, topic: str = "", *, signals=None, limit: int = 8) -> dict:
        """CREATED → … → WAITING_HUMAN 까지 자동 수행(각 단계 기존 모듈 조율). **체크포인트에서 정지.**

        자동 백테스트 없음 — WAITING_HUMAN 에서 멈추고 사람 승인을 기다린다.
        """
        cyc = self.create_cycle(topic)
        outputs = {}

        # OBSERVING — 시장 관찰 → 기회
        obs = _safe(lambda: __import__("jarvis.research_workflow.market_observation",
                                       fromlist=["observe_market"]).observe_market(signals=signals), {}) or {}
        outputs["observation"] = {"opportunity_count": obs.get("opportunity_count", 0),
                                  "by_type": obs.get("by_type", {})}
        top_opp = (obs.get("opportunities") or [{}])[0] if obs.get("opportunities") else {}
        cyc = self.advance(cyc)   # → OBSERVING

        # DISCOVERING — 기회 상세(상위)
        outputs["discovery"] = {"top_opportunity": top_opp.get("type"),
                                "questions": top_opp.get("possible_questions", [])}
        cyc = self.advance(cyc)   # → DISCOVERING

        # GENERATING — 가설 생성(recall-first)
        disc = _safe(lambda: __import__("jarvis.research_workflow.hypothesis_discovery",
                                        fromlist=["discover_research"]
                                        ).discover_research(topic, opportunity=top_opp, limit=limit), {}) or {}
        research_hyps = disc.get("research_hypotheses", [])
        outputs["hypotheses"] = {"count": len(research_hyps),
                                 "with_why_different": disc.get("with_why_different", 0)}
        cyc = self.advance(cyc)   # → GENERATING

        # PRIORITIZING — 연구 우선순위
        prio = _safe(lambda: __import__("jarvis.research_workflow.research_priority",
                                        fromlist=["prioritize_research"]
                                        ).prioritize_research(research_hyps, limit=limit), {}) or {}
        outputs["prioritization"] = {"queue_size": prio.get("count", 0), "top": prio.get("top", {})}
        cyc = self.advance(cyc)   # → PRIORITIZING

        cyc = self.advance(cyc)   # → WAITING_HUMAN (정지)

        cyc["outputs"] = outputs
        cyc["research_hypotheses"] = research_hyps
        cyc["research_queue"] = prio.get("research_queue", [])
        cyc["auto_backtest"] = False
        cyc["note"] = ("Research Cycle → WAITING_HUMAN 에서 정지. 자동 백테스트 없음. "
                       "사람이 외부 검증을 승인해야 EXTERNAL_VALIDATION 진입. 거래·집행 없음.")
        return cyc


def run_cycle(topic: str = "", *, signals=None, limit: int = 8) -> dict:
    """모듈 진입점 — WAITING_HUMAN 체크포인트까지 실행 후 정지."""
    return ResearchCycleManager().run_to_checkpoint(topic, signals=signals, limit=limit)
