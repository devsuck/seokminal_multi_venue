"""Alpha Intelligence Engine (P10.3) — 신호 발견·후보 관리·평가·랭킹. **연구·기록 전용.**

신호/버전을 불변으로 등록하고 생명주기(IDEA→HYPOTHESIS→RESEARCHING→EVALUATED→VALIDATED→
ARCHIVED)·피처·가설·실험·평가·랭킹·계보를 남긴다. **trading signal 실행·주문·portfolio·자본배분·
자동 선택/배포 없음.** execution/broker/portfolio/risk import·변경 없음. Alpha score/rank 는 연구
평가값 · VALIDATED ≠ trading enabled. 외부(P9.8/P9.9/P10.1/P10.2) 데이터는 참조 문자열로만. 결정적.
"""
from __future__ import annotations

from jarvis.alpha_intelligence import ledger
from jarvis.alpha_intelligence.models import (
    ARCHIVED,
    ART_EVALUATION,
    ART_EXPERIMENT,
    ART_FEATURE,
    ART_HYPOTHESIS,
    ART_SIGNAL,
    EVALUATED,
    GENESIS,
    HYPOTHESIS,
    IDEA,
    RESEARCHING,
    VALIDATED,
    AlphaHypothesis,
    AlphaRanking,
    AlphaReport,
    FeatureDefinition,
    IllegalTransition,
    ImmutableFeatureError,
    ImmutableSignalError,
    ImmutableVersionError,
    SignalArtifact,
    SignalEvaluation,
    SignalExperiment,
    SignalMetadata,
    SignalVersion,
    artifact_id as _artifact_id,
    can_transition,
    content_hash,
    evaluation_id as _evaluation_id,
    evaluation_verdict,
    experiment_id as _experiment_id,
    feature_hash as _feature_hash,
    hypothesis_id as _hypothesis_id,
    input_digest,
    overall_score,
    performance_score,
    ranking_id as _ranking_id,
    robustness_score,
    signal_hash as _signal_hash,
    stability_score,
    version_event_id,
    version_hash as _version_hash,
    version_key as _vkey,
)


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class AlphaIntelligenceEngine:
    """alpha 지능 엔진. 불변·append-only·결정적. 실행/거래/자본배분 없음."""

    # ── 아티팩트 계보(내부) ──
    def _record_artifact(self, artifact_type: str, ref_id: str, parent_artifact: str,
                         signal_id: str, now: str, *, commit: bool) -> dict:
        aid = _artifact_id(artifact_type, ref_id)
        rec = SignalArtifact(
            artifact_id=aid, artifact_type=artifact_type, ref_id=ref_id,
            parent_artifact=parent_artifact, signal_id=signal_id, created_at=now,
            input_hash=input_digest(artifact_type, ref_id), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    # ── register_signal ──
    def register_signal(self, signal_id: str, name: str, description: str, author: str,
                        category: str, now: str = "", *, commit: bool = False) -> SignalMetadata:
        sh = _signal_hash(signal_id, name, author, category, description)
        for s in ledger.read_signals():
            if s.get("signal_id") == signal_id:
                if s.get("signal_hash") != sh:
                    raise ImmutableSignalError(f"{signal_id} 신호 불변 — 변경 불가")
                return SignalMetadata(**{k: v for k, v in s.items()
                                         if k in SignalMetadata.__dataclass_fields__})
        rec = SignalMetadata(
            signal_id=signal_id, name=name, description=description, author=author,
            category=category, created_at=now, signal_hash=sh, input_hash=sh,
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.signal_hash_exists(sh):
            head = ledger.signals_head()
            ledger.append_signal(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_SIGNAL, signal_id, "", signal_id, now, commit=commit)
        return SignalMetadata(**rec)

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
        rec = SignalVersion(
            version_id=eid, version_key=vkey, signal_id=meta["signal_id"],
            version=meta["version"], author=meta["author"],
            formula_description=meta["formula_description"], parameters=meta["parameters"],
            feature_dependencies=meta["feature_dependencies"],
            dataset_version=meta["dataset_version"], version_hash=meta["version_hash"],
            from_state=frm, to_state=to, status=to, created_at=now, actor=actor,
            input_hash=input_digest(vkey, frm, to), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.version_event_exists(eid):
            head = ledger.versions_head()
            ledger.append_version(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def create_signal_version(self, signal_id: str, version: str, author: str,
                              formula_description: str, parameters: dict,
                              feature_dependencies: list, dataset_version: str = "",
                              now: str = "", *, commit: bool = False) -> SignalVersion:
        vkey = _vkey(signal_id, version)
        vh = _version_hash(signal_id, version, formula_description, parameters,
                           feature_dependencies, dataset_version)
        existing = ledger.version_events_for(vkey)
        if existing:
            if existing[0].get("version_hash") != vh:
                raise ImmutableVersionError(f"{vkey} 버전 불변 — 내용 변경 불가")
            return SignalVersion(**existing[-1])
        meta = {"signal_id": signal_id, "version": version, "author": author,
                "formula_description": formula_description, "parameters": dict(parameters or {}),
                "feature_dependencies": list(feature_dependencies or []),
                "dataset_version": dataset_version, "version_hash": vh}
        rec = self._emit_version(vkey, meta, "", IDEA, now, actor=author, commit=commit)
        return SignalVersion(**rec)

    def _safe_advance(self, vkey: str, to: str, now: str, *, actor: str, commit: bool) -> None:
        meta = self._version_meta(vkey)
        if meta is None:
            return
        cur = self.current_state(vkey)
        if cur != to and can_transition(cur, to):
            self._emit_version(vkey, meta, cur, to, now, actor=actor, commit=commit)

    def transition(self, signal_id: str, version: str, to: str, now: str = "", *,
                   actor: str = "researcher", commit: bool = False) -> dict:
        vkey = _vkey(signal_id, version)
        meta = self._version_meta(vkey)
        if meta is None:
            raise IllegalTransition(f"미존재 버전 {vkey}")
        return self._emit_version(vkey, meta, self.current_state(vkey), to, now,
                                  actor=actor, commit=commit)

    def validate_signal(self, signal_id: str, version: str, now: str = "", *,
                        actor: str = "validator", commit: bool = False) -> dict:
        """EVALUATED→VALIDATED. **VALIDATED ≠ trading enabled(연구 상태일 뿐).**"""
        return self.transition(signal_id, version, VALIDATED, now, actor=actor, commit=commit)

    def archive_signal(self, signal_id: str, version: str, now: str = "", *,
                       actor: str = "operator", commit: bool = False) -> dict:
        return self.transition(signal_id, version, ARCHIVED, now, actor=actor, commit=commit)

    # ── register_feature ──
    def register_feature(self, feature_id: str, name: str, description: str,
                         source_dataset: str, formula: str, calculation_version: str,
                         now: str = "", *, commit: bool = False) -> FeatureDefinition:
        fh = _feature_hash(feature_id, name, source_dataset, formula, calculation_version)
        for f in ledger.read_features():
            if (f.get("feature_id") == feature_id
                    and f.get("calculation_version") == calculation_version):
                if f.get("feature_hash") != fh:
                    raise ImmutableFeatureError(f"{feature_id} 피처 불변")
                return FeatureDefinition(**{k: v for k, v in f.items()
                                            if k in FeatureDefinition.__dataclass_fields__})
        rec = FeatureDefinition(
            feature_hash=fh, feature_id=feature_id, name=name, description=description,
            source_dataset=source_dataset, formula=formula,
            calculation_version=calculation_version, created_at=now, input_hash=fh,
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.feature_hash_exists(fh):
            head = ledger.features_head()
            ledger.append_feature(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_FEATURE, feature_id, "", "", now, commit=commit)
        return FeatureDefinition(**rec)

    # ── create_hypothesis (IDEA→HYPOTHESIS) ──
    def create_hypothesis(self, signal_id: str, version: str, statement: str,
                          rationale: str = "", now: str = "",
                          *, commit: bool = False) -> AlphaHypothesis:
        hid = _hypothesis_id(signal_id, statement)
        rec = AlphaHypothesis(
            hypothesis_id=hid, signal_id=signal_id, version=version, statement=statement,
            rationale=rationale, created_at=now, input_hash=input_digest(signal_id, statement),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.hypothesis_exists(hid):
            head = ledger.hypotheses_head()
            ledger.append_hypothesis(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_HYPOTHESIS, hid, _artifact_id(ART_SIGNAL, signal_id),
                              signal_id, now, commit=commit)
        self._safe_advance(_vkey(signal_id, version), HYPOTHESIS, now, actor="researcher",
                           commit=commit)
        return AlphaHypothesis(**rec)

    # ── create_experiment (HYPOTHESIS→RESEARCHING) ──
    def create_experiment(self, signal_id: str, version: str, hypothesis_id: str, *,
                          feature_dependencies: list | None = None, dataset_version: str = "",
                          parameters: dict | None = None, evaluation_period: str = "",
                          benchmark: str = "", now: str = "",
                          commit: bool = False) -> SignalExperiment:
        vkey = _vkey(signal_id, version)
        params = dict(parameters or {})
        ph = input_digest(sorted(params.items()))
        eid = _experiment_id(vkey, hypothesis_id, ph, evaluation_period)
        rec = SignalExperiment(
            experiment_id=eid, signal_id=signal_id, version=version, hypothesis_id=hypothesis_id,
            feature_dependencies=list(feature_dependencies or []), dataset_version=dataset_version,
            parameters=params, evaluation_period=evaluation_period, benchmark=benchmark,
            created_at=now, input_hash=input_digest(vkey, hypothesis_id, ph, evaluation_period),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.experiment_exists(eid):
            head = ledger.experiments_head()
            ledger.append_experiment(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = _artifact_id(ART_HYPOTHESIS, hypothesis_id)
        self._record_artifact(ART_EXPERIMENT, eid, parent, signal_id, now, commit=commit)
        self._safe_advance(vkey, RESEARCHING, now, actor="researcher", commit=commit)
        return SignalExperiment(**rec)

    # ── record_evaluation (RESEARCHING→EVALUATED) ──
    def record_evaluation(self, experiment_id: str, performance: dict, robustness: dict,
                          now: str = "", *, commit: bool = False) -> SignalEvaluation:
        exp = ledger.get_experiment(experiment_id)
        signal_id = exp.get("signal_id", "") if exp else ""
        sharpe = float(performance.get("sharpe", 0.0))
        verdict = evaluation_verdict(robustness, sharpe)
        mh = input_digest(sorted(performance.items()), sorted(robustness.items()))
        vid = _evaluation_id(experiment_id, mh)
        rec = SignalEvaluation(
            evaluation_id=vid, experiment_id=experiment_id, signal_id=signal_id,
            performance=dict(performance), robustness=dict(robustness), verdict=verdict,
            created_at=now, input_hash=mh, previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.evaluation_exists(vid):
            head = ledger.evaluations_head()
            ledger.append_evaluation(_seal(rec, head["record_hash"] if head else GENESIS))
        if exp:
            self._record_artifact(ART_EVALUATION, vid, _artifact_id(ART_EXPERIMENT, experiment_id),
                                  signal_id, now, commit=commit)
            self._safe_advance(_vkey(exp["signal_id"], exp["version"]), EVALUATED, now,
                               actor="evaluator", commit=commit)
        return SignalEvaluation(**rec)

    # ── rank_signals (연구 평가값 — 자동 선택/배포 없음) ──
    def _derive_scores(self) -> list:
        """신호별 최신 평가 → 점수(결정적)."""
        latest: dict = {}
        for v in ledger.read_evaluations():
            latest[v.get("signal_id")] = v   # 파일 순서상 마지막이 최신
        out = []
        for sid, ev in sorted(latest.items()):
            perf = ev.get("performance", {})
            rob = ev.get("robustness", {})
            ps = performance_score(float(perf.get("sharpe", 0.0)))
            rs = robustness_score(rob)
            ss = stability_score(float(perf.get("max_drawdown", 0.0)),
                                 float(perf.get("volatility", 0.0)))
            out.append({"signal_id": sid, "performance_score": ps, "robustness_score": rs,
                        "stability_score": ss})
        return out

    def rank_signals(self, now: str = "", *, scores: list | None = None,
                     commit: bool = False) -> AlphaRanking:
        scores = scores if scores is not None else self._derive_scores()
        ranked = []
        for s in scores:
            ov = overall_score(int(s["performance_score"]), int(s["robustness_score"]),
                               int(s["stability_score"]))
            ranked.append({**s, "overall_score": ov})
        # 결정적 정렬: overall desc, signal_id asc
        ranked.sort(key=lambda x: (-x["overall_score"], x["signal_id"]))
        for i, r in enumerate(ranked):
            r["rank"] = i + 1
        ih = input_digest([(r["signal_id"], r["overall_score"]) for r in ranked])
        rid = _ranking_id(ih)
        rec = AlphaRanking(ranking_id=rid, timestamp=now, rankings=ranked, input_hash=ih,
                           previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.ranking_exists(rid):
            head = ledger.rankings_head()
            ledger.append_ranking(_seal(rec, head["record_hash"] if head else GENESIS))
        return AlphaRanking(**rec)

    # ── generate_alpha_report ──
    def generate_alpha_report(self, now: str = "") -> AlphaReport:
        signals = {s.get("signal_id") for s in ledger.read_signals()}
        vkeys = {r.get("version_key") for r in ledger.read_versions()}
        dist: dict = {}
        for vk in vkeys:
            st = self.current_state(vk)
            dist[st] = dist.get(st, 0) + 1
        evs = ledger.read_evaluations()
        ep = sum(1 for v in evs if v.get("verdict") == "PASS")
        ew = sum(1 for v in evs if v.get("verdict") == "WARNING")
        ef = sum(1 for v in evs if v.get("verdict") == "FAILED")
        return AlphaReport(
            timestamp=now, signal_count=len(signals), version_count=len(vkeys),
            state_distribution=dict(sorted(dist.items())),
            feature_count=len(ledger.read_features()),
            hypothesis_count=len(ledger.read_hypotheses()),
            experiment_count=len(ledger.read_experiments()), evaluation_count=len(evs),
            evaluation_pass=ep, evaluation_warning=ew, evaluation_failed=ef,
            ranking_count=len(ledger.read_rankings()))
