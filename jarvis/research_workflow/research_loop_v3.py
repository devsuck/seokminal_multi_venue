"""Continuous Research Loop v3 (P190) — 전체 연구 루프를 연결한다. **조율만, 실행 없음.**

Observation → Opportunity → Hypothesis → Experiment Proposal → **Human Checkpoint** → External Test →
Validation → Ranking → Knowledge Update → Next Research Cycle.

**Human Checkpoint 에서 정지** — 사람 승인 없이 External Test 로 진입하지 않는다(자동 백테스트 없음).
**재사용**: research_cycle(P181)·experiment_designer(P184)·research_gate(P186)·
validation_intelligence(P187)·research_selection(P188)·continuous_learning(P136, 학습). 새 원장 없음.

원칙(문서 §Constitution, §P190): 통합·조율만 · 결정적 · 자문 전용 · 자동 실행 없음 · 거래·집행 없음 · 사람 결정.
"""
from __future__ import annotations

# 루프 단계(문서 §P190) — Human Checkpoint 에서 정지
LOOP_STAGES = ("OBSERVATION", "OPPORTUNITY", "HYPOTHESIS", "EXPERIMENT_PROPOSAL",
               "HUMAN_CHECKPOINT", "EXTERNAL_TEST", "VALIDATION", "RANKING",
               "KNOWLEDGE_UPDATE", "NEXT_CYCLE")


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def run_research_loop(topic: str = "", *, signals=None, limit: int = 6,
                      external_results: dict | None = None) -> dict:
    """전체 연구 루프 조율. Human Checkpoint 에서 정지(external_results 없으면). 결정적·읽기전용.

    external_results(선택): 사람이 외부에서 실행한 백테스트 결과 — 있으면 VALIDATION→RANKING→
    KNOWLEDGE_UPDATE 진행(학습은 continuous_learning 재사용). 없으면 HUMAN_CHECKPOINT 에서 정지.
    """
    stages_done = []

    # OBSERVATION → OPPORTUNITY → HYPOTHESIS → PRIORITIZE (research_cycle 재사용, WAITING_HUMAN 정지)
    cycle = _safe(lambda: __import__("jarvis.research_workflow.research_cycle",
                                     fromlist=["run_cycle"]).run_cycle(topic, signals=signals, limit=limit),
                  {}) or {}
    stages_done += ["OBSERVATION", "OPPORTUNITY", "HYPOTHESIS"]
    research_queue = cycle.get("research_queue", [])
    top = research_queue[0] if research_queue else {}

    # EXPERIMENT_PROPOSAL (experiment_designer)
    proposal = _safe(lambda: __import__("jarvis.research_workflow.experiment_designer",
                                        fromlist=["design_experiment"]).design_experiment(top), {}) or {}
    stages_done.append("EXPERIMENT_PROPOSAL")

    # HUMAN_CHECKPOINT (research_gate — approval queue, 승인=외부 테스트 허용, 실행 아님)
    gate = _safe(lambda: __import__("jarvis.research_workflow.research_gate",
                                    fromlist=["build_approval_queue"]
                                    ).build_approval_queue(research_queue, limit=limit), {}) or {}
    stages_done.append("HUMAN_CHECKPOINT")

    loop = {"topic": topic, "loop_stages": list(LOOP_STAGES), "stages_completed": stages_done,
            "cycle_state": cycle.get("state"), "human_checkpoint_pending": True,
            "auto_backtest": False,
            "observation": cycle.get("outputs", {}).get("observation", {}),
            "top_hypothesis": {"question": top.get("question"), "priority_score": top.get("priority_score")},
            "experiment_proposal": {"universe": proposal.get("universe"),
                                    "expected_research_value": proposal.get("expected_research_value"),
                                    "failure_conditions": proposal.get("failure_conditions", [])},
            "human_review_queue": {"queue_size": gate.get("queue_size", 0),
                                   "actions": gate.get("available_actions", [])}}

    # external_results 있으면(사람이 외부 실행 후 주입) VALIDATION → RANKING → KNOWLEDGE_UPDATE
    if external_results:
        validation = _safe(lambda: __import__("jarvis.research_workflow.validation_intelligence",
                                              fromlist=["build_validation_report"]
                                              ).build_validation_report(external_results,
                                                                        external_results.get("paper")), {}) or {}
        selection = _safe(lambda: __import__("jarvis.research_workflow.research_selection",
                                             fromlist=["evaluate_research"]
                                             ).evaluate_research(external_results, validation=validation), {}) or {}
        learned = _safe(lambda: __import__("jarvis.research_workflow.continuous_learning",
                                           fromlist=["on_research_complete"]
                                           ).on_research_complete(external_results, commit=False), {}) or {}
        loop["stages_completed"] += ["EXTERNAL_TEST", "VALIDATION", "RANKING", "KNOWLEDGE_UPDATE"]
        loop["validation"] = {"classification": validation.get("classification"),
                              "failure_reasons": validation.get("failure_reasons", [])}
        loop["evidence_grade"] = selection.get("evidence_grade")
        loop["knowledge_update"] = {"learned": bool(learned)}
        loop["human_checkpoint_pending"] = False

    loop.update({"requires_human_review": True, "is_advisory": True, "is_decision": False,
                 "note": ("Continuous Research Loop v3(읽기전용) — Observation→…→Human Checkpoint 정지. "
                          "external_results 주입 시에만 Validation→Ranking→Knowledge 진행. "
                          "자동 백테스트 없음, 새 원장 없음. 사람이 모든 결정.")})
    return loop
