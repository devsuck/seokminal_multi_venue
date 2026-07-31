"""Monthly Decision Loop (Phase 5-C) — **절차 정의 + 읽기전용 projection. 새 원장·새 계산엔진 없음.**

목적: 월 1회 "이 전략 계속 가져갈까?" 를 사람이 판단할 때 훑어야 할 정보를 한 화면에 모은다.
      Current Positions → Strategy Status → Forward Progress → Validation Changes → Risk Changes →
      Decision Required 순서. 전부 forward_learning(STEP4-A)·registry·risk governor·paper_execution
      원장을 그대로 재사용 — 신규 데이터 소스 없음, 신규 지표 계산 없음.

`suggested_label`(KEEP/WATCH/PAUSE/REJECT) 은 이미 알려진 상태(evidence robust 여부·forward 편차·
invalidation 트리거 여부·registry 상 이미 내려진 상태)를 그대로 라벨로 옮긴 것 — frontend의 기존
evidenceQuality()/forwardProgress()/riskState() 톤 함수와 동일한 성격(신규 판단 로직 아님). **제안일
뿐, 결정 아님** — 어떤 registry/state 도 이 라벨로 자동 갱신되지 않는다. 사람이 최종 결정.
"""
from __future__ import annotations


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _positions() -> list[dict]:
    from jarvis.paper_execution.ledger import current_positions
    return list(_safe(lambda: current_positions().values(), {}) or {})


def _prediction_integrity() -> dict:
    """Phase 5-F Step4 — prediction_registry.registry_status()의 by_integrity 읽기 재사용(신규 계산 없음)."""
    st = _safe(lambda: __import__("jarvis.research_workflow.prediction_registry",
                                  fromlist=["registry_status"]).registry_status(), {}) or {}
    by = st.get("by_integrity") or {}
    return {"valid": by.get("VALID", 0), "legacy_capture": by.get("LEGACY_CAPTURE", 0),
            "invalidated": by.get("INVALIDATED", 0), "recapture_required": by.get("RECAPTURED", 0)}


def _suggested_label(record: dict) -> dict:
    """기존에 이미 알려진 값(evidence/forward/risk/registry 상태)을 KEEP/WATCH/PAUSE/REJECT 로 매핑.
    새 판단 로직 없음 — dashboard가 이미 보여주는 3개 톤(Evidence/Forward/Risk)의 조합일 뿐."""
    status = record.get("validation_status")
    if status in ("paper_failed", "paper_retired", "rejected"):
        return {"label": "REJECT", "reason": f"registry 상 이미 {status}로 전이됨 — 사람이 이미 결정"}

    ev = record.get("evidence_used") or []
    latest = ev[-1] if ev else {}
    robust = bool(latest.get("cost_robust")) and latest.get("wf_second_sharpe") is not None
    dev = (record.get("current_behavior") or {}).get("envelope_deviation")
    has_invalidation = bool(record.get("invalidation_condition"))
    has_forward = record.get("expected_behavior") is not None

    if dev is not None:
        return {"label": "PAUSE", "reason": "forward envelope 편차 감지 — 사람 확인 필요"}
    if not record.get("thesis") or not record.get("prediction_captured"):
        return {"label": "WATCH", "reason": "thesis 사전등록 불완전 — 판단 근거 부족"}
    if not has_forward:
        return {"label": "WATCH", "reason": "forward 데이터 아직 없음 — 축적 대기"}
    if robust and has_invalidation:
        return {"label": "KEEP", "reason": "WF+cost robust 근거 · invalidation 조건 등록됨 · 편차 없음"}
    return {"label": "WATCH", "reason": "근거 partial — 계속 관찰"}


def build_monthly_review() -> dict:
    """월간 Decision Loop 절차용 read-model. 6단계를 이미 존재하는 값으로 채운다.

    1) Current Positions  2) Strategy Status  3) Forward Progress  4) Validation Changes
    5) Risk Changes  6) Decision Required(사람이 KEEP/WATCH/PAUSE/REJECT 중 실제로 고름 — 여기 라벨은 제안).
    """
    import jarvis.investment_os as ios

    fwd = _safe(lambda: ios.build_forward_learning_records(), {}) or {}
    records = fwd.get("records", [])
    positions = _positions()

    risk = _safe(lambda: __import__("jarvis.risk.governor", fromlist=["RiskLimits"]).RiskLimits(), None)

    strategies = []
    for r in records:
        suggestion = _suggested_label(r)
        strategies.append({
            "strategy_id": r.get("strategy_id"),
            "strategy_status": r.get("validation_status"),
            "forward_progress": {"expected_behavior": r.get("expected_behavior"),
                                 "current_behavior": r.get("current_behavior"),
                                 "paper_start_date": r.get("paper_start_date"),
                                 "forward_period_months": r.get("forward_period_months")},
            "validation_changes": (r.get("decision_history") or [])[-5:],
            "risk_changes": {"invalidation_condition": r.get("invalidation_condition")},
            "decision_required": {
                "suggested_label": suggestion["label"], "reason": suggestion["reason"],
                "next_possible": r.get("next_possible", []),
                "human_approval_required_next": r.get("human_approval_required_next", []),
                "is_suggestion": True,
            },
        })

    return {
        "step_order": ["current_positions", "strategy_status", "forward_progress",
                       "validation_changes", "risk_changes", "decision_required"],
        "current_positions": {"positions": positions, "count": len(positions)},
        "strategies": strategies, "count": len(strategies),
        "risk_limits": {"max_notional": getattr(risk, "max_notional", None),
                        "kill_switch": getattr(risk, "kill_switch", None)} if risk else {},
        "prediction_integrity": _prediction_integrity(),
        "labels": ["KEEP", "WATCH", "PAUSE", "REJECT"],
        "requires_human_review": True, "is_advisory": True, "is_decision": False,
        "note": ("Monthly Decision Loop(절차, Phase 5-C) — forward_learning·registry·risk governor·"
                 "paper_execution 원장 재사용. 새 원장·새 계산엔진 없음. suggested_label 은 이미 알려진 "
                 "상태의 라벨 매핑일 뿐 — 어떤 registry도 자동 갱신 안 됨. 사람이 실제로 KEEP/WATCH/"
                 "PAUSE/REJECT 를 고르고 그 결정은 decision_center.record_decision() 기존 감사로 저장.")}
