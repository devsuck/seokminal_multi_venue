"""Research Governance Engine (P10.2) — 전략 연구·실험·검증 관리. **실행/거래/자본배분 없음.**

전략/버전을 불변으로 등록하고 생명주기(DRAFT→RESEARCHING→BACKTESTED→VALIDATED→REVIEWED→
ARCHIVED)를 관리하며 가설·실험·백테스트·검증·비교·아티팩트 계보를 남긴다. **주문 생성·전략 실행·
자본 배분·live trading·자동 승인 없음.** execution/broker/portfolio/risk import 없음. VALIDATED 는
연구 상태일 뿐 trading permission 아님. 외부(P9.8/P9.9/P10.1) 데이터는 참조 문자열로만. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.research_governance import ledger
from jarvis.research_governance.models import (
    ARCHIVED,
    ART_BACKTEST,
    ART_COMPARISON,
    ART_EXPERIMENT,
    ART_STRATEGY,
    ART_VALIDATION,
    BACKTESTED,
    DRAFT,
    GENESIS,
    RESEARCHING,
    REVIEWED,
    VALIDATED,
    BacktestRecord,
    ExperimentComparison,
    ExperimentRun,
    ImmutableStrategyError,
    ImmutableVersionError,
    ResearchArtifact,
    ResearchGovernanceReport,
    ResearchHypothesis,
    StrategyMetadata,
    StrategyVersion,
    ValidationReport,
    artifact_id as _artifact_id,
    backtest_id as _backtest_id,
    can_transition,
    comparison_id as _comparison_id,
    comparison_recommendation,
    content_hash,
    experiment_id as _experiment_id,
    hypothesis_id as _hypothesis_id,
    input_digest,
    validation_report_id,
    validation_status,
    version_event_id,
    version_hash as _version_hash,
    version_key as _vkey,
    IllegalTransition,
)


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchGovernanceEngine:
    """연구 거버넌스 엔진. 불변·append-only·결정적. 실행/거래/자본배분 없음."""

    # ── 아티팩트 계보(내부) ──
    def _record_artifact(self, artifact_type: str, ref_id: str, parent_artifact: str,
                         strategy_id: str, now: str, *, commit: bool) -> dict:
        aid = _artifact_id(artifact_type, ref_id)
        rec = ResearchArtifact(
            artifact_id=aid, artifact_type=artifact_type, ref_id=ref_id,
            parent_artifact=parent_artifact, strategy_id=strategy_id, created_at=now,
            input_hash=input_digest(artifact_type, ref_id), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    # ── register_strategy ──
    def register_strategy(self, strategy_id: str, name: str, description: str, author: str,
                          asset_class: str, now: str = "",
                          *, commit: bool = False) -> StrategyMetadata:
        from jarvis.research_governance.models import strategy_hash as _sh
        sh = _sh(strategy_id, name, author, asset_class, description)
        for s in ledger.read_strategies():
            if s.get("strategy_id") == strategy_id:
                if s.get("strategy_hash") != sh:
                    raise ImmutableStrategyError(f"{strategy_id} 전략 불변 — 변경 불가")
                return StrategyMetadata(**{k: v for k, v in s.items()
                                           if k in StrategyMetadata.__dataclass_fields__})
        rec = StrategyMetadata(
            strategy_id=strategy_id, name=name, description=description, author=author,
            asset_class=asset_class, created_at=now, strategy_hash=sh, input_hash=sh,
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.strategy_hash_exists(sh):
            head = ledger.strategies_head()
            ledger.append_strategy(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_STRATEGY, strategy_id, "", strategy_id, now, commit=commit)
        return StrategyMetadata(**rec)

    # ── 버전 생명주기(이벤트 소싱) ──
    def _version_meta(self, vkey: str) -> dict | None:
        evs = ledger.version_events_for(vkey)
        return evs[0] if evs else None

    def current_state(self, vkey: str) -> str:
        evs = ledger.version_events_for(vkey)
        return evs[-1].get("to_state", "") if evs else ""

    def _emit_version(self, vkey: str, meta: dict, frm: str, to: str, now: str,
                      *, actor: str, commit: bool) -> dict:
        if not can_transition(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단")
        eid = version_event_id(vkey, frm, to)
        rec = StrategyVersion(
            version_id=eid, version_key=vkey, strategy_id=meta["strategy_id"],
            version=meta["version"], author=meta["author"], parameters=meta["parameters"],
            dataset_version=meta["dataset_version"], feature_version=meta["feature_version"],
            model_version=meta["model_version"], version_hash=meta["version_hash"],
            from_state=frm, to_state=to, status=to, created_at=now, actor=actor,
            input_hash=input_digest(vkey, frm, to), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.version_event_exists(eid):
            head = ledger.versions_head()
            ledger.append_version(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def create_version(self, strategy_id: str, version: str, author: str, parameters: dict,
                       dataset_version: str = "", feature_version: str = "",
                       model_version: str = "", now: str = "",
                       *, commit: bool = False) -> StrategyVersion:
        vkey = _vkey(strategy_id, version)
        vh = _version_hash(strategy_id, version, parameters, dataset_version, feature_version,
                           model_version)
        existing = ledger.version_events_for(vkey)
        if existing:
            if existing[0].get("version_hash") != vh:
                raise ImmutableVersionError(f"{vkey} 버전 불변 — 내용 변경 불가")
            return StrategyVersion(**existing[-1])
        meta = {"strategy_id": strategy_id, "version": version, "author": author,
                "parameters": dict(parameters or {}), "dataset_version": dataset_version,
                "feature_version": feature_version, "model_version": model_version,
                "version_hash": vh}
        rec = self._emit_version(vkey, meta, "", DRAFT, now, actor=author, commit=commit)
        return StrategyVersion(**rec)

    def _safe_advance(self, vkey: str, to: str, now: str, *, actor: str, commit: bool) -> None:
        """연구 진행에 따른 관용 전이(불가 시 no-op — 다중 실험 허용)."""
        meta = self._version_meta(vkey)
        if meta is None:
            return
        cur = self.current_state(vkey)
        if cur != to and can_transition(cur, to):
            self._emit_version(vkey, meta, cur, to, now, actor=actor, commit=commit)

    def transition(self, strategy_id: str, version: str, to: str, now: str = "", *,
                   actor: str = "reviewer", commit: bool = False) -> dict:
        """명시적 전이(가드 강제). 차단 전이는 IllegalTransition."""
        vkey = _vkey(strategy_id, version)
        meta = self._version_meta(vkey)
        if meta is None:
            raise IllegalTransition(f"미존재 버전 {vkey}")
        return self._emit_version(vkey, meta, self.current_state(vkey), to, now,
                                  actor=actor, commit=commit)

    def review_strategy(self, strategy_id: str, version: str, now: str = "", *,
                        actor: str = "reviewer", commit: bool = False) -> dict:
        return self.transition(strategy_id, version, REVIEWED, now, actor=actor, commit=commit)

    def archive_strategy(self, strategy_id: str, version: str, now: str = "", *,
                         actor: str = "operator", commit: bool = False) -> dict:
        return self.transition(strategy_id, version, ARCHIVED, now, actor=actor, commit=commit)

    # ── create_experiment (가설 + 실험, DRAFT→RESEARCHING) ──
    def create_experiment(self, strategy_id: str, version: str, hypothesis: str, *,
                          rationale: str = "", dataset_version: str = "",
                          feature_version: str = "", model_version: str = "",
                          parameters: dict | None = None, backtest_period: str = "",
                          cost_assumption: dict | None = None, benchmark: str = "",
                          now: str = "", commit: bool = False) -> ExperimentRun:
        vkey = _vkey(strategy_id, version)
        hyp_id = _hypothesis_id(strategy_id, hypothesis)
        params = dict(parameters or {})
        ph = input_digest(sorted(params.items()))
        eid = _experiment_id(vkey, hyp_id, ph, backtest_period)
        rec = ExperimentRun(
            experiment_id=eid, strategy_id=strategy_id, version=version, hypothesis_id=hyp_id,
            hypothesis=hypothesis, dataset_version=dataset_version, feature_version=feature_version,
            model_version=model_version, parameters=params, backtest_period=backtest_period,
            cost_assumption=dict(cost_assumption or {}), benchmark=benchmark, created_at=now,
            input_hash=input_digest(vkey, hyp_id, ph, backtest_period),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.experiment_exists(eid):
            head = ledger.experiments_head()
            ledger.append_experiment(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_EXPERIMENT, eid, _artifact_id(ART_STRATEGY, strategy_id),
                              strategy_id, now, commit=commit)
        self._safe_advance(vkey, RESEARCHING, now, actor="researcher", commit=commit)
        return ExperimentRun(**rec)

    def hypothesis(self, strategy_id: str, statement: str, rationale: str = "",
                   now: str = "") -> ResearchHypothesis:
        return ResearchHypothesis(hypothesis_id=_hypothesis_id(strategy_id, statement),
                                  strategy_id=strategy_id, statement=statement,
                                  rationale=rationale, created_at=now)

    # ── record_backtest (RESEARCHING→BACKTESTED) ──
    def record_backtest(self, experiment_id: str, *, total_return: float = 0.0,
                        volatility: float = 0.0, sharpe: float = 0.0, max_drawdown: float = 0.0,
                        turnover: float = 0.0, benchmark_comparison: dict | None = None,
                        backtest_period: str = "", cost_assumption: dict | None = None,
                        result_summary: str = "", now: str = "",
                        commit: bool = False) -> BacktestRecord:
        mh = input_digest(total_return, volatility, sharpe, max_drawdown, turnover)
        bid = _backtest_id(experiment_id, mh)
        rec = BacktestRecord(
            backtest_id=bid, experiment_id=experiment_id, total_return=float(total_return),
            volatility=float(volatility), sharpe=float(sharpe), max_drawdown=float(max_drawdown),
            turnover=float(turnover), benchmark_comparison=dict(benchmark_comparison or {}),
            backtest_period=backtest_period, cost_assumption=dict(cost_assumption or {}),
            result_summary=result_summary, created_at=now, input_hash=mh,
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.backtest_exists(bid):
            head = ledger.backtests_head()
            ledger.append_backtest(_seal(rec, head["record_hash"] if head else GENESIS))
        exp = ledger.get_experiment(experiment_id)
        if exp:
            self._record_artifact(ART_BACKTEST, bid, _artifact_id(ART_EXPERIMENT, experiment_id),
                                  exp.get("strategy_id", ""), now, commit=commit)
            self._safe_advance(_vkey(exp["strategy_id"], exp["version"]), BACKTESTED, now,
                               actor="researcher", commit=commit)
        return BacktestRecord(**rec)

    # ── record_validation (BACKTESTED→VALIDATED) ──
    def record_validation(self, experiment_id: str, checks: dict, now: str = "",
                          *, commit: bool = False) -> ValidationReport:
        status = validation_status(checks)
        ch = input_digest(sorted((k, str(v)) for k, v in checks.items()))
        rid = validation_report_id(experiment_id, ch)
        rec = ValidationReport(
            report_id=rid, experiment_id=experiment_id, checks=dict(checks),
            validation_status=status, created_at=now, input_hash=ch,
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.validation_exists(rid):
            head = ledger.validations_head()
            ledger.append_validation(_seal(rec, head["record_hash"] if head else GENESIS))
        exp = ledger.get_experiment(experiment_id)
        if exp:
            self._record_artifact(ART_VALIDATION, rid, _artifact_id(ART_EXPERIMENT, experiment_id),
                                  exp.get("strategy_id", ""), now, commit=commit)
            # VALIDATED = 연구 결과 상태(거래 인가 아님)
            self._safe_advance(_vkey(exp["strategy_id"], exp["version"]), VALIDATED, now,
                               actor="validator", commit=commit)
        return ValidationReport(**rec)

    # ── compare_experiments (기록만 — 자동 선택 아님) ──
    def compare_experiments(self, experiment_a: str, experiment_b: str, now: str = "",
                            *, commit: bool = False) -> ExperimentComparison:
        def _metrics(eid):
            bts = ledger.backtests_for(eid)
            if not bts:
                return {"sharpe": 0.0, "total_return": 0.0, "volatility": 0.0,
                        "max_drawdown": 0.0, "turnover": 0.0}
            b = bts[-1]
            return {"sharpe": b.get("sharpe", 0.0), "total_return": b.get("total_return", 0.0),
                    "volatility": b.get("volatility", 0.0), "max_drawdown": b.get("max_drawdown", 0.0),
                    "turnover": b.get("turnover", 0.0)}

        ma, mb = _metrics(experiment_a), _metrics(experiment_b)
        deltas = {k: round(float(ma[k]) - float(mb[k]), 8) for k in ma}
        rec_label = comparison_recommendation(ma["sharpe"], mb["sharpe"])
        cid = _comparison_id(experiment_a, experiment_b)
        rec = ExperimentComparison(
            comparison_id=cid, experiment_a=experiment_a, experiment_b=experiment_b,
            metrics_a=ma, metrics_b=mb, deltas=deltas, recommendation=rec_label, created_at=now,
            input_hash=input_digest(experiment_a, experiment_b), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.comparison_exists(cid):
            head = ledger.comparisons_head()
            ledger.append_comparison(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_COMPARISON, cid, "", "", now, commit=commit)
        return ExperimentComparison(**rec)

    # ── generate_research_report ──
    def generate_research_report(self, now: str = "") -> ResearchGovernanceReport:
        strategies = {s.get("strategy_id") for s in ledger.read_strategies()}
        vkeys = {r.get("version_key") for r in ledger.read_versions()}
        dist: dict = {}
        for vk in vkeys:
            st = self.current_state(vk)
            dist[st] = dist.get(st, 0) + 1
        vals = ledger.read_validations()
        vp = sum(1 for v in vals if v.get("validation_status") == "PASS")
        vw = sum(1 for v in vals if v.get("validation_status") == "WARNING")
        vf = sum(1 for v in vals if v.get("validation_status") == "FAILED")
        return ResearchGovernanceReport(
            timestamp=now, strategy_count=len(strategies), version_count=len(vkeys),
            state_distribution=dict(sorted(dist.items())),
            experiment_count=len(ledger.read_experiments()),
            backtest_count=len(ledger.read_backtests()), validation_count=len(vals),
            validation_pass=vp, validation_warning=vw, validation_failed=vf,
            comparison_count=len(ledger.read_comparisons()))
