"""Autonomous Experiment Designer (P184) — Hypothesis → Experiment Proposal 자동 변환. **설계만, 실행 없음.**

기존 experiment_planner(P74)를 재사용해 ExperimentSpec 을 만들고, 3개 연구 지표를 덧붙인다:
  Information Gain Score · Complexity Score · Expected Research Value.

출력 Experiment Specification: universe·timeframe·required_data·benchmark·metrics·validation_rules·
cost_assumptions·failure_conditions + 위 3지표.

원칙(문서 §Constitution, §P184): 통합·조율만 · 결정적 · 자문 전용 · 자동 백테스트 없음 · 거래·집행 없음 · 사람 결정.
"""
from __future__ import annotations

# 실패 조건(연구 사전등록 — 결정적)
_FAILURE_CONDITIONS = (
    "walk-forward 후반부 엣지 소멸",
    "비용 반영 후 net 음수",
    "랜덤 베이스라인 대비 유의성 없음(p>0.05)",
    "레짐 밖에서 붕괴",
)


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _spec(hypothesis):
    """experiment_planner 재사용 — Hypothesis/question → ExperimentSpec dict."""
    def _go():
        from jarvis.research_workflow.experiment_planner import ExperimentPlanner
        # planner 는 Hypothesis 또는 dict/문자열을 받음
        return ExperimentPlanner().plan(hypothesis).to_dict()
    return _safe(_go, {}) or {}


def _info_gain(hypothesis, spec):
    """정보 획득 = novelty × 검증 커버리지(결정적)."""
    novelty = float((hypothesis or {}).get("novelty", (hypothesis or {}).get("novelty_score", 0.5))) \
        if isinstance(hypothesis, dict) else 0.5
    checklist = spec.get("validation_checklist") or []
    coverage = min(1.0, len(checklist) / 6.0) if checklist else 0.5
    return round(0.6 * novelty + 0.4 * coverage, 4)


def _complexity(spec):
    """복잡도 = 필요 검증 수 + 피처 수(결정적, 0~1)."""
    checklist = len(spec.get("validation_checklist") or [])
    feats = len(spec.get("feature_set") or [])
    return round(min(1.0, (checklist + feats) / 12.0), 4)


def design_experiment(hypothesis) -> dict:
    """Hypothesis → Experiment Proposal(자동 변환) + 정보획득·복잡도·기대연구가치. 결정적·읽기전용.

    hypothesis: Research Hypothesis(P183) dict, Hypothesis(P73), 또는 문자열.
    """
    hyp = hypothesis
    if isinstance(hypothesis, dict) and hypothesis.get("question"):
        # P183 Research Hypothesis → planner 가 이해하는 형태로
        hyp = {"statement": hypothesis["question"],
               "hypothesis_id": hypothesis.get("hypothesis_id"),
               "expected_edge": "MEDIUM", "confidence": "MEDIUM",
               "source": "hypothesis_discovery"}
    spec = _spec(hyp)

    info_gain = _info_gain(hypothesis if isinstance(hypothesis, dict) else {}, spec)
    complexity = _complexity(spec)
    # 기대 연구 가치 = 정보획득 × (1 - 복잡도 페널티)
    expected_value = round(info_gain * (1.0 - 0.35 * complexity), 4)

    proposal = {
        "spec_id": spec.get("spec_id"),
        "hypothesis_id": spec.get("hypothesis_id"),
        "universe": spec.get("universe"),
        "timeframe": spec.get("timeframe"),
        "required_data": spec.get("feature_set", []),
        "benchmark": spec.get("random_baseline", {}) or {"type": "random_matched"},
        "metrics": spec.get("validation_checklist", []),
        "validation_rules": spec.get("walk_forward", {}),
        "cost_assumptions": spec.get("transaction_costs", {}),
        "failure_conditions": list(_FAILURE_CONDITIONS),
        "information_gain_score": info_gain,
        "complexity_score": complexity,
        "expected_research_value": expected_value,
        "requires_human_review": True, "is_advisory": True, "is_decision": False,
        "note": ("Experiment Proposal(읽기전용) — experiment_planner 재사용. 자동 백테스트 없음. "
                 "사람 검토 후 외부 실행. 거래·집행 없음.")}
    return proposal
