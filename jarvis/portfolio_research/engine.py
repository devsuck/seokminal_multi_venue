"""Portfolio Research Engine (P10.4) — 포트폴리오 구성 연구·백테스트·리스크 분석. **연구·기록 전용.**

포트폴리오/버전을 불변으로 등록하고 생명주기(DRAFT→CONSTRUCTED→BACKTESTED→RISK_ANALYZED→
VALIDATED→ARCHIVED)·가설·구성연구(이론적 가중치)·백테스트·리스크분석·비교·계보를 남긴다.
**실제 자본 배분·주문·portfolio mutation·live trading·자동 배포 없음.** execution/broker/risk import·
변경 없음. allocation study 는 이론적 가중치 · VALIDATED ≠ deployment. 외부(P9.8~P10.3) 데이터는 참조
문자열로만. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.portfolio_research import ledger
from jarvis.portfolio_research.models import (
    ARCHIVED,
    ART_BACKTEST,
    ART_CONSTRUCTION,
    ART_HYPOTHESIS,
    ART_PORTFOLIO,
    ART_RISK,
    BACKTESTED,
    CONSTRUCTED,
    DRAFT,
    GENESIS,
    RISK_ANALYZED,
    VALIDATED,
    ConstructionStudy,
    IllegalTransition,
    ImmutablePortfolioError,
    ImmutableVersionError,
    PortfolioArtifact,
    PortfolioBacktest,
    PortfolioComparison,
    PortfolioHypothesis,
    PortfolioMetadata,
    PortfolioResearchReport,
    PortfolioVersion,
    RiskAnalysis,
    artifact_id as _artifact_id,
    backtest_id as _backtest_id,
    can_transition,
    comparison_id as _comparison_id,
    comparison_recommendation,
    concentration_hhi,
    content_hash,
    hypothesis_id as _hypothesis_id,
    input_digest,
    normalize_weights,
    portfolio_hash as _portfolio_hash,
    risk_analysis_id as _risk_analysis_id,
    risk_verdict,
    study_id as _study_id,
    version_event_id,
    version_hash as _version_hash,
    version_key as _vkey,
)


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class PortfolioResearchEngine:
    """포트폴리오 연구 엔진. 불변·append-only·결정적. 실제 배분/실행/거래 없음."""

    # ── 아티팩트 계보(내부) ──
    def _record_artifact(self, artifact_type: str, ref_id: str, parent_artifact: str,
                         portfolio_id: str, now: str, *, commit: bool) -> dict:
        aid = _artifact_id(artifact_type, ref_id)
        rec = PortfolioArtifact(
            artifact_id=aid, artifact_type=artifact_type, ref_id=ref_id,
            parent_artifact=parent_artifact, portfolio_id=portfolio_id, created_at=now,
            input_hash=input_digest(artifact_type, ref_id), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    # ── register_portfolio ──
    def register_portfolio(self, portfolio_id: str, name: str, description: str, author: str,
                           objective: str, now: str = "",
                           *, commit: bool = False) -> PortfolioMetadata:
        ph = _portfolio_hash(portfolio_id, name, author, objective, description)
        for p in ledger.read_portfolios():
            if p.get("portfolio_id") == portfolio_id:
                if p.get("portfolio_hash") != ph:
                    raise ImmutablePortfolioError(f"{portfolio_id} 포트폴리오 연구 불변 — 변경 불가")
                return PortfolioMetadata(**{k: v for k, v in p.items()
                                            if k in PortfolioMetadata.__dataclass_fields__})
        rec = PortfolioMetadata(
            portfolio_id=portfolio_id, name=name, description=description, author=author,
            objective=objective, created_at=now, portfolio_hash=ph, input_hash=ph,
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.portfolio_hash_exists(ph):
            head = ledger.portfolios_head()
            ledger.append_portfolio(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_PORTFOLIO, portfolio_id, "", portfolio_id, now, commit=commit)
        return PortfolioMetadata(**rec)

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
        rec = PortfolioVersion(
            version_id=eid, version_key=vkey, portfolio_id=meta["portfolio_id"],
            version=meta["version"], author=meta["author"],
            construction_method=meta["construction_method"],
            signal_universe=meta["signal_universe"], constraints=meta["constraints"],
            dataset_version=meta["dataset_version"], version_hash=meta["version_hash"],
            from_state=frm, to_state=to, status=to, created_at=now, actor=actor,
            input_hash=input_digest(vkey, frm, to), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.version_event_exists(eid):
            head = ledger.versions_head()
            ledger.append_version(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def create_version(self, portfolio_id: str, version: str, author: str,
                       construction_method: str, signal_universe: list,
                       constraints: dict | None = None, dataset_version: str = "",
                       now: str = "", *, commit: bool = False) -> PortfolioVersion:
        vkey = _vkey(portfolio_id, version)
        constraints = dict(constraints or {})
        vh = _version_hash(portfolio_id, version, construction_method, signal_universe,
                           constraints, dataset_version)
        existing = ledger.version_events_for(vkey)
        if existing:
            if existing[0].get("version_hash") != vh:
                raise ImmutableVersionError(f"{vkey} 버전 불변 — 내용 변경 불가")
            return PortfolioVersion(**existing[-1])
        meta = {"portfolio_id": portfolio_id, "version": version, "author": author,
                "construction_method": construction_method,
                "signal_universe": list(signal_universe or []), "constraints": constraints,
                "dataset_version": dataset_version, "version_hash": vh}
        rec = self._emit_version(vkey, meta, "", DRAFT, now, actor=author, commit=commit)
        return PortfolioVersion(**rec)

    def _safe_advance(self, vkey: str, to: str, now: str, *, actor: str, commit: bool) -> None:
        meta = self._version_meta(vkey)
        if meta is None:
            return
        cur = self.current_state(vkey)
        if cur != to and can_transition(cur, to):
            self._emit_version(vkey, meta, cur, to, now, actor=actor, commit=commit)

    def transition(self, portfolio_id: str, version: str, to: str, now: str = "", *,
                   actor: str = "researcher", commit: bool = False) -> dict:
        vkey = _vkey(portfolio_id, version)
        meta = self._version_meta(vkey)
        if meta is None:
            raise IllegalTransition(f"미존재 버전 {vkey}")
        return self._emit_version(vkey, meta, self.current_state(vkey), to, now,
                                  actor=actor, commit=commit)

    def validate_portfolio(self, portfolio_id: str, version: str, now: str = "", *,
                           actor: str = "validator", commit: bool = False) -> dict:
        """RISK_ANALYZED→VALIDATED. **VALIDATED ≠ deployment(연구 상태일 뿐).**"""
        return self.transition(portfolio_id, version, VALIDATED, now, actor=actor, commit=commit)

    def archive_portfolio(self, portfolio_id: str, version: str, now: str = "", *,
                          actor: str = "operator", commit: bool = False) -> dict:
        return self.transition(portfolio_id, version, ARCHIVED, now, actor=actor, commit=commit)

    # ── create_hypothesis ──
    def create_hypothesis(self, portfolio_id: str, version: str, statement: str,
                          rationale: str = "", now: str = "",
                          *, commit: bool = False) -> PortfolioHypothesis:
        hid = _hypothesis_id(portfolio_id, statement)
        rec = PortfolioHypothesis(
            hypothesis_id=hid, portfolio_id=portfolio_id, version=version, statement=statement,
            rationale=rationale, created_at=now, input_hash=input_digest(portfolio_id, statement),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.hypothesis_exists(hid):
            head = ledger.hypotheses_head()
            ledger.append_hypothesis(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_HYPOTHESIS, hid, _artifact_id(ART_PORTFOLIO, portfolio_id),
                              portfolio_id, now, commit=commit)
        return PortfolioHypothesis(**rec)

    # ── record_construction (DRAFT→CONSTRUCTED) — 이론적 가중치 ──
    def record_construction(self, portfolio_id: str, version: str, method: str, weights: dict,
                            rebalance_frequency: str = "monthly", now: str = "",
                            *, commit: bool = False) -> ConstructionStudy:
        vkey = _vkey(portfolio_id, version)
        norm = normalize_weights(weights)
        conc = concentration_hhi(weights)
        wh = input_digest(sorted(norm.items()))
        sid = _study_id(vkey, method, wh)
        rec = ConstructionStudy(
            study_id=sid, portfolio_id=portfolio_id, version=version, method=method,
            weights=norm, rebalance_frequency=rebalance_frequency, concentration=conc,
            created_at=now, input_hash=input_digest(vkey, method, wh),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.study_exists(sid):
            head = ledger.studies_head()
            ledger.append_study(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_CONSTRUCTION, sid, _artifact_id(ART_PORTFOLIO, portfolio_id),
                              portfolio_id, now, commit=commit)
        self._safe_advance(vkey, CONSTRUCTED, now, actor="researcher", commit=commit)
        return ConstructionStudy(**rec)

    # ── record_backtest (CONSTRUCTED→BACKTESTED) ──
    def record_backtest(self, study_id: str, *, total_return: float = 0.0,
                        volatility: float = 0.0, sharpe: float = 0.0, max_drawdown: float = 0.0,
                        turnover: float = 0.0, diversification: float = 0.0,
                        benchmark_comparison: dict | None = None, period: str = "",
                        now: str = "", commit: bool = False) -> PortfolioBacktest:
        study = ledger.get_study(study_id)
        portfolio_id = study.get("portfolio_id", "") if study else ""
        mh = input_digest(total_return, volatility, sharpe, max_drawdown, turnover)
        bid = _backtest_id(study_id, mh)
        rec = PortfolioBacktest(
            backtest_id=bid, study_id=study_id, portfolio_id=portfolio_id,
            total_return=float(total_return), volatility=float(volatility), sharpe=float(sharpe),
            max_drawdown=float(max_drawdown), turnover=float(turnover),
            diversification=float(diversification),
            benchmark_comparison=dict(benchmark_comparison or {}), period=period, created_at=now,
            input_hash=mh, previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.backtest_exists(bid):
            head = ledger.backtests_head()
            ledger.append_backtest(_seal(rec, head["record_hash"] if head else GENESIS))
        if study:
            self._record_artifact(ART_BACKTEST, bid, _artifact_id(ART_CONSTRUCTION, study_id),
                                  portfolio_id, now, commit=commit)
            self._safe_advance(_vkey(study["portfolio_id"], study["version"]), BACKTESTED, now,
                               actor="researcher", commit=commit)
        return PortfolioBacktest(**rec)

    # ── record_risk_analysis (BACKTESTED→RISK_ANALYZED) ──
    def record_risk_analysis(self, study_id: str, metrics: dict, now: str = "",
                             *, commit: bool = False) -> RiskAnalysis:
        study = ledger.get_study(study_id)
        portfolio_id = study.get("portfolio_id", "") if study else ""
        verdict = risk_verdict(metrics)
        mh = input_digest(sorted((k, str(v)) for k, v in metrics.items()))
        aid = _risk_analysis_id(study_id, mh)
        rec = RiskAnalysis(
            analysis_id=aid, study_id=study_id, portfolio_id=portfolio_id, metrics=dict(metrics),
            risk_verdict=verdict, created_at=now, input_hash=mh, previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.risk_exists(aid):
            head = ledger.risk_head()
            ledger.append_risk(_seal(rec, head["record_hash"] if head else GENESIS))
        if study:
            # 리스크 분석 아티팩트는 CONSTRUCTION 을 부모로(백테스트와 형제) — 계보 트리 무결.
            self._record_artifact(ART_RISK, aid, _artifact_id(ART_CONSTRUCTION, study_id),
                                  portfolio_id, now, commit=commit)
            self._safe_advance(_vkey(study["portfolio_id"], study["version"]), RISK_ANALYZED,
                               now, actor="risk_researcher", commit=commit)
        return RiskAnalysis(**rec)

    # ── compare_portfolios (기록만 — 자동 선택 아님) ──
    def compare_portfolios(self, portfolio_a: str, portfolio_b: str, now: str = "",
                           *, commit: bool = False) -> PortfolioComparison:
        def _metrics(pid):
            bts = ledger.backtests_for_portfolio(pid)
            if not bts:
                return {"sharpe": 0.0, "total_return": 0.0, "volatility": 0.0,
                        "max_drawdown": 0.0, "diversification": 0.0}
            b = bts[-1]
            return {"sharpe": b.get("sharpe", 0.0), "total_return": b.get("total_return", 0.0),
                    "volatility": b.get("volatility", 0.0), "max_drawdown": b.get("max_drawdown", 0.0),
                    "diversification": b.get("diversification", 0.0)}

        ma, mb = _metrics(portfolio_a), _metrics(portfolio_b)
        deltas = {k: round(float(ma[k]) - float(mb[k]), 8) for k in ma}
        rec_label = comparison_recommendation(ma["sharpe"], mb["sharpe"])
        cid = _comparison_id(portfolio_a, portfolio_b)
        rec = PortfolioComparison(
            comparison_id=cid, portfolio_a=portfolio_a, portfolio_b=portfolio_b, metrics_a=ma,
            metrics_b=mb, deltas=deltas, recommendation=rec_label, created_at=now,
            input_hash=input_digest(portfolio_a, portfolio_b), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.comparison_exists(cid):
            head = ledger.comparisons_head()
            ledger.append_comparison(_seal(rec, head["record_hash"] if head else GENESIS))
        return PortfolioComparison(**rec)

    # ── generate_portfolio_report ──
    def generate_portfolio_report(self, now: str = "") -> PortfolioResearchReport:
        portfolios = {p.get("portfolio_id") for p in ledger.read_portfolios()}
        vkeys = {r.get("version_key") for r in ledger.read_versions()}
        dist: dict = {}
        for vk in vkeys:
            st = self.current_state(vk)
            dist[st] = dist.get(st, 0) + 1
        risks = ledger.read_risk()
        rp = sum(1 for r in risks if r.get("risk_verdict") == "PASS")
        rw = sum(1 for r in risks if r.get("risk_verdict") == "WARNING")
        rf = sum(1 for r in risks if r.get("risk_verdict") == "FAILED")
        return PortfolioResearchReport(
            timestamp=now, portfolio_count=len(portfolios), version_count=len(vkeys),
            state_distribution=dict(sorted(dist.items())),
            hypothesis_count=len(ledger.read_hypotheses()),
            construction_count=len(ledger.read_studies()),
            backtest_count=len(ledger.read_backtests()), risk_analysis_count=len(risks),
            risk_pass=rp, risk_warning=rw, risk_failed=rf,
            comparison_count=len(ledger.read_comparisons()))
