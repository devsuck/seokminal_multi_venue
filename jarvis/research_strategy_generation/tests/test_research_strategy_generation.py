"""P29 research_strategy_generation 테스트 — 세션/후보 생애주기·가설·신규성·증거·선택금지·
계보·verify·replay·CLI·보안·READ ONLY 상위. GENERATED ≠ SELECTED."""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.research_strategy_generation import ledger
from jarvis.research_strategy_generation import models as M
from jarvis.research_strategy_generation.engine import ResearchStrategyGenerationEngine
from jarvis.research_strategy_generation.models import (
    CANDIDATE_CATEGORIES,
    CANDIDATE_STATES,
    EVIDENCE_TYPES,
    FORBIDDEN_VERBS,
    GENESIS,
    NOVELTY_LEVELS,
    SESSION_STATES,
    C_ANALYZED,
    C_ARCHIVED,
    C_NOVELTY_CHECKED,
    C_PROPOSED,
    C_REVIEWED,
    S_ANALYZED,
    S_ARCHIVED,
    S_CONCLUDED,
    S_CREATED,
    S_GENERATING,
    IllegalCandidateTransition,
    IllegalSessionTransition,
    UnknownEntityError,
    can_candidate_transition,
    can_session_transition,
    classify_novelty,
    content_hash,
    novelty_score,
)
from jarvis.research_strategy_generation.verify import (
    candidate_lifecycle_integrity,
    candidate_selection_integrity,
    duplicate_integrity,
    lineage_integrity,
    reference_integrity,
    replay,
    session_lifecycle_integrity,
    verify_chain,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_strategy_generation.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchStrategyGenerationEngine()


def _sess(e, objective="alpha generation", now=T[0]):
    return e.create_session(objective, now, commit=True).session_id


def _cand(e, sess, category="ALPHA", statement="regime-aware momentum overlay", now=T[1]):
    return e.generate_candidate(sess, category, statement, ["rmi:m1"], now, commit=True).candidate_id


# ═══════════════ session lifecycle ═══════════════
def test_create_session(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().create_session("obj", T[0], commit=True)
    assert ev.to_state == S_CREATED
    assert ev.session_id.startswith("SGS:")
    assert ev.session_event_id.startswith("SGE:")


def test_session_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    e.start_generating(sess, now=T[1], commit=True)
    e.analyze_session(sess, now=T[2], commit=True)
    e.conclude_session(sess, now=T[3], commit=True)
    e.archive_session(sess, now=T[4], commit=True)
    assert e.session_state(sess) == S_ARCHIVED


def test_session_no_skip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    with pytest.raises(IllegalSessionTransition):
        e.conclude_session(sess, now=T[1], commit=True)


def test_session_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.create_session("o", T[0], commit=True).session_id
    b = e.create_session("o", T[1], commit=True).session_id
    assert a == b
    assert len(ledger.session_events(a)) == 1


def test_session_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().start_generating("SGS:nope", now=T[1], commit=True)


@pytest.mark.parametrize("frm,to,ok", [
    (S_CREATED, S_GENERATING, True), (S_CREATED, S_ANALYZED, False),
    (S_GENERATING, S_ANALYZED, True), (S_ANALYZED, S_CONCLUDED, True),
    (S_CONCLUDED, S_ARCHIVED, True), (S_CONCLUDED, S_GENERATING, True),
    (S_ARCHIVED, S_GENERATING, False),
])
def test_session_transition_matrix(frm, to, ok):
    assert can_session_transition(frm, to) is ok


@pytest.mark.parametrize("s", SESSION_STATES)
def test_session_states(s):
    assert s in SESSION_STATES


# ═══════════════ candidate generation (no selection) ═══════════════
def test_generate_candidate(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    c = e.generate_candidate(sess, "ALPHA", "momentum overlay", ["rmi:1"], T[1], commit=True)
    assert c.candidate_id.startswith("SGC:")
    assert c.to_state == C_PROPOSED
    assert c.is_selected is False


def test_candidate_bad_category(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    with pytest.raises(ValueError):
        e.generate_candidate(sess, "NOPE", "s", now=T[1], commit=True)


def test_candidate_unknown_session(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().generate_candidate("SGS:nope", "ALPHA", "s", now=T[1], commit=True)


def test_candidate_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    cand = _cand(e, sess)
    e.analyze_candidate(cand, now=T[2], commit=True)
    e.analyze_novelty(cand, T[3], commit=True)  # → NOVELTY_CHECKED
    e.review_candidate(cand, now=T[4], commit=True)
    e.archive_candidate(cand, now=T[5], commit=True)
    assert e.candidate_state(cand) == C_ARCHIVED


def test_candidate_no_skip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    cand = _cand(e, sess)
    with pytest.raises(IllegalCandidateTransition):
        e.review_candidate(cand, now=T[2], commit=True)  # PROPOSED→REVIEWED skip


def test_candidate_never_selected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    cand = _cand(e, sess)
    e.analyze_candidate(cand, now=T[2], commit=True)
    for ev in ledger.candidate_events(cand):
        assert ev["is_selected"] is False  # 어떤 상태에서도 선택 없음


def test_candidate_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    cand = _cand(e, sess)
    arts = {a["artifact_id"]: a for a in ledger.read_artifacts()}
    cand_art = next(a for a in arts.values() if a["ref_id"] == cand)
    assert cand_art["parent_artifact"] == M.artifact_id(M.ART_SESSION, sess)


@pytest.mark.parametrize("frm,to,ok", [
    (C_PROPOSED, C_ANALYZED, True), (C_PROPOSED, C_REVIEWED, False),
    (C_ANALYZED, C_NOVELTY_CHECKED, True), (C_NOVELTY_CHECKED, C_REVIEWED, True),
    (C_REVIEWED, C_ARCHIVED, True), (C_ARCHIVED, C_ANALYZED, False),
])
def test_candidate_transition_matrix(frm, to, ok):
    assert can_candidate_transition(frm, to) is ok


@pytest.mark.parametrize("s", CANDIDATE_STATES)
def test_candidate_states(s):
    assert s in CANDIDATE_STATES


@pytest.mark.parametrize("cat", CANDIDATE_CATEGORIES)
def test_candidate_categories(tmp_path, monkeypatch, cat):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    c = e.generate_candidate(sess, cat, f"s-{cat}", now=T[1], commit=True)
    assert c.category == cat


# ═══════════════ hypothesis ═══════════════
def test_record_hypothesis(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    cand = _cand(e, sess)
    h = e.record_hypothesis(cand, "regime filter improves sharpe", "prior evidence", "higher sharpe",
                            T[2], commit=True)
    assert h.hypothesis_id.startswith("SGH:")


def test_hypothesis_unknown_candidate(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().record_hypothesis("SGC:nope", "h", now=T[0], commit=True)


# ═══════════════ novelty ═══════════════
def test_analyze_novelty_first(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    cand = _cand(e, sess)
    e.analyze_candidate(cand, now=T[2], commit=True)
    n = e.analyze_novelty(cand, T[3], commit=True)
    assert n.novelty_id.startswith("SGN:")
    assert n.score == 1.0  # 유일 후보 → 완전 신규
    assert n.level == "NOVEL"


def test_analyze_novelty_advances_candidate(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    cand = _cand(e, sess)
    e.analyze_candidate(cand, now=T[2], commit=True)
    e.analyze_novelty(cand, T[3], commit=True)
    assert e.candidate_state(cand) == C_NOVELTY_CHECKED


def test_novelty_duplicate(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    c1 = e.generate_candidate(sess, "ALPHA", "regime aware momentum overlay strategy", now=T[1],
                              commit=True).candidate_id
    c2 = e.generate_candidate(sess, "ALPHA", "regime aware momentum overlay strategy variant",
                              now=T[2], commit=True).candidate_id
    e.analyze_candidate(c2, now=T[3], commit=True)
    n = e.analyze_novelty(c2, T[4], commit=True)
    assert n.compared_count >= 1
    assert n.level in NOVELTY_LEVELS


def test_novelty_score_helper():
    assert novelty_score("a b c", []) == 1.0
    assert novelty_score("a b c", ["a b c"]) == 0.0


@pytest.mark.parametrize("score,level", [(0.9, "NOVEL"), (0.5, "INCREMENTAL"), (0.1, "DUPLICATE")])
def test_classify_novelty(score, level):
    assert classify_novelty(score) == level


# ═══════════════ evidence ═══════════════
def test_record_evidence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    cand = _cand(e, sess)
    ev = e.record_evidence(cand, "rmi:m1", "HISTORICAL", "memory_intelligence", T[2], commit=True)
    assert ev.evidence_id.startswith("SGV:")


def test_evidence_bad_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    cand = _cand(e, sess)
    with pytest.raises(ValueError):
        e.record_evidence(cand, "r", "NOPE", now=T[2], commit=True)


@pytest.mark.parametrize("et", EVIDENCE_TYPES)
def test_evidence_types(et):
    assert et in EVIDENCE_TYPES


# ═══════════════ integration READ ONLY ═══════════════
def test_source_layers_present():
    for k in ("alpha_intelligence", "knowledge_graph", "research_memory", "autonomous_research",
              "memory_intelligence", "insight_intelligence"):
        assert k in ledger.SOURCE_LAYERS


def test_source_count_readonly(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    p = sp("rmi_memories.jsonl")
    with open(p, "w") as f:
        for i in range(3):
            f.write(json.dumps({"memory_event_id": f"m{i}"}) + "\n")
    before = open(p).read()
    assert ledger.source_count("memory_intelligence") == 3
    assert open(p).read() == before


def test_all_source_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert set(ledger.all_source_counts()) == set(ledger.SOURCE_LAYERS)


# ═══════════════ verify ═══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_verify_after_activity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    e.start_generating(sess, now=T[1], commit=True)
    cand = _cand(e, sess, now=T[2])
    e.record_hypothesis(cand, "h", now=T[3], commit=True)
    e.analyze_candidate(cand, now=T[4], commit=True)
    e.analyze_novelty(cand, T[5], commit=True)
    e.record_evidence(cand, "r", "PATTERN", "insight_intelligence", T[6], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _sess(e)
    p = sp("rsg_sessions.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["objective"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    _cand(e, sess)
    p = sp("rsg_candidates.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["previous_hash"] = "sha256:bad"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _sess(e)
    p = sp("rsg_sessions.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    with open(p, "a") as f:
        f.write(json.dumps(rows[0]) + "\n")
    assert verify_chain()["ok"] is False


def test_session_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    e.start_generating(sess, now=T[1], commit=True)
    assert session_lifecycle_integrity()["ok"] is True


def test_candidate_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    _cand(e, sess)
    assert candidate_lifecycle_integrity()["ok"] is True


def test_duplicate_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _sess(e, "a")
    _sess(e, "b")
    assert duplicate_integrity()["ok"] is True


def test_selection_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    _cand(e, sess)
    assert candidate_selection_integrity()["ok"] is True


def test_selection_integrity_detects_selected(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    _cand(e, sess)
    p = sp("rsg_candidates.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["is_selected"] = True
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert candidate_selection_integrity()["ok"] is False


def test_reference_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    cand = _cand(e, sess)
    e.record_evidence(cand, "r", "LESSON", "research_memory", T[2], commit=True)
    assert reference_integrity()["ok"] is True


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    cand = _cand(e, sess)
    e.record_hypothesis(cand, "h", now=T[2], commit=True)
    assert lineage_integrity()["ok"] is True


# ═══════════════ replay ═══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    _cand(e, sess)
    assert replay(e, T[9])["deterministic"] is True


# ═══════════════ report ═══════════════
def test_generate_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    cand = _cand(e, sess, category="REGIME")
    e.analyze_candidate(cand, now=T[2], commit=True)
    e.analyze_novelty(cand, T[3], commit=True)
    r = e.generate_report("SYSTEM", T[4], commit=True)
    assert r.report_id.startswith("SGR:")
    assert r.is_binding is False
    assert r.candidate_count == 1
    assert r.category_distribution.get("REGIME") == 1


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("SYSTEM", T[0], commit=True)
    assert "SELECTED" in r.disclaimer


# ═══════════════ 금지 동사 ═══════════════
@pytest.mark.parametrize("verb", sorted(FORBIDDEN_VERBS))
def test_forbidden_verb(verb):
    assert M.is_forbidden_verb(verb) is True


@pytest.mark.parametrize("verb", ["GENERATE", "PROPOSE", "ANALYZE", "COMPARE", "RECORD"])
def test_allowed_verb(verb):
    assert M.is_forbidden_verb(verb) is False


def test_forbidden_empty():
    assert M.is_forbidden_verb("") is False


# ═══════════════ ID / hash ═══════════════
@pytest.mark.parametrize("fn,args,prefix", [
    (M.session_id, ("o",), "SGS:"),
    (M.session_event_id, ("s", "CREATED", 0), "SGE:"),
    (M.candidate_id, ("s", "st"), "SGC:"),
    (M.candidate_event_id, ("c", "PROPOSED", 0), "SGD:"),
    (M.hypothesis_id, ("c", "h"), "SGH:"),
    (M.novelty_id, ("c", 0), "SGN:"),
    (M.evidence_id, ("c", "r", 0), "SGV:"),
    (M.report_id, ("s", "t"), "SGR:"),
    (M.artifact_id, ("CANDIDATE", "r"), "SGA:"),
])
def test_id_prefixes(fn, args, prefix):
    assert fn(*args).startswith(prefix)


def test_content_hash_excludes_meta():
    a = content_hash({"x": 1, "previous_hash": "p", "record_hash": "r"})
    b = content_hash({"x": 1, "previous_hash": "Q", "record_hash": "Z"})
    assert a == b


# ═══════════════ summary ═══════════════
def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    _cand(e, sess)
    s = e.summary(T[9])
    assert s.session_count == 1
    assert s.candidate_count == 1


# ═══════════════ CLI ═══════════════
def test_cli_session(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_strategy_generation.__main__ import main
    assert main(["session", "--objective", "alpha gen", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["session"]["to_state"] == "CREATED"


def test_cli_candidate(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_strategy_generation.__main__ import main
    main(["session", "--objective", "o", "--commit"])
    sess = json.loads(capsys.readouterr().out)["session"]["session_id"]
    assert main(["candidate", "--session", sess, "--category", "ALPHA", "--statement", "s",
                 "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["candidate"]["is_selected"] is False


def test_cli_novelty_and_evidence(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_strategy_generation.__main__ import main
    main(["session", "--objective", "o", "--commit"])
    sess = json.loads(capsys.readouterr().out)["session"]["session_id"]
    main(["candidate", "--session", sess, "--category", "ALPHA", "--statement", "s", "--commit"])
    cand = json.loads(capsys.readouterr().out)["candidate"]["candidate_id"]
    main(["candidate", "--session", sess, "--category", "ALPHA", "--statement", "s", "--commit"])
    capsys.readouterr()
    assert main(["evidence", "--candidate", cand, "--ref", "r", "--type", "HISTORICAL",
                 "--commit"]) == 0


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_strategy_generation.__main__ import main
    assert main(["report", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["report"]["is_binding"] is False


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_strategy_generation.__main__ import main
    assert main(["verify"]) == 0


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_strategy_generation.__main__ import main
    assert main(["summary"]) == 0


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_strategy_generation.__main__ import main
    assert main(["replay"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["deterministic"] is True


# ═══════════════ 격리 / ledger ═══════════════
def test_records_frozen(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().create_session("o", T[0], commit=True)
    with pytest.raises(Exception):
        ev.objective = "x"


def test_seven_ledgers():
    assert len(ledger.ALL_LEDGERS) == 7


def test_ledger_filenames_prefixed():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("rsg_")


def test_required_ledgers_present():
    names = {f for f, _ in ledger.ALL_LEDGERS}
    for req in ("rsg_sessions.jsonl", "rsg_candidates.jsonl", "rsg_hypotheses.jsonl",
                "rsg_novelty.jsonl", "rsg_evidence.jsonl", "rsg_reports.jsonl",
                "rsg_artifacts.jsonl"):
        assert req in names


# ═══════════════ 보안 스캔 ═══════════════
_PKG = os.path.dirname(os.path.dirname(__file__))
_SRC = [os.path.join(_PKG, f) for f in os.listdir(_PKG) if f.endswith(".py")]

_FORBIDDEN_IMPORTS = (
    "jarvis.execution", "jarvis.broker", "jarvis.live_trading", "jarvis.portfolio_execution",
    "jarvis.live_portfolio", "jarvis.portfolio", "jarvis.order", "jarvis.deployment", "jarvis.live",
)


@pytest.mark.parametrize("path", _SRC)
def test_no_forbidden_imports(path):
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(f) for f in _FORBIDDEN_IMPORTS), node.module
        if isinstance(node, ast.Import):
            for n in node.names:
                assert not any(n.name.startswith(f) for f in _FORBIDDEN_IMPORTS), n.name


@pytest.mark.parametrize("path", _SRC)
def test_no_forbidden_method_defs(path):
    tree = ast.parse(open(path).read())
    bad = ("execute", "deploy", "trade", "allocate", "approve", "select", "execute_trade",
           "place_order", "allocate_capital", "deploy_strategy", "activate_live",
           "approve_for_trading", "select_strategy")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert "claude-opus" not in open(path).read().lower()


@pytest.mark.parametrize("path", _SRC)
def test_no_destructive_ledger_api(path):
    src = open(path).read()
    for bad in ("def delete_", "def overwrite_", "def drop_", "def truncate", "def purge_"):
        assert bad not in src


def test_ledger_append_only():
    src = open(os.path.join(_PKG, "ledger.py")).read()
    assert '"a"' in src
    assert '"w"' not in src


def test_engine_no_forbidden_methods():
    e = _eng()
    for attr in ("execute", "deploy", "trade", "allocate", "approve", "select"):
        assert not hasattr(e, attr)


# ═══════════════ end-to-end ═══════════════
def test_end_to_end(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("rmi_memories.jsonl"), "w") as f:
        f.write(json.dumps({"memory_event_id": "rmi:m1"}) + "\n")
    e = _eng()
    sess = e.create_session("generate alpha candidates from regime memories", T[0],
                            commit=True).session_id
    e.start_generating(sess, now=T[1], commit=True)
    c1 = e.generate_candidate(sess, "ALPHA", "regime-aware momentum overlay", ["rmi:m1"], T[2],
                              commit=True).candidate_id
    c2 = e.generate_candidate(sess, "RISK", "tail-hedged carry with regime gate", ["rmi:m1"], T[3],
                              commit=True).candidate_id
    e.record_hypothesis(c1, "regime gate reduces drawdown", "prior memory", "lower dd", T[4],
                        commit=True)
    e.analyze_candidate(c1, now=T[5], commit=True)
    n = e.analyze_novelty(c1, T[6], commit=True)
    assert n.level in NOVELTY_LEVELS
    e.record_evidence(c1, "rmi:m1", "HISTORICAL", "memory_intelligence", T[7], commit=True)
    e.review_candidate(c1, now=T[8], commit=True)  # 검토만 — 선택 아님
    assert e.candidate_state(c1) == C_REVIEWED
    e.analyze_candidate(c2, now=T[9], commit=True)
    e.analyze_novelty(c2, T[10], commit=True)
    e.analyze_session(sess, now=T[11], commit=True)
    r = e.generate_report("SYSTEM", T[12], commit=True)
    assert r.candidate_count == 2
    assert r.is_binding is False  # GENERATED ≠ SELECTED
    # 어떤 후보도 선택되지 않음
    assert all(ev["is_selected"] is False for ev in ledger.read_candidate_events())
    assert open(sp("rmi_memories.jsonl")).read()  # 상위 원장 불변
    assert verify_chain()["ok"] is True
    assert replay(e, T[13])["deterministic"] is True
