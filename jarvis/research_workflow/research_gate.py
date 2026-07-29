"""Human Research Gate (P186) — 가장 중요한 governance layer. Research Approval Queue. **승인=외부 테스트 요청 허용, 실행 아님.**

Human Action: APPROVE RESEARCH REQUEST · REJECT · MODIFY.
**Approve 는 실행 명령이 아니다.** Approve 의미 = "외부 테스트 요청 허용"(사람이 외부에서 백테스트를 돌림).

**절대**: backtest 자동 실행 금지 · trade 금지 · execution 금지.
**재사용**: backtest_bridge(P102, CREATED→WAITING_HUMAN 전이만 — 실행 안 함)·experiment_designer(P184).

원칙(문서 §Constitution, §P186): 통합·조율만 · 결정적 · 자문 전용 · 자동 실행 없음 · 거래·집행 없음 · 사람 결정.
"""
from __future__ import annotations

HUMAN_ACTIONS = ("APPROVE", "REJECT", "MODIFY")
# 절대 허용하지 않는 액션(방어) — Approve 조차 실행이 아님
FORBIDDEN_ACTIONS = ("execute", "trade", "allocate", "place_order", "approve_investment",
                     "deploy_strategy", "auto_backtest", "run_backtest")


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _rid(question):
    import hashlib
    return "REQ:" + hashlib.sha1((question or "req").encode()).hexdigest()[:12]


def build_approval_queue(candidates, *, limit: int = 10) -> dict:
    """연구 후보 → Research Approval Queue(PENDING). 각 항목에 제안 실험 첨부. 결정적·읽기전용."""
    cands = [c.to_dict() if hasattr(c, "to_dict") else dict(c) for c in (candidates or [])]
    requests = []
    for c in cands[:limit]:
        question = c.get("question") or c.get("statement", "")
        proposal = _safe(lambda: __import__("jarvis.research_workflow.experiment_designer",
                                            fromlist=["design_experiment"]).design_experiment(c), {}) or {}
        requests.append({"request_id": _rid(question), "question": question,
                         "priority_score": c.get("priority_score", c.get("novelty", 0.5)),
                         "why_important": c.get("why_important", ""),
                         "proposed_experiment": {"universe": proposal.get("universe"),
                                                 "metrics": proposal.get("metrics", []),
                                                 "failure_conditions": proposal.get("failure_conditions", []),
                                                 "expected_research_value": proposal.get("expected_research_value")},
                         "available_actions": list(HUMAN_ACTIONS), "status": "PENDING",
                         "requires_human_review": True})
    return {"queue_size": len(requests), "requests": requests,
            "available_actions": list(HUMAN_ACTIONS), "forbidden_actions": list(FORBIDDEN_ACTIONS),
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Human Research Gate(읽기전용) — 승인 큐. APPROVE=외부 테스트 요청 허용(실행 아님). "
                     "자동 백테스트·거래·집행 없음. 모든 결정은 사람.")}


def act(action: str, request_id: str, *, hypothesis=None, modification: str = "") -> dict:
    """사람 액션 처리. APPROVE→외부 테스트 요청(WAITING_HUMAN), REJECT→기각, MODIFY→수정요청. 실행 없음."""
    a = (action or "").strip().upper()
    if a.lower() in FORBIDDEN_ACTIONS or a not in HUMAN_ACTIONS:
        return {"error": f"금지되거나 알 수 없는 액션: {action}", "allowed": list(HUMAN_ACTIONS),
                "is_binding": False, "is_decision": False}
    if a == "APPROVE":
        # backtest_bridge 로 잡 생성 후 WAITING_HUMAN 전이 — **실행하지 않는다**(사람이 외부에서 돌림)
        result = _safe(lambda: _approve_external_test(hypothesis), {})
        return {"action": "APPROVE", "request_id": request_id,
                "meaning": "외부 테스트 요청 허용 — Jarvis 는 실행하지 않는다(사람이 외부 백테스트 실행)",
                "job": result, "executed": False, "is_binding": False,
                "requires_human_review": True, "is_advisory": True, "is_decision": False}
    if a == "REJECT":
        return {"action": "REJECT", "request_id": request_id, "status": "ARCHIVED",
                "executed": False, "is_binding": False, "is_decision": False}
    return {"action": "MODIFY", "request_id": request_id, "modification": modification,
            "status": "RETURNED_FOR_REVISION", "executed": False, "is_binding": False,
            "is_decision": False}


def _approve_external_test(hypothesis) -> dict:
    """backtest_bridge 재사용 — 잡 생성 → WAITING_HUMAN. 자동 실행 없음(사람이 외부에서 실행)."""
    from jarvis.research_workflow.backtest_bridge import create_job, submit_for_human_run
    job = create_job(hypothesis or {"statement": "approved research"})
    job = submit_for_human_run(job)   # CREATED → WAITING_HUMAN (실행 아님)
    return job.to_dict()
