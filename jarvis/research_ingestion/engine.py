"""Research Ingestion Engine (P53) — 백테스트 결과를 연구 메모리로 흘려보내는 오케스트레이터. **실행 없음.**

완료된 백테스트(dict)를 기존 엔진 API로 기록한다:
  experiment_tracking (expt_) — 실험/실행/파라미터/결과
  research_memory_intelligence (rmi_) — 실패/성공/교훈
그 결과 research_assistant.recall/failure_intelligence/perspectives 가 실데이터로 채워진다.
**새 실험/실패 저장소를 만들지 않는다(통합). 거래·집행·배포 없음. 멱등(결정적 ID → 재수집은 no-op).**
"""
from __future__ import annotations

from jarvis.research_ingestion import ledger
from jarvis.research_ingestion import models as M
from jarvis.research_ingestion.models import (
    GENESIS,
    IngestionRecord,
    IngestionResult,
    IngestionSummary,
    SchemaError,
    content_hash,
    input_digest,
)

# 실패 카테고리별 기본 교훈(명시 lesson 없을 때)
_DEFAULT_LESSON = {
    "OVERFITTING": "인샘플 과적합 — walk-forward·OOS 우선, 파라미터 수 최소화.",
    "DATA_LEAKAGE": "룩어헤드/데이터 누설 — 피처 시점 정합 재점검.",
    "REGIME_CHANGE": "레짐 변화 취약 — regime-robust 검증·매크로 필터 요구.",
    "COST_SENSITIVITY": "거래비용 민감 — 비용 반영 백테스트·회전율 축소.",
    "LIQUIDITY": "유동성 문제 — 체결가능 규모·거래량 필터.",
    "POOR_HYPOTHESIS": "가설 약함 — 랜덤 베이스라인 대비 엣지 재확인.",
    "TIMING": "타이밍/지연 — 진입 시점 가정 재검토.",
    "RISK_CONCENTRATION": "리스크 집중 — 상관·편중 제한.",
    "PARAMETER_INSTABILITY": "파라미터 불안정 — 민감도 분석·안정 구간만 채택.",
    "UNCLASSIFIED": "실패 사유 구조화 필요 — root_cause 를 명시해 재기록.",
}


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchIngestionEngine:
    """백테스트 → 연구 메모리 오케스트레이터. 기존 엔진 재사용(주입 가능). 실행/집행 권한 없음."""

    def __init__(self, experiment_engine=None, memory_engine=None) -> None:
        self._exp = experiment_engine
        self._mem = memory_engine

    def _experiment(self):
        if self._exp is None:
            from jarvis.experiment_tracking.engine import ExperimentTrackingEngine
            self._exp = ExperimentTrackingEngine()
        return self._exp

    def _memory(self):
        if self._mem is None:
            from jarvis.research_memory_intelligence.engine import ResearchMemoryIntelligenceEngine
            self._mem = ResearchMemoryIntelligenceEngine()
        return self._mem

    def validate(self, backtest: dict) -> dict:
        return M.validate_backtest(backtest)

    def ingest(self, backtest: dict, now="", *, commit=False, strict=False) -> IngestionResult:
        """백테스트 1건 수집. 기존 원장에 기록 + 결과 판정 + 실패 자동분류. 멱등."""
        bt = backtest or {}
        v = M.validate_backtest(bt)
        if strict and not v["ok"]:
            raise SchemaError(f"필수 필드 누락: {v['missing_fields']}")
        name = str(bt.get("strategy_name", "")).strip() or "unknown_strategy"
        version = str(bt.get("strategy_version", ""))
        bt_hash = M.backtest_hash(bt)
        iid = M.ingestion_id(name, bt_hash)

        existing = ledger.ingestion_by_id(iid)
        if existing:   # 멱등: 동일 백테스트 재수집 → 기존 결과 반환
            return IngestionResult(
                ingestion_id=iid, experiment_id=existing.get("experiment_id", ""),
                run_id=existing.get("run_id", ""), outcome=existing.get("outcome", ""),
                failure_category=existing.get("failure_category", ""),
                validation_complete=existing.get("validation_complete", False),
                missing_validations=v["missing_validations"], parameters_written=0,
                results_written=0, memory_written="none", deduplicated=True)

        metrics = bt.get("metrics") or {}
        outcome = M.classify_outcome(metrics, str(bt.get("outcome", "")), v["validation_complete"])
        reason = str(bt.get("root_cause", "") or bt.get("failure_reason", ""))
        category = M.auto_classify_failure(metrics, reason) if outcome == M.OUT_FAILURE else ""

        # commit=False = 드라이런 프리뷰(기록 없음 — 판정만). 기존 원장 무변경.
        if not commit:
            return IngestionResult(
                ingestion_id=iid, experiment_id="", run_id="", outcome=outcome,
                failure_category=category, validation_complete=v["validation_complete"],
                missing_validations=v["missing_validations"], parameters_written=0,
                results_written=0, memory_written="none", deduplicated=False)

        exp = self._experiment()
        mem = self._memory()

        # 1) 실험 + 실행
        experiment = exp.create_experiment(name, objective=str(bt.get("hypothesis", "")),
                                           tags=[str(bt.get("universe", ""))], now=now, commit=commit)
        run = exp.record_run(experiment.experiment_id, code_version=version,
                             note=str(bt.get("hypothesis", "")), now=now, commit=commit)
        # 2) 파라미터(연구 컨텍스트)
        params = {
            "universe": bt.get("universe", ""), "period_start": (bt.get("period") or {}).get("start", ""),
            "period_end": (bt.get("period") or {}).get("end", ""),
            "features": ", ".join(bt.get("features", []) or []),
            "entry_rules": bt.get("entry_rules", ""), "exit_rules": bt.get("exit_rules", ""),
            "risk_rules": bt.get("risk_rules", ""), "source": bt.get("source", ""),
        }
        pcount = 0
        for k, val in params.items():
            if str(val).strip():
                exp.record_parameter(run.run_id, k, val, now=now, commit=commit)
                pcount += 1
        # 3) 결과(수치 지표)
        rcount = 0
        for metric, val in metrics.items():
            num = M._num(val)
            if num is not None:
                exp.record_result(run.run_id, metric, num, now=now, commit=commit)
                rcount += 1
        # 검증 완전성 플래그(문서 §7) — 결과로도 기록
        exp.record_result(run.run_id, "validation_complete", 1.0 if v["validation_complete"] else 0.0,
                          now=now, commit=commit)

        # 4) 결과 판정(위에서 계산됨) + 메모리
        memory_written = "none"
        lesson = str(bt.get("lesson", ""))
        if outcome == M.OUT_FAILURE:
            summary = (f"{name} {version} FAILURE [{category}] — "
                       f"{reason or 'metric-derived'} | sharpe={metrics.get('sharpe')}")
            ev = {"category": category, "root_cause": reason, "metrics": metrics,
                  "experiment_id": experiment.experiment_id}
            mem.record_failure(origin=experiment.experiment_id, summary=summary, evidence=ev,
                               now=now, commit=commit)
            mem.record_lesson(origin=experiment.experiment_id,
                              lesson=(lesson or _DEFAULT_LESSON.get(category, "")),
                              evidence={"category": category}, impact="high", now=now, commit=commit)
            memory_written = "failure"
        elif outcome == M.OUT_SUCCESS:
            summary = (f"{name} {version} SUCCESS — sharpe={metrics.get('sharpe')} "
                       f"mdd={metrics.get('max_drawdown')}")
            mem.record_success(origin=experiment.experiment_id, summary=summary,
                               evidence={"metrics": metrics}, now=now, commit=commit)
            if lesson:
                mem.record_lesson(origin=experiment.experiment_id, lesson=lesson,
                                  evidence={}, impact="medium", now=now, commit=commit)
            memory_written = "success"

        # 5) 수집 감사 기록(중복탐지·해시)
        rec = IngestionRecord(
            ingestion_id=iid, backtest_hash=bt_hash, strategy_name=name, strategy_version=version,
            experiment_id=experiment.experiment_id, run_id=run.run_id, outcome=outcome,
            failure_category=category, validation_complete=v["validation_complete"],
            metric_count=rcount, source=str(bt.get("source", "")), created_at=now,
            input_hash=input_digest(name, bt_hash), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.ingestion_exists(iid):
            head = ledger.ingestions_head()
            ledger.append_ingestion(_seal(rec, head["record_hash"] if head else GENESIS))

        return IngestionResult(
            ingestion_id=iid, experiment_id=experiment.experiment_id, run_id=run.run_id,
            outcome=outcome, failure_category=category,
            validation_complete=v["validation_complete"],
            missing_validations=v["missing_validations"], parameters_written=pcount,
            results_written=rcount, memory_written=memory_written, deduplicated=False)

    def ingest_many(self, backtests, now="", *, commit=False) -> list:
        return [self.ingest(bt, now=now, commit=commit) for bt in (backtests or [])]

    def verify_integrity(self) -> dict:
        from jarvis.research_ingestion.verify import verify_chain
        return verify_chain()

    def summary(self, now="") -> IngestionSummary:
        rows = ledger.read_ingestions()
        by_out: dict = {}
        by_cat: dict = {}
        for r in rows:
            by_out[r.get("outcome")] = by_out.get(r.get("outcome"), 0) + 1
            if r.get("failure_category"):
                by_cat[r["failure_category"]] = by_cat.get(r["failure_category"], 0) + 1
        return IngestionSummary(timestamp=now, ingestion_count=len(rows),
                                by_outcome=dict(sorted(by_out.items())),
                                by_failure_category=dict(sorted(by_cat.items())))
