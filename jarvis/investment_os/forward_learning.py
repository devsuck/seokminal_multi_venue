"""jarvis.investment_os.forward_learning — Forward Learning Record (STEP4-A). **읽기전용 프로젝션.**

기존 registry(FSM)·research/agents/experiment_registry(백테스트 증거)·research_workflow.prediction_registry
(P201, thesis·invalidation·evidence 사전등록)·jarvis.paper.deploy(배포 메타)+각 forward 러너가 이미
기록해 둔 ledger(.jsonl)/report(.md) 파일을 strategy_id 로 조인한 읽기모델. **새 원장·새 schema·새 store
없음** — 순수 in-memory projection. **러너의 generate()/run_forward() 는 절대 호출하지 않는다** — 이미
기록된 파일만 읽는다(호출 시 매번 실데이터 로드+백테스트 재실행 = 요청 스레드에서 무거운 연산, 읽기전용
원칙 위반. 최초 구현에서 이 실수를 했다가 동시요청 시 CPU 100%+·99초 지연으로 발견, 파일 읽기로 수정).

답하는 질문(STEP4 완료 기준): "어디까지 검증됐는가"(validation_status) · "왜 믿는가"(thesis+evidence_used) ·
"실제 결과가 thesis와 일치하는가"(expected_behavior vs current_behavior) · "다음 판단·승인자는 누구인가"
(next_possible_transitions + human_approval_required_next).

원칙: Research OS 무변경, 새 파일은 이 소비층(investment_os)에만. 실행 없음. 사람이 결정.
"""
from __future__ import annotations

_TRACKED_STATUSES = ("paper_active", "paper_candidate",
                     "paper_candidate_forward_test_required", "watchlist")


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _registry_events(strategy_id: str) -> list[dict]:
    """registry.jsonl 원시 이벤트(해당 strategy_id만) — decision_history 용. 읽기전용, 파일 그대로."""
    import json
    import os

    from jarvis.config import state_path
    path = state_path("registry.jsonl")
    if not os.path.exists(path):
        return []
    out = []
    with open(path) as f:
        for ln in f:
            if not ln.strip():
                continue
            ev = json.loads(ln)
            if ev.get("strategy_id") == strategy_id:
                out.append(ev)
    return out


def _experiment_evidence(strategy_id: str) -> list[dict]:
    """experiment_registry.jsonl 에서 해당 hypothesis_id 증거(최근 5건). 읽기전용."""
    rows = _safe(lambda: __import__("research.agents.experiment_registry",
                                    fromlist=["load_all"]).load_all(), []) or []
    return [r for r in rows if r.get("hypothesis_id") == strategy_id][-5:]


def _prediction_for(strategy_id: str) -> dict | None:
    preds = _safe(lambda: __import__("jarvis.research_workflow.prediction_registry",
                                     fromlist=["list_predictions"]).list_predictions(), []) or []
    matches = [p for p in preds if p.get("strategy_id") == strategy_id]
    return matches[-1] if matches else None


_ENVELOPE_RE = __import__("re").compile(
    r"Sharpe ([\d.\-]+) · maxDD ([\d.\-]+) · 월수익 평균 ([\d.\-]+) std ([\d.\-]+) · "
    r"P10 ([\d.\-]+) / P90 ([\d.\-]+)")


def _forward_report(strategy_id: str) -> dict | None:
    """전용 forward 러너(tsmom/tom/buyback 등)의 **이미 기록된** ledger/report 파일만 읽는다.

    중요: `jarvis.paper.deploy.run_forward()` 는 러너의 `generate(write=False)` 를 호출해
    실데이터 로드+전체 백테스트를 **매 호출마다 재실행**한다 — 대시보드 페이지 로드마다 부르면
    무거운 연산이 요청 스레드에서 동시에 여러 번 실행되어 원인이 된다(측정: 동시 4-endpoint
    로드 시 99초). "읽기전용 projection, 실행 없음" 원칙에도 어긋남 — 여기서는 절대 generate()
    를 부르지 않고 이미 주기적으로 기록된 ledger(.jsonl)/report(.md) 파일만 읽는다.
    """
    import importlib
    import json
    import os

    dep = _safe(lambda: __import__("jarvis.paper.deploy",
                                   fromlist=["deployment_of"]).deployment_of(strategy_id))
    if not dep or dep.get("runner") in (None, "generic"):
        return None
    mod_name = dep["runner"].split(":")[0]
    mod = _safe(lambda: importlib.import_module(mod_name))
    ledger_path = getattr(mod, "LEDGER", None)
    report_path = getattr(mod, "REPORT", None)
    if not ledger_path or not os.path.exists(ledger_path):
        return None

    last = None
    with open(ledger_path) as f:
        for ln in f:
            if ln.strip():
                last = json.loads(ln)
    if last is None:
        return None

    envelope = None
    if report_path and os.path.exists(report_path):
        with open(report_path) as f:
            m = _ENVELOPE_RE.search(f.read())
        if m:
            envelope = {"sharpe": float(m.group(1)), "max_dd": float(m.group(2)),
                        "monthly_p10": float(m.group(5)), "monthly_p90": float(m.group(6))}

    return {"as_of": last.get("as_of"), "backtest_envelope": envelope,
            "forward_months": last.get("forward_months"), "envelope_deviation": None}


def _deployment(strategy_id: str) -> dict | None:
    return _safe(lambda: __import__("jarvis.paper.deploy",
                                    fromlist=["deployment_of"]).deployment_of(strategy_id))


def _first_deployment(strategy_id: str) -> dict | None:
    """paper_start_date 전용 — 최초 배포 행. 반복 재배포 기록 때문에 deployment_of()(최신 행)을 쓰면
    forward 추적 시작일이 계속 "지금"으로 밀린다(STEP5 audit P4)."""
    return _safe(lambda: __import__("jarvis.paper.deploy",
                                    fromlist=["first_deployment_of"]).first_deployment_of(strategy_id))


def _next_transitions(status: str) -> dict:
    from jarvis.registry import ALLOWED_TRANSITIONS, Status
    try:
        allowed = {s.value for s in ALLOWED_TRANSITIONS.get(Status(status), set())}
    except ValueError:
        allowed = set()
    human_gated = {Status.LIVE_CANDIDATE.value, Status.MICRO_LIVE.value, Status.CONSTRAINED_LIVE.value}
    return {"next_possible": sorted(allowed),
            "human_approval_required_next": sorted(allowed & human_gated)}


def build_record(strategy_id: str) -> dict:
    """전략 1개의 Forward Learning Record — 전부 기존 데이터 조인, 읽기전용."""
    from jarvis.registry import StrategyRegistry
    st = _safe(lambda: StrategyRegistry().state(strategy_id))
    if st is None:
        return {"strategy_id": strategy_id, "found": False}

    events = _registry_events(strategy_id)
    evidence_rows = _experiment_evidence(strategy_id)
    prediction = _prediction_for(strategy_id)
    dep = _deployment(strategy_id)
    first_dep = _first_deployment(strategy_id)
    fwd = _forward_report(strategy_id)
    latest_ev = evidence_rows[-1] if evidence_rows else {}

    thesis = (prediction or {}).get("thesis") or latest_ev.get("note") or latest_ev.get("verdict") or ""

    expected_behavior = None
    current_behavior = None
    if fwd:
        expected_behavior = fwd.get("backtest_envelope")
        current_behavior = {"forward_months": fwd.get("forward_months"),
                            "envelope_deviation": fwd.get("envelope_deviation")}

    return {
        "strategy_id": strategy_id, "found": True,
        "validation_status": st.get("status"),
        "thesis": thesis,
        "evidence_used": [{"sharpe": e.get("sharpe"), "p": e.get("p"),
                           "random_percentile": e.get("random_percentile"),
                           "wf_first_sharpe": e.get("wf_first_sharpe"),
                           "wf_second_sharpe": e.get("wf_second_sharpe"),
                           "cost_robust": e.get("cost_robust"), "verdict": e.get("verdict")}
                          for e in evidence_rows],
        "paper_start_date": (first_dep or {}).get("deployed_at"),
        "forward_period_months": len((fwd or {}).get("forward_months") or {}),
        "expected_behavior": expected_behavior,
        "current_behavior": current_behavior,
        "invalidation_condition": (prediction or {}).get("invalidation_condition") or None,
        "prediction_captured": prediction is not None,
        "decision_history": [{"from": e.get("from"), "to": e.get("to"), "reason": e.get("reason"),
                              "approver": e.get("approver"), "timestamp": e.get("timestamp")}
                             for e in events],
        **_next_transitions(st.get("status")),
        "requires_human_review": True, "is_advisory": True, "is_decision": False,
    }


def build_forward_learning_records(*, statuses: tuple[str, ...] = _TRACKED_STATUSES) -> dict:
    """추적 대상 전략 전체의 Forward Learning Record. 읽기전용 projection — 새 원장 없음, 실행 없음.

    coverage_gaps 는 STEP4-C 정신(빠진 기록 찾기) 을 이 뷰에도 반영 — 숨기지 않고 그대로 노출.
    """
    from jarvis.registry import StrategyRegistry
    rows = _safe(lambda: StrategyRegistry().all_current(), []) or []
    targets = [r["strategy_id"] for r in rows if r.get("status") in statuses]
    records = [build_record(sid) for sid in targets]

    return {"records": records, "count": len(records), "tracked_statuses": list(statuses),
            "coverage_gaps": {
                "missing_thesis": sum(1 for r in records if not r.get("thesis")),
                "missing_prediction_capture": sum(1 for r in records if not r.get("prediction_captured")),
                "missing_forward_data": sum(1 for r in records if r.get("expected_behavior") is None),
            },
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Forward Learning Record(읽기전용 projection) — registry·experiment_registry·"
                     "prediction_registry·paper.deploy 조인. 새 원장·새 schema 없음. Research OS 무변경. "
                     "실행 없음. 모든 결정은 사람.")}
