"""Collaborative Multi-Agent Research (P178) — 고정 파이프라인을 **협업 워크플로**로 확장한다. **분석만, 승인 없음.**

기존 multi_agent_workflow(P128, Director→Analyst→Strategy→Critic→Writer)를 재사용하고 그 위에 **협업 라운드**를
얹는다. 에이전트는 가설에 대해 결정적 액션을 낸다:
  challenge · refine · split · merge · reject · request_evidence.
Research Director 가 조율자로 종합한다. **자율 승인 없음** — 모든 결정은 사람.

원칙(문서 §Constitution, §P178): 통합·조율만 · 결정적 · 자문 전용 · 자율 승인 없음 · 거래·집행 없음 · 사람 결정.
"""
from __future__ import annotations

_COMPOUND_MARKERS = (" and ", " & ", " + ", "+", ";", " with ")


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _base_workflow(objective, events, commit, now):
    def _go():
        from jarvis.research_workflow.multi_agent_workflow import run
        return run(objective, events=events, commit=commit, now=now)
    return _safe(_go, {"review": {}, "report": {}}) or {}


def _recall(statement):
    return _safe(lambda: __import__("jarvis.research_workflow.semantic_recall",
                                    fromlist=["recall_context"]).recall_context(statement), {}) or {}


def _collab_actions(hypothesis, review, recall):
    """에이전트별 협업 액션(결정적). challenge/refine/split/merge/reject/request_evidence."""
    actions = []
    stmt = str(hypothesis or "")
    verdict = str(review.get("verdict", "")).upper()

    # Critic → challenge (항상: 가장 약한 고리 지적)
    actions.append({"agent": "ResearchReviewer", "action": "challenge",
                    "detail": "핵심 가정의 반증 조건을 명시 검증하라",
                    "rationale": f"critic verdict={verdict or 'n/a'}"})

    # StrategyResearcher → split (복합 가설이면 분해 제안)
    if any(m in stmt.lower() for m in _COMPOUND_MARKERS):
        actions.append({"agent": "StrategyResearcher", "action": "split",
                        "detail": "복합 가설을 독립 검증 가능한 하위 가설로 분해",
                        "rationale": "compound statement detected"})
    else:
        actions.append({"agent": "StrategyResearcher", "action": "refine",
                        "detail": "유니버스/기간을 좁혀 검정력 높은 변형으로 정제",
                        "rationale": "atomic statement — refine scope"})

    # Analyst → request_evidence (선행연구 적거나 증거 부족 시)
    prior = recall.get("prior_research_count")
    prior_n = len(prior) if isinstance(prior, list) else (int(prior) if prior else 0)
    if prior_n <= 1:
        actions.append({"agent": "MarketAnalyst", "action": "request_evidence",
                        "detail": "데이터/선행연구 근거 보강 요청(커버리지 부족)",
                        "rationale": f"prior_research={prior_n}"})

    # Reviewer → merge (유사 과거연구 존재 시) / reject (부정 verdict 시)
    if recall.get("tried_before"):
        actions.append({"agent": "ResearchReviewer", "action": "merge",
                        "detail": "유사 과거 연구와 병합해 중복 회피",
                        "rationale": "recall:tried_before"})
    if verdict in ("REJECT", "FAIL", "NEGATIVE"):
        actions.append({"agent": "ResearchReviewer", "action": "reject",
                        "detail": "현 형태로는 기각 — 교정 없이는 재검증 금지",
                        "rationale": f"verdict={verdict}"})
    return actions


def run_collaborative_research(objective: str, *, hypothesis: str = "", events=None,
                               now: str = "", commit: bool = False) -> dict:
    """협업 다중 에이전트 연구 — 기존 파이프라인 + 협업 라운드. 결정적·읽기전용. 자율 승인 없음.

    commit 은 기존 multi_agent_workflow 로 전달(rwf_/ras_ 기존 원장만). 새 원장 없음.
    """
    obj = (objective or "").strip()
    hyp = (hypothesis or obj).strip()
    base = _base_workflow(obj, events, commit, now)
    review = base.get("review", {}) or {}
    recall = _recall(hyp)

    actions = _collab_actions(hyp, review, recall)
    action_counts: dict = {}
    for a in actions:
        action_counts[a["action"]] = action_counts.get(a["action"], 0) + 1

    # Director 종합(조율자) — 결정 아님, 사람 검토 큐로 전달
    director_synthesis = {
        "coordinator": "ResearchDirector",
        "collaboration_summary": f"{len(actions)}개 협업 액션 · verdict={review.get('verdict', 'n/a')}",
        "next_step": "사람 검토 후 정제/분해/기각 결정",
        "autonomous_approval": False}

    return {"objective": obj, "hypothesis": hyp,
            "base_pipeline": base.get("pipeline", ["Director", "Analyst", "StrategyResearcher",
                                                   "Critic", "Writer"]),
            "collaboration_actions": actions, "action_counts": action_counts,
            "director_synthesis": director_synthesis,
            "review": review, "report": base.get("report", {}),
            "human_review_queue": [{"hypothesis": hyp, "actions": len(actions),
                                    "requires_human_review": True}],
            "committed": bool(commit),
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Collaborative Multi-Agent Research(읽기전용) — 협업 라운드(challenge/refine/split/"
                     "merge/reject/request_evidence), Director 조율. 자율 승인 없음, 새 원장 없음. 사람이 결정.")}
