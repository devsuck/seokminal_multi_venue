"""P11.5 AI Research Reviewer 테스트. **연구 품질 AI 비평/리뷰어 — 평가·기록 전용.**

리뷰 생성(5차원·결정적 평결·불변)·비평(차원·심각도·불변)·증거(연결·종류·불변)·리포트(불변·is_decision=False)·
평결 순수함수(PASS/WARNING/REJECT_RESEARCH)·verify(체인/변조/중복/증거연결/평결결정성/자동결정없음)·replay·CLI·
보안(금지import·자동 결정/승인/삭제 없음·연구거부≠전략삭제·삭제 API 없음·불변·REVIEW≠DECISION·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import json
import os

import pytest

from jarvis.research_reviewer import ledger
from jarvis.research_reviewer import models as M
from jarvis.research_reviewer.engine import ResearchReviewerEngine
from jarvis.research_reviewer.models import (
    DIM_NOVELTY,
    DIM_REPRODUCIBILITY,
    DIM_RISK,
    DIM_ROBUSTNESS,
    DIM_STATISTICAL,
    EV_METRIC,
    SEV_CRITICAL,
    SEV_MAJOR,
    SEV_MINOR,
    V_PASS,
    V_REJECT_RESEARCH,
    V_WARNING,
    ImmutableCritiqueError,
    ImmutableEvidenceError,
    ImmutableReviewError,
    InvalidDimension,
    InvalidEvidenceType,
    InvalidScore,
    InvalidSeverity,
    MissingDimensions,
    UnknownCritiqueError,
    UnknownReviewError,
)

T0 = "2026-07-24T00:00:00Z"
T1 = "2026-07-24T00:01:00Z"
T2 = "2026-07-24T00:02:00Z"


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_reviewer.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchReviewerEngine()


def _scores(stat=0.9, rob=0.9, rep=0.9, risk=0.9, nov=0.9):
    return {DIM_STATISTICAL: stat, DIM_ROBUSTNESS: rob, DIM_REPRODUCIBILITY: rep,
            DIM_RISK: risk, DIM_NOVELTY: nov}


def _review(e, subject="strat_A", reviewer="reviewer_1", scores=None, now=T0):
    return e.create_review(subject, reviewer, scores or _scores(), "RESEARCH", now,
                           commit=True).review_id


# ══════════════ create_review ══════════════
def test_review_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().create_review("s", "rev", _scores(), "RESEARCH", T0, commit=True)
    assert r.review_id.startswith("RVW:")
    assert r.verdict == V_PASS
    assert r.no_auto_decision is True


def test_review_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    a = _eng().create_review("s", "rev", _scores(), now=T0, commit=False)
    b = _eng().create_review("s", "rev", _scores(), now=T1, commit=False)
    assert a.review_id == b.review_id


def test_review_deterministic_verdict(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    a = _eng().create_review("s", "rev", _scores(0.5, 0.5, 0.5, 0.5, 0.5), now=T0, commit=False)
    b = _eng().create_review("s", "rev", _scores(0.5, 0.5, 0.5, 0.5, 0.5), now=T1, commit=False)
    assert a.verdict == b.verdict


def test_review_pass(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().create_review("s", "rev", _scores(0.9, 0.8, 0.85, 0.9, 0.75), now=T0, commit=True)
    assert r.verdict == V_PASS


def test_review_warning(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    # min 0.45 (<0.5) → WARNING
    r = _eng().create_review("s", "rev", _scores(0.9, 0.9, 0.9, 0.45, 0.9), now=T0, commit=True)
    assert r.verdict == V_WARNING


def test_review_reject(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    # min 0.2 (<0.3) → REJECT_RESEARCH
    r = _eng().create_review("s", "rev", _scores(0.9, 0.9, 0.9, 0.2, 0.9), now=T0, commit=True)
    assert r.verdict == V_REJECT_RESEARCH


def test_review_reject_low_overall(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    # overall 0.35 (<0.4) → REJECT
    r = _eng().create_review("s", "rev", _scores(0.35, 0.35, 0.35, 0.35, 0.35), now=T0,
                             commit=True)
    assert r.verdict == V_REJECT_RESEARCH


def test_review_dimension_verdicts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().create_review("s", "rev", _scores(0.9, 0.45, 0.2, 0.9, 0.9), now=T0, commit=True)
    assert r.dimension_verdicts[DIM_STATISTICAL] == V_PASS
    assert r.dimension_verdicts[DIM_ROBUSTNESS] == V_WARNING
    assert r.dimension_verdicts[DIM_REPRODUCIBILITY] == V_REJECT_RESEARCH


def test_review_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.create_review("s", "rev", _scores(0.9), now=T0, commit=True)
    with pytest.raises(ImmutableReviewError):
        e.create_review("s", "rev", _scores(0.5), now=T1, commit=True)


def test_review_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.create_review("s", "rev", _scores(), now=T0, commit=True)
    e.create_review("s", "rev", _scores(), now=T1, commit=True)
    assert len(ledger.read_reviews()) == 1


def test_review_missing_dimension(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(MissingDimensions):
        _eng().create_review("s", "rev", {DIM_STATISTICAL: 0.9}, now=T0, commit=True)


def test_review_invalid_dimension(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    sc = _scores()
    sc["BOGUS"] = 0.5
    with pytest.raises(InvalidDimension):
        _eng().create_review("s", "rev", sc, now=T0, commit=True)


def test_review_invalid_score(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(InvalidScore):
        _eng().create_review("s", "rev", _scores(1.5), now=T0, commit=True)


def test_review_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().create_review("s", "rev", _scores(), now=T0, commit=False)
    assert ledger.read_reviews() == []


def test_review_overall_score(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().create_review("s", "rev", _scores(0.8, 0.8, 0.8, 0.8, 0.8), now=T0, commit=True)
    assert r.overall_score == 0.8


# ══════════════ add_critique ══════════════
def test_critique_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    c = e.add_critique(rv, DIM_RISK, SEV_MAJOR, "high drawdown", T0, commit=True)
    assert c.critique_id.startswith("RVC:")
    assert c.severity == SEV_MAJOR


def test_critique_unknown_review(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownReviewError):
        _eng().add_critique("RVW:ghost", DIM_RISK, SEV_MAJOR, "x", T0, commit=True)


def test_critique_invalid_dimension(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    with pytest.raises(InvalidDimension):
        e.add_critique(rv, "BOGUS", SEV_MAJOR, "x", T0, commit=True)


def test_critique_invalid_severity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    with pytest.raises(InvalidSeverity):
        e.add_critique(rv, DIM_RISK, "HUGE", "x", T0, commit=True)


def test_critique_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    e.add_critique(rv, DIM_RISK, SEV_MAJOR, "same desc", T0, commit=True)
    with pytest.raises(ImmutableCritiqueError):
        e.add_critique(rv, DIM_RISK, SEV_CRITICAL, "same desc", T1, commit=True)


def test_critique_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    e.add_critique(rv, DIM_RISK, SEV_MAJOR, "d", T0, commit=True)
    e.add_critique(rv, DIM_RISK, SEV_MAJOR, "d", T1, commit=True)
    assert len(ledger.review_critiques(rv)) == 1


@pytest.mark.parametrize("sev", list(M.SEVERITIES))
def test_critique_all_severities(tmp_path, monkeypatch, sev):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    c = e.add_critique(rv, DIM_RISK, sev, f"d_{sev}", T0, commit=True)
    assert c.severity == sev


def test_critiques_by_dimension(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    e.add_critique(rv, DIM_RISK, SEV_MAJOR, "d1", T0, commit=True)
    e.add_critique(rv, DIM_STATISTICAL, SEV_MINOR, "d2", T0, commit=True)
    assert len(e.critiques_by_dimension(rv, DIM_RISK)) == 1


# ══════════════ add_evidence (linkage) ══════════════
def test_evidence_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    c = e.add_critique(rv, DIM_RISK, SEV_MAJOR, "d", T0, commit=True)
    ev = e.add_evidence(c.critique_id, EV_METRIC, "maxdd=-0.4", "too deep", T0, commit=True)
    assert ev.evidence_id.startswith("RVE:")
    assert ev.critique_id == c.critique_id


def test_evidence_unknown_critique(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownCritiqueError):
        _eng().add_evidence("RVC:ghost", EV_METRIC, "x", "", T0, commit=True)


def test_evidence_invalid_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    c = e.add_critique(rv, DIM_RISK, SEV_MAJOR, "d", T0, commit=True)
    with pytest.raises(InvalidEvidenceType):
        e.add_evidence(c.critique_id, "BOGUS", "x", "", T0, commit=True)


def test_evidence_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    c = e.add_critique(rv, DIM_RISK, SEV_MAJOR, "d", T0, commit=True)
    e.add_evidence(c.critique_id, EV_METRIC, "ref", "detail1", T0, commit=True)
    with pytest.raises(ImmutableEvidenceError):
        e.add_evidence(c.critique_id, EV_METRIC, "ref", "detail2", T1, commit=True)


@pytest.mark.parametrize("etype", list(M.EVIDENCE_TYPES))
def test_evidence_all_types(tmp_path, monkeypatch, etype):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    c = e.add_critique(rv, DIM_RISK, SEV_MAJOR, "d", T0, commit=True)
    ev = e.add_evidence(c.critique_id, etype, f"ref_{etype}", "", T0, commit=True)
    assert ev.evidence_type == etype


def test_evidence_linkage_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    c = e.add_critique(rv, DIM_RISK, SEV_MAJOR, "d", T0, commit=True)
    ev = e.add_evidence(c.critique_id, EV_METRIC, "r", "", T0, commit=True)
    assert e.evidence_for_review(rv) == [ev.evidence_id]


# ══════════════ generate_report (immutable, no decision) ══════════════
def test_report_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    e.add_critique(rv, DIM_RISK, SEV_MAJOR, "d", T0, commit=True)
    r = e.generate_report(rv, T1, commit=True)
    assert r.report_id.startswith("RVR:")
    assert r.critique_count == 1
    assert r.is_decision is False


def test_report_verdict_matches_review(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e, scores=_scores(0.2, 0.9, 0.9, 0.9, 0.9))
    r = e.generate_report(rv, T1, commit=True)
    assert r.verdict == V_REJECT_RESEARCH


def test_report_severity_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    e.add_critique(rv, DIM_RISK, SEV_MAJOR, "d1", T0, commit=True)
    e.add_critique(rv, DIM_STATISTICAL, SEV_MAJOR, "d2", T0, commit=True)
    e.add_critique(rv, DIM_NOVELTY, SEV_MINOR, "d3", T0, commit=True)
    r = e.generate_report(rv, T1, commit=True)
    assert r.severity_distribution[SEV_MAJOR] == 2
    assert r.severity_distribution[SEV_MINOR] == 1


def test_report_evidence_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    c = e.add_critique(rv, DIM_RISK, SEV_MAJOR, "d", T0, commit=True)
    e.add_evidence(c.critique_id, EV_METRIC, "r1", "", T0, commit=True)
    e.add_evidence(c.critique_id, EV_METRIC, "r2", "", T0, commit=True)
    r = e.generate_report(rv, T1, commit=True)
    assert r.evidence_count == 2


def test_report_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    a = e.generate_report(rv, T1, commit=False)
    b = e.generate_report(rv, T1, commit=False)
    assert a.to_dict() == b.to_dict()


def test_report_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    e.generate_report(rv, T1, commit=True)
    e.generate_report(rv, T1, commit=True)
    assert len(ledger.read_reports()) == 1


def test_report_has_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    r = e.generate_report(rv, T1, commit=True)
    assert "REJECT_RESEARCH ≠ DELETE_STRATEGY" in r.disclaimer


def test_report_unknown_review(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownReviewError):
        _eng().generate_report("RVW:ghost", T1, commit=True)


# ══════════════ 순수 함수 ══════════════
@pytest.mark.parametrize("score,expect", [
    (0.9, V_PASS), (0.7, V_PASS), (0.5, V_PASS), (0.49, V_WARNING), (0.3, V_WARNING),
    (0.29, V_REJECT_RESEARCH), (0.0, V_REJECT_RESEARCH)])
def test_dimension_verdict_pure(score, expect):
    assert M.dimension_verdict(score) == expect


def test_overall_score_pure():
    assert M.overall_score({"A": 0.6, "B": 0.8}) == 0.7


def test_overall_verdict_pure():
    assert M.overall_verdict(_scores(0.9)) == V_PASS
    assert M.overall_verdict(_scores(0.9, 0.9, 0.9, 0.45, 0.9)) == V_WARNING
    assert M.overall_verdict(_scores(0.9, 0.9, 0.9, 0.2, 0.9)) == V_REJECT_RESEARCH


def test_validate_scores_pure():
    M.validate_scores(_scores())  # no raise
    with pytest.raises(MissingDimensions):
        M.validate_scores({DIM_RISK: 0.5})


def test_three_verdicts():
    assert set(M.VERDICTS) == {"PASS", "WARNING", "REJECT_RESEARCH"}


def test_five_dimensions():
    assert len(M.DIMENSIONS) == 5


# ══════════════ verify / replay ══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_reviewer.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_after_activity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_reviewer.verify import verify_chain
    e = _eng()
    rv = _review(e)
    c = e.add_critique(rv, DIM_RISK, SEV_MAJOR, "d", T0, commit=True)
    e.add_evidence(c.critique_id, EV_METRIC, "r", "", T0, commit=True)
    e.generate_report(rv, T1, commit=True)
    res = verify_chain()
    assert res["ok"] is True
    assert res["linkage"]["ok"] is True
    assert res["determinism"]["ok"] is True
    assert res["no_auto_decision"]["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _review(e)
    p = sp("rvw_reviews.jsonl")
    rows = [json.loads(x) for x in open(p)]
    rows[0]["verdict"] = "PASS_TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_reviewer.verify import verify_chain
    assert verify_chain()["ok"] is False


def test_verify_determinism_detects_forged_verdict(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    # 실제로는 REJECT 여야 하는데 PASS 로 위조
    _review(e, scores=_scores(0.9, 0.9, 0.9, 0.2, 0.9))
    p = sp("rvw_reviews.jsonl")
    rows = [json.loads(x) for x in open(p)]
    rows[0]["verdict"] = "PASS"
    rows[0]["record_hash"] = M.content_hash(rows[0])  # 재봉인(체인은 통과)
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_reviewer.verify import verdict_determinism
    assert verdict_determinism()["ok"] is False


def test_verify_no_auto_decision_detects_forged(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    e.generate_report(rv, T1, commit=True)
    p = sp("rvw_reports.jsonl")
    rows = [json.loads(x) for x in open(p)]
    rows[0]["is_decision"] = True
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_reviewer.verify import no_auto_decision
    assert no_auto_decision()["ok"] is False


def test_verify_linkage_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_reviewer.verify import evidence_linkage
    e = _eng()
    rv = _review(e)
    c = e.add_critique(rv, DIM_RISK, SEV_MAJOR, "d", T0, commit=True)
    e.add_evidence(c.critique_id, EV_METRIC, "r", "", T0, commit=True)
    assert evidence_linkage()["ok"] is True


def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_reviewer.verify import replay
    e = _eng()
    _review(e)
    assert replay(e, T1)["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    e.add_critique(rv, DIM_RISK, SEV_MAJOR, "d", T0, commit=True)
    e.generate_report(rv, T1, commit=True)
    s = e.summary(T2)
    assert s.review_count == 1
    assert s.critique_count == 1
    assert s.report_count == 1


def test_summary_verdict_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.create_review("s1", "r", _scores(0.9), now=T0, commit=True)
    e.create_review("s2", "r", _scores(0.2, 0.9, 0.9, 0.9, 0.9), now=T0, commit=True)
    s = e.summary(T1)
    assert s.verdict_distribution[V_PASS] == 1
    assert s.verdict_distribution[V_REJECT_RESEARCH] == 1


# ══════════════ 조회 편의 ══════════════
def test_list_reviews_by_verdict(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    r1 = e.create_review("s1", "r", _scores(0.9), now=T0, commit=True).review_id
    e.create_review("s2", "r", _scores(0.2, 0.9, 0.9, 0.9, 0.9), now=T0, commit=True)
    assert e.list_reviews(V_PASS) == [r1]


def test_reviews_of_subject(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    r1 = e.create_review("subj", "r1", _scores(), now=T0, commit=True).review_id
    r2 = e.create_review("subj", "r2", _scores(), now=T0, commit=True).review_id
    assert e.reviews_of_subject("subj") == sorted([r1, r2])


def test_get_verdict(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    assert e.get_verdict(rv) == V_PASS


# ══════════════ 보안 / 불변식 (no auto decision, reject != delete) ══════════════
def test_no_forbidden_imports():
    import ast
    forbidden = ("execution", "broker", "order", "portfolio_execution", "capital_allocation",
                 "live_trading", "permission", "risk_controller")
    base = os.path.dirname(os.path.dirname(__file__))
    for fn in ("engine.py", "ledger.py", "models.py", "verify.py", "__main__.py", "__init__.py"):
        tree = ast.parse(open(os.path.join(base, fn)).read())
        for n in ast.walk(tree):
            mods = []
            if isinstance(n, ast.Import):
                mods = [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom):
                mods = [n.module or ""]
            for m in mods:
                for fb in forbidden:
                    assert not (m == f"jarvis.{fb}" or m.startswith(f"jarvis.{fb}.")), (fn, m)


def test_engine_no_decision_methods():
    e = ResearchReviewerEngine()
    for bad in ("approve", "auto_approve", "deploy", "delete", "delete_strategy",
                "remove_strategy", "execute", "trade", "allocate", "activate", "decide"):
        assert not hasattr(e, bad), bad


def test_no_decision_verbs_in_source():
    base = os.path.dirname(os.path.dirname(__file__))
    for fn in ("engine.py", "models.py"):
        src = open(os.path.join(base, fn)).read()
        for bad in ("def approve", "def deploy", "def delete", "def execute", "def trade",
                    "def decide", "def remove_strategy"):
            assert bad not in src, (fn, bad)


def test_forbidden_verbs_defined():
    for v in ("APPROVE", "DEPLOY", "DELETE", "DELETE_STRATEGY", "EXECUTE"):
        assert M.is_forbidden_verb(v) is True
    assert M.is_forbidden_verb("REVIEW") is False


def test_reject_not_delete(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = e.create_review("strat_X", "r", _scores(0.2, 0.9, 0.9, 0.9, 0.9), now=T0,
                         commit=True).review_id
    # REJECT_RESEARCH 라도 어떤 것도 삭제되지 않음 — 리뷰 원장만 존재
    assert e.get_verdict(rv) == V_REJECT_RESEARCH
    fns = {l[0] for l in ledger.ALL_LEDGERS}
    assert "rvw_strategies.jsonl" not in fns  # 전략 원장 없음(삭제 대상 없음)


def test_no_delete_or_update_api():
    import inspect
    src = inspect.getsource(ledger)
    for bad in ("def delete", "def update", "def remove", "def overwrite", "def edit_"):
        assert bad not in src, bad


def test_ledger_only_appends():
    import inspect
    src = inspect.getsource(ledger)
    assert '"a"' in src
    assert 'open(p, "w"' not in src


def test_disclaimer_marks_no_decision():
    from jarvis.research_reviewer.engine import _DISCLAIMER
    assert "REVIEW ≠ DECISION" in _DISCLAIMER
    assert "VERDICT ≠ ACTION" in _DISCLAIMER


def test_all_reviews_no_auto_decision(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _review(e)
    for r in ledger.read_reviews():
        assert r["no_auto_decision"] is True


def test_all_reports_not_decision(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    e.generate_report(rv, T1, commit=True)
    for r in ledger.read_reports():
        assert r["is_decision"] is False


def test_records_frozen():
    r = M.ReviewRecord(review_id="RVW:x", subject="s", subject_type="R", reviewer="r",
                       dimension_scores={}, dimension_verdicts={}, overall_score=0.5,
                       verdict="PASS", no_auto_decision=True, created_at=T0)
    with pytest.raises(Exception):
        r.verdict = "REJECT_RESEARCH"  # type: ignore


def test_only_rvw_files_written(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    c = e.add_critique(rv, DIM_RISK, SEV_MAJOR, "d", T0, commit=True)
    e.add_evidence(c.critique_id, EV_METRIC, "r", "", T0, commit=True)
    e.generate_report(rv, T1, commit=True)
    for fn in os.listdir(tmp_path):
        assert fn.startswith("rvw_"), fn


# ══════════════ 커버리지: id 접두사·상수 ══════════════
def test_id_prefixes_distinct():
    ids = {M.review_id("s", "r")[:4], M.critique_id("rv", "d", "x")[:4],
           M.evidence_id("c", "t", "r")[:4], M.report_id("s", "rv", T0)[:4]}
    assert len(ids) == 4


def test_four_owned_ledgers():
    assert len(ledger.ALL_LEDGERS) == 4
    fns = {l[0] for l in ledger.ALL_LEDGERS}
    assert len(fns) == 4
    assert all(f.startswith("rvw_") for f in fns)


def test_four_severities():
    assert len(M.SEVERITIES) == 4


def test_six_evidence_types():
    assert len(M.EVIDENCE_TYPES) == 6


def test_content_hash_excludes_hash_fields():
    r = {"a": 1, "previous_hash": "p", "record_hash": "r"}
    assert M.content_hash(r) == M.content_hash({"a": 1, "previous_hash": "z", "record_hash": "q"})


def test_input_digest_deterministic():
    assert M.input_digest("a", "b") == M.input_digest("a", "b")
    assert M.input_digest("a", "b") != M.input_digest("b", "a")


def test_list_reviews_all(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    assert rv in e.list_reviews()


# ══════════════ CLI ══════════════
def _run(argv, capsys):
    from jarvis.research_reviewer.__main__ import main
    rc = main(argv)
    return rc, capsys.readouterr().out


def test_cli_review(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["review", "--subject", "s", "--reviewer", "r",
                    "--scores", "STATISTICAL=0.9,ROBUSTNESS=0.9,REPRODUCIBILITY=0.9,RISK=0.9,NOVELTY=0.9",
                    "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["review"]["verdict"] == "PASS"


def test_cli_critique_and_evidence(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    rc, out = _run(["critique", "--review", rv, "--dim", "RISK", "--severity", "MAJOR",
                    "--desc", "dd", "--commit"], capsys)
    assert rc == 0
    cid = json.loads(out)["critique"]["critique_id"]
    rc2, out2 = _run(["evidence", "--critique", cid, "--type", "METRIC", "--ref", "x", "--commit"],
                     capsys)
    assert rc2 == 0
    assert json.loads(out2)["evidence"]["critique_id"] == cid


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    rc, out = _run(["report", "--review", rv, "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["report"]["is_decision"] is False


def test_cli_verdict(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    rc, out = _run(["verdict", "--review", rv], capsys)
    assert rc == 0
    assert json.loads(out)["verdict"] == "PASS"


def test_cli_reviews(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _review(_eng())
    rc, out = _run(["reviews"], capsys)
    assert rc == 0
    assert len(json.loads(out)["reviews"]) == 1


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["verify"], capsys)
    assert rc == 0
    assert json.loads(out)["ok"] is True


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _review(_eng())
    rc, out = _run(["replay"], capsys)
    assert rc == 0
    assert json.loads(out)["deterministic"] is True


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["summary"], capsys)
    assert rc == 0
    assert "review_count" in json.loads(out)


# ══════════════ 추가 커버리지 ══════════════
@pytest.mark.parametrize("dim", list(M.DIMENSIONS))
def test_each_dimension_scored(tmp_path, monkeypatch, dim):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    r = e.create_review("s", "rev", _scores(), now=T0, commit=True)
    assert dim in r.dimension_scores
    assert dim in r.dimension_verdicts


@pytest.mark.parametrize("dim", list(M.DIMENSIONS))
def test_critique_each_dimension(tmp_path, monkeypatch, dim):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    c = e.add_critique(rv, dim, SEV_MINOR, f"c_{dim}", T0, commit=True)
    assert c.dimension == dim


@pytest.mark.parametrize("scores,expect", [
    ((0.9, 0.9, 0.9, 0.9, 0.9), V_PASS),
    ((0.7, 0.7, 0.7, 0.7, 0.7), V_PASS),
    ((0.5, 0.5, 0.5, 0.5, 0.5), V_WARNING),
    ((0.49, 0.9, 0.9, 0.9, 0.9), V_WARNING),
    ((0.3, 0.9, 0.9, 0.9, 0.9), V_WARNING),
    ((0.29, 0.9, 0.9, 0.9, 0.9), V_REJECT_RESEARCH),
    ((0.35, 0.35, 0.35, 0.35, 0.35), V_REJECT_RESEARCH),
])
def test_verdict_matrix(tmp_path, monkeypatch, scores, expect):
    _iso(tmp_path, monkeypatch)
    r = _eng().create_review("s", "r", _scores(*scores), now=T0, commit=True)
    assert r.verdict == expect


def test_critique_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    e.add_critique(rv, DIM_RISK, SEV_MAJOR, "d", T0, commit=False)
    assert ledger.read_critiques() == []


def test_evidence_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    c = e.add_critique(rv, DIM_RISK, SEV_MAJOR, "d", T0, commit=True)
    e.add_evidence(c.critique_id, EV_METRIC, "r", "", T0, commit=False)
    assert ledger.read_evidence() == []


def test_report_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    e.generate_report(rv, T1, commit=False)
    assert ledger.read_reports() == []


def test_evidence_for_review_multiple_critiques(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    c1 = e.add_critique(rv, DIM_RISK, SEV_MAJOR, "d1", T0, commit=True)
    c2 = e.add_critique(rv, DIM_STATISTICAL, SEV_MINOR, "d2", T0, commit=True)
    e.add_evidence(c1.critique_id, EV_METRIC, "r1", "", T0, commit=True)
    e.add_evidence(c2.critique_id, EV_METRIC, "r2", "", T0, commit=True)
    assert len(e.evidence_for_review(rv)) == 2


def test_evidence_for_review_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    assert e.evidence_for_review(rv) == []


def test_multiple_reviewers_same_subject(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.create_review("subj", "r1", _scores(), now=T0, commit=True)
    e.create_review("subj", "r2", _scores(0.2, 0.9, 0.9, 0.9, 0.9), now=T0, commit=True)
    assert len(e.reviews_of_subject("subj")) == 2


def test_score_boundary_zero_and_one(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    r = e.create_review("s", "r", _scores(0.0, 1.0, 1.0, 1.0, 1.0), now=T0, commit=True)
    assert r.dimension_scores[DIM_STATISTICAL] == 0.0
    assert r.verdict == V_REJECT_RESEARCH  # min 0.0


def test_invalid_score_negative(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(InvalidScore):
        _eng().create_review("s", "r", _scores(-0.1), now=T0, commit=True)


def test_report_dimension_scores_preserved(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e, scores=_scores(0.8, 0.7, 0.6, 0.9, 0.75))
    r = e.generate_report(rv, T1, commit=True)
    assert r.dimension_scores[DIM_STATISTICAL] == 0.8


def test_critiques_by_dimension_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    assert e.critiques_by_dimension(rv, DIM_RISK) == []


def test_list_reviews_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().list_reviews() == []


def test_overall_score_rounding(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    r = e.create_review("s", "r", _scores(0.1, 0.2, 0.3, 0.4, 0.5), now=T0, commit=True)
    assert r.overall_score == 0.3


def test_report_review_id_link(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rv = _review(e)
    r = e.generate_report(rv, T1, commit=True)
    assert r.review_id == rv


def test_reviews_of_subject_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().reviews_of_subject("none") == []


def test_verdict_ids_stable():
    assert M.review_id("a", "b") == M.review_id("a", "b")
    assert M.review_id("a", "b") != M.review_id("b", "a")


# ══════════════ 통합 시나리오 ══════════════
def test_end_to_end_review(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    # 약한 재현성·리스크 → WARNING/REJECT 경계
    rv = e.create_review("momentum_strat", "ai_reviewer",
                         _scores(0.8, 0.7, 0.35, 0.4, 0.6), "RESEARCH", T0, commit=True)
    assert rv.verdict == V_WARNING  # min 0.35 (>=0.3, <0.5)
    c1 = e.add_critique(rv.review_id, DIM_REPRODUCIBILITY, SEV_MAJOR,
                        "seed not fixed", T0, commit=True)
    e.add_evidence(c1.critique_id, EV_REPLAY := "REPLAY", "replay_mismatch", "run2 differs", T0,
                   commit=True)
    c2 = e.add_critique(rv.review_id, DIM_RISK, SEV_MINOR, "moderate drawdown", T0, commit=True)
    e.add_evidence(c2.critique_id, EV_METRIC, "maxdd=-0.25", "", T0, commit=True)
    rep = e.generate_report(rv.review_id, T1, commit=True)
    assert rep.verdict == V_WARNING
    assert rep.critique_count == 2
    assert rep.evidence_count == 2
    assert rep.is_decision is False
    assert len(e.evidence_for_review(rv.review_id)) == 2
    from jarvis.research_reviewer.verify import verify_chain
    v = verify_chain()
    assert v["ok"] is True
    assert v["linkage"]["ok"] and v["determinism"]["ok"] and v["no_auto_decision"]["ok"]
