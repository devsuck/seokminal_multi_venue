"""Backtest Research Bridge (P102) — Experiment Planner 를 **기존 백테스트 워크플로**에 연결한다. **자동 실행 없음.**

가설 → ExperimentSpec(P74) → BacktestResearchJob(요청/상태 추적) → (사람이 외부에서 백테스트 실행) →
결과를 backtest_adapter 로 수집(dry-run 프리뷰). **기존 백테스트 엔진 무변경 · 자동 집행 없음.** 백테스트는
외부 단계(models.EXTERNAL_STAGES)로, 이 브리지는 결과만 소비한다.

원칙(문서 §Constitution, §P102): 통합·조율만. 결정적. 거래·집행 없음. 사람 결정.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

# 잡 상태(연구 요청 상태 — 트레이딩 상태 아님)
S_CREATED = "CREATED"
S_WAITING_HUMAN = "WAITING_HUMAN"        # 사람이 외부 백테스트를 실행해야 함
S_EXTERNAL_RUNNING = "EXTERNAL_RUNNING"  # 외부 실행 중(사람 표시)
S_COMPLETED = "COMPLETED"
S_FAILED = "FAILED"
JOB_STATES = (S_CREATED, S_WAITING_HUMAN, S_EXTERNAL_RUNNING, S_COMPLETED, S_FAILED)


@dataclass(frozen=True)
class BacktestResearchJob:
    experiment_id: str
    strategy: str
    universe: str
    parameters: dict
    validation_requirements: list
    status: str
    result_summary: dict = field(default_factory=dict)
    requires_human_review: bool = True
    is_advisory: bool = True
    is_decision: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def create_job(hypothesis_or_spec, *, assistant=None) -> BacktestResearchJob:
    """가설 또는 ExperimentSpec → BacktestResearchJob(status=CREATED). 실행하지 않음 — 요청만 만든다."""
    from jarvis.research_workflow.experiment_planner import ExperimentPlanner, ExperimentSpec
    spec = hypothesis_or_spec
    if not isinstance(spec, ExperimentSpec):
        # dict/Hypothesis → plan
        spec = ExperimentPlanner().plan(hypothesis_or_spec)
    return BacktestResearchJob(
        experiment_id=spec.spec_id, strategy=spec.strategy_name, universe=spec.universe,
        parameters={"timeframe": spec.timeframe, "rebalance": spec.rebalance,
                    "features": list(spec.feature_set), "transaction_costs": spec.transaction_costs,
                    "walk_forward": spec.walk_forward, "random_baseline": spec.random_baseline},
        validation_requirements=[c["metric"] if isinstance(c, dict) else c
                                 for c in spec.validation_checklist],
        status=S_CREATED)


def submit_for_human_run(job: BacktestResearchJob) -> BacktestResearchJob:
    """잡을 사람 실행 대기로 전환(CREATED → WAITING_HUMAN). 자동 실행 없음 — 사람이 외부 백테스트를 돌린다."""
    return _with(job, status=S_WAITING_HUMAN)


def mark_running(job: BacktestResearchJob) -> BacktestResearchJob:
    """사람이 외부 백테스트를 시작했음을 표시(WAITING_HUMAN → EXTERNAL_RUNNING). Jarvis 는 실행하지 않는다."""
    return _with(job, status=S_EXTERNAL_RUNNING)


def complete_job(job: BacktestResearchJob, backtest_result: dict, *, commit: bool = False) -> dict:
    """외부 백테스트 결과 → 상태 COMPLETED/FAILED + backtest_adapter 수집(dry-run 기본). 실행·집행 없음.

    기존 backtest_adapter.ingest_backtest 로 결과를 수집(idempotent, commit=False=프리뷰). 백테스트 엔진 무변경.
    """
    try:
        from jarvis.research_ingestion.backtest_adapter import ingest_backtest
        res = ingest_backtest(backtest_result or {}, commit=commit)
        summary = res.to_dict() if hasattr(res, "to_dict") else dict(res or {})
        status = S_COMPLETED if summary.get("outcome") not in ("FAILURE", "INCOMPLETE") else S_FAILED
    except Exception as e:  # noqa: BLE001
        summary, status = {"error": str(e)}, S_FAILED
    updated = _with(job, status=status, result_summary=summary)
    return {"job": updated.to_dict(), "ingestion": summary, "committed": commit,
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": "외부 백테스트 결과 수집(기존 backtest_adapter, dry-run 기본) — 엔진 무변경, 자동 실행 없음."}


def _with(job: BacktestResearchJob, **changes) -> BacktestResearchJob:
    d = job.to_dict()
    d.update(changes)
    d.pop("requires_human_review", None)
    d.pop("is_advisory", None)
    d.pop("is_decision", None)
    return BacktestResearchJob(**d)
