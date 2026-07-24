"""P28 research_insight_intelligence 테스트 — 통찰 생애주기·맥락·증거 해석·공백 탐지·관계 매핑·
계보·verify·replay·CLI·보안·READ ONLY 상위. INSIGHT ≠ DECISION."""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.research_insight_intelligence import ledger
from jarvis.research_insight_intelligence import models as M
from jarvis.research_insight_intelligence.engine import ResearchInsightEngine
from jarvis.research_insight_intelligence.models import (
    EVIDENCE_TYPES,
    FORBIDDEN_VERBS,
    GAP_TYPES,
    GENESIS,
    INSIGHT_CATEGORIES,
    INSIGHT_STATES,
    RELATION_TYPES,
    I_ARCHIVED,
    I_CONNECTED,
    I_CREATED,
    I_REVIEWED,
    I_SUPPORTED,
    IllegalInsightTransition,
    UnknownEntityError,
    can_insight_transition,
    content_hash,
    interpret_confidence,
    jaccard,
)
from jarvis.research_insight_intelligence.verify import (
    duplicate_integrity,
    gap_integrity,
    insight_lifecycle_integrity,
    interpretation_integrity,
    lineage_integrity,
    relationship_integrity,
    replay,
    verify_chain,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_insight_intelligence.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchInsightEngine()


def _ins(e, category="PATTERN", statement="regime filter reduces drawdown", conf=0.6, ctx="",
         now=T[0]):
    return e.extract_insight(["rmi:m1"], category, statement, conf, ctx, now, commit=True).insight_id


# ═══════════════ context ═══════════════
def test_create_context(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    c = _eng().create_context("regime-analysis", ["kg:1", "rmi:2"], "regime study", T[0], commit=True)
    assert c.context_id.startswith("IIC:")
    assert c.references == ["kg:1", "rmi:2"]


def test_context_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.create_context("d", [], "desc", T[0], commit=True).context_id
    b = e.create_context("d", ["x"], "desc", T[1], commit=True).context_id
    assert a == b
    assert len(ledger.read_contexts()) == 1


def test_context_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.create_context("d", [], "x", T[0], commit=True)
    assert any(a["artifact_type"] == "CONTEXT" for a in ledger.read_artifacts())


# ═══════════════ insight lifecycle ═══════════════
def test_extract_insight(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().extract_insight(["rmi:1"], "PATTERN", "regime helps", 0.7, "", T[0], commit=True)
    assert ev.to_state == I_CREATED
    assert ev.insight_id.startswith("IIN:")
    assert ev.insight_event_id.startswith("IIE:")


def test_insight_bad_category(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        _eng().extract_insight([], "NOPE", "s", now=T[0], commit=True)


def test_insight_confidence_clamped(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().extract_insight([], "RISK", "s", 5.0, "", T[0], commit=True)
    assert ev.confidence == 1.0


def test_insight_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ins = _ins(e)
    e.support_insight(ins, now=T[1], commit=True)
    ins2 = _ins(e, statement="other", now=T[2])
    e.support_insight(ins2, now=T[3], commit=True)
    e.connect_insights(ins, ins2, "EXTENDS", T[4], commit=True)  # ins → CONNECTED
    e.review_insight(ins, now=T[5], commit=True)
    e.archive_insight(ins, now=T[6], commit=True)
    assert e.insight_state(ins) == I_ARCHIVED


def test_insight_no_skip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ins = _ins(e)
    with pytest.raises(IllegalInsightTransition):
        e.review_insight(ins, now=T[1], commit=True)  # CREATED→REVIEWED skip


def test_insight_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.extract_insight([], "PATTERN", "same", 0.5, "", T[0], commit=True).insight_id
    b = e.extract_insight([], "PATTERN", "same", 0.9, "", T[1], commit=True).insight_id
    assert a == b
    assert len(ledger.insight_events(a)) == 1


def test_insight_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().support_insight("IIN:nope", now=T[1], commit=True)


def test_insights_in_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ins = _ins(e)
    e.support_insight(ins, now=T[1], commit=True)
    assert ins in e.insights_in_state(I_SUPPORTED)


def test_insight_context_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ctx = e.create_context("d", [], "x", T[0], commit=True).context_id
    ins = e.extract_insight([], "PATTERN", "s", 0.5, ctx, T[1], commit=True).insight_id
    arts = {a["artifact_id"]: a for a in ledger.read_artifacts()}
    ins_art = next(a for a in arts.values() if a["ref_id"] == ins)
    assert ins_art["parent_artifact"] == M.artifact_id(M.ART_CONTEXT, ctx)


@pytest.mark.parametrize("frm,to,ok", [
    (I_CREATED, I_SUPPORTED, True), (I_CREATED, I_CONNECTED, False),
    (I_SUPPORTED, I_CONNECTED, True), (I_CONNECTED, I_REVIEWED, True),
    (I_REVIEWED, I_ARCHIVED, True), (I_REVIEWED, I_CONNECTED, True),
    (I_ARCHIVED, I_CONNECTED, False), (I_CREATED, I_ARCHIVED, False),
])
def test_insight_transition_matrix(frm, to, ok):
    assert can_insight_transition(frm, to) is ok


@pytest.mark.parametrize("s", INSIGHT_STATES)
def test_insight_states(s):
    assert s in INSIGHT_STATES


@pytest.mark.parametrize("cat", INSIGHT_CATEGORIES)
def test_insight_categories(tmp_path, monkeypatch, cat):
    _iso(tmp_path, monkeypatch)
    ev = _eng().extract_insight([], cat, f"s-{cat}", 0.5, "", T[0], commit=True)
    assert ev.category == cat


# ═══════════════ evidence interpretation ═══════════════
def test_interpret_evidence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ins = _ins(e)
    it = e.interpret_evidence(ins, "supported by 3 experiments", ["e1", "e2", "e3"], ["e4"],
                              "monitoring", T[1], commit=True)
    assert it.interpretation_id.startswith("IIP:")
    assert it.supporting_count == 3
    assert it.conflicting_count == 1
    assert it.confidence == 0.75


def test_interpret_advances_to_supported(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ins = _ins(e)
    e.interpret_evidence(ins, "explanation", ["e1"], [], "", T[1], commit=True)
    assert e.insight_state(ins) == I_SUPPORTED  # CREATED→SUPPORTED


def test_interpret_creates_evidence_links(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ins = _ins(e)
    e.interpret_evidence(ins, "x", ["e1", "e2"], ["e3"], "monitoring", T[1], commit=True)
    links = ledger.evidence_for(ins)
    assert len(links) == 3
    assert sum(1 for l in links if l["evidence_type"] == "SUPPORTING") == 2
    assert sum(1 for l in links if l["evidence_type"] == "CONFLICTING") == 1


def test_interpret_unknown_insight(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().interpret_evidence("IIN:nope", "x", now=T[0], commit=True)


def test_interpret_confidence_helper():
    assert interpret_confidence(3, 1) == 0.75
    assert interpret_confidence(0, 0) == 0.0
    assert interpret_confidence(5, 0) == 1.0


@pytest.mark.parametrize("et", EVIDENCE_TYPES)
def test_evidence_types(et):
    assert et in EVIDENCE_TYPES


# ═══════════════ gap detection ═══════════════
def test_detect_gap(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    g = _eng().detect_gap("MISSING_VALIDATION", "no OOS test", "walk-forward results", ["IIN:x"],
                          T[0], commit=True)
    assert g.gap_id.startswith("IIG:")
    assert g.gap_type == "MISSING_VALIDATION"


def test_gap_bad_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        _eng().detect_gap("NOPE", "d", now=T[0], commit=True)


@pytest.mark.parametrize("gt", GAP_TYPES)
def test_gap_types(gt):
    assert gt in GAP_TYPES


def test_gap_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.detect_gap("UNEXPLORED_AREA", "d", now=T[0], commit=True).gap_id
    b = e.detect_gap("UNEXPLORED_AREA", "d", now=T[1], commit=True).gap_id
    assert a == b
    assert len(ledger.read_research_gaps()) == 1


# ═══════════════ relationship mapping ═══════════════
def test_connect_insights(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _ins(e, statement="a")
    b = _ins(e, statement="b", now=T[1])
    r = e.connect_insights(a, b, "SUPPORTS", T[2], commit=True)
    assert r.relationship_id.startswith("IIX:")
    assert r.relation_type == "SUPPORTS"


def test_connect_bad_relation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _ins(e, statement="a")
    b = _ins(e, statement="b", now=T[1])
    with pytest.raises(ValueError):
        e.connect_insights(a, b, "NOPE", T[2], commit=True)


def test_connect_unknown_insight(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _ins(e)
    with pytest.raises(UnknownEntityError):
        e.connect_insights(a, "IIN:nope", "SUPPORTS", T[2], commit=True)


def test_connect_advances_supported_to_connected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _ins(e, statement="a")
    b = _ins(e, statement="b", now=T[1])
    e.support_insight(a, now=T[2], commit=True)
    e.connect_insights(a, b, "EXTENDS", T[3], commit=True)
    assert e.insight_state(a) == I_CONNECTED


@pytest.mark.parametrize("rt", RELATION_TYPES)
def test_relation_types(rt):
    assert rt in RELATION_TYPES


def test_relationship_lineage_parent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _ins(e, statement="a")
    b = _ins(e, statement="b", now=T[1])
    r = e.connect_insights(a, b, "SUPPORTS", T[2], commit=True)
    arts = {x["artifact_id"]: x for x in ledger.read_artifacts()}
    rel_art = next(x for x in arts.values() if x["ref_id"] == r.relationship_id)
    assert rel_art["parent_artifact"] == M.artifact_id(M.ART_INSIGHT, a)


# ═══════════════ summarize ═══════════════
def test_summarize(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _ins(e, category="PATTERN", statement="a")
    _ins(e, category="RISK", statement="b", now=T[1])
    e.detect_gap("MISSING_VALIDATION", "g", now=T[2], commit=True)
    s = e.summarize("SYSTEM")
    assert s["insight_count"] == 2
    assert s["category_distribution"].get("PATTERN") == 1
    assert s["gap_distribution"].get("MISSING_VALIDATION") == 1


# ═══════════════ integration READ ONLY ═══════════════
def test_source_layers_present():
    for k in ("knowledge_graph", "decision_intelligence", "simulation", "research_memory",
              "monitoring", "reliability", "autonomous_research", "agent_coordination",
              "memory_intelligence"):
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


def test_source_ref_exists(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    p = sp("kg_entities.jsonl")
    with open(p, "w") as f:
        f.write(json.dumps({"entity_id": "kg:e1"}) + "\n")
    assert ledger.source_ref_exists("knowledge_graph", "kg:e1") is True
    assert ledger.source_ref_exists("knowledge_graph", "kg:zz") is False


def test_all_source_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    counts = ledger.all_source_counts()
    assert set(counts) == set(ledger.SOURCE_LAYERS)


# ═══════════════ verify ═══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_verify_after_activity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ctx = e.create_context("d", [], "x", T[0], commit=True).context_id
    a = e.extract_insight([], "PATTERN", "a", 0.6, ctx, T[1], commit=True).insight_id
    b = e.extract_insight([], "RISK", "b", 0.5, ctx, T[2], commit=True).insight_id
    e.interpret_evidence(a, "explained", ["e1"], [], "monitoring", T[3], commit=True)
    e.connect_insights(a, b, "SUPPORTS", T[4], commit=True)
    e.detect_gap("INSUFFICIENT_SAMPLES", "need more", "n=1000", [a], T[5], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _ins(e)
    p = sp("rii_insights.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["statement"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.detect_gap("MISSING_VALIDATION", "g1", now=T[0], commit=True)
    e.detect_gap("UNEXPLORED_AREA", "g2", now=T[1], commit=True)
    p = sp("rii_research_gaps.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:bad"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_duplicate_insight(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _ins(e)
    p = sp("rii_insights.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    with open(p, "a") as f:
        f.write(json.dumps(rows[0]) + "\n")
    assert verify_chain()["ok"] is False


def test_insight_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ins = _ins(e)
    e.support_insight(ins, now=T[1], commit=True)
    assert insight_lifecycle_integrity()["ok"] is True


def test_duplicate_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _ins(e, statement="a")
    _ins(e, statement="b", now=T[1])
    assert duplicate_integrity()["ok"] is True


def test_interpretation_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ins = _ins(e)
    e.interpret_evidence(ins, "x", ["e1"], [], "monitoring", T[1], commit=True)
    assert interpretation_integrity()["ok"] is True


def test_interpretation_integrity_detects_bad_evidence_type(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    ins = _ins(e)
    e.interpret_evidence(ins, "x", ["e1"], [], "monitoring", T[1], commit=True)
    p = sp("rii_evidence_links.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["evidence_type"] = "HACKED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert interpretation_integrity()["ok"] is False


def test_gap_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.detect_gap("CONTRADICTORY_RESULTS", "g", now=T[0], commit=True)
    assert gap_integrity()["ok"] is True


def test_relationship_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _ins(e, statement="a")
    b = _ins(e, statement="b", now=T[1])
    e.connect_insights(a, b, "DEPENDS_ON", T[2], commit=True)
    assert relationship_integrity()["ok"] is True


def test_relationship_integrity_detects_bad_relation(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _ins(e, statement="a")
    b = _ins(e, statement="b", now=T[1])
    e.connect_insights(a, b, "SUPPORTS", T[2], commit=True)
    p = sp("rii_relationships.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["relation_type"] = "HACKED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert relationship_integrity()["ok"] is False


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ctx = e.create_context("d", [], "x", T[0], commit=True).context_id
    a = e.extract_insight([], "PATTERN", "a", 0.5, ctx, T[1], commit=True).insight_id
    b = e.extract_insight([], "RISK", "b", 0.5, ctx, T[2], commit=True).insight_id
    e.interpret_evidence(a, "x", ["e1"], [], "monitoring", T[3], commit=True)
    e.connect_insights(a, b, "SUPPORTS", T[4], commit=True)
    assert lineage_integrity()["ok"] is True


# ═══════════════ replay ═══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _ins(e)
    e.detect_gap("MISSING_VALIDATION", "g", now=T[1], commit=True)
    assert replay(e, T[9])["deterministic"] is True


# ═══════════════ report ═══════════════
def test_generate_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _ins(e, category="OPPORTUNITY", statement="a")
    b = _ins(e, category="RISK", statement="b", now=T[1])
    e.connect_insights(a, b, "CONTRADICTS", T[2], commit=True)
    e.detect_gap("UNEXPLORED_AREA", "g", now=T[3], commit=True)
    r = e.generate_report("SYSTEM", T[4], commit=True)
    assert r.report_id.startswith("IIO:")
    assert r.is_binding is False
    assert r.insight_count == 2
    assert r.gap_count == 1
    assert r.relationship_count == 1
    assert r.category_distribution.get("OPPORTUNITY") == 1


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("SYSTEM", T[0], commit=True)
    assert "DECISION" in r.disclaimer


# ═══════════════ 금지 동사 ═══════════════
@pytest.mark.parametrize("verb", sorted(FORBIDDEN_VERBS))
def test_forbidden_verb(verb):
    assert M.is_forbidden_verb(verb) is True


@pytest.mark.parametrize("verb", ["INTERPRET", "EXPLAIN", "SUMMARIZE", "CONNECT", "UNDERSTAND",
                                  "ANALYZE"])
def test_allowed_verb(verb):
    assert M.is_forbidden_verb(verb) is False


@pytest.mark.parametrize("v", ["EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL",
                                "DEPLOY_STRATEGY", "ACTIVATE_LIVE", "APPROVE_FOR_TRADING",
                                "SELECT_STRATEGY"])
def test_forbidden_membership(v):
    assert v in FORBIDDEN_VERBS


def test_forbidden_empty():
    assert M.is_forbidden_verb("") is False


# ═══════════════ ID / hash ═══════════════
@pytest.mark.parametrize("fn,args,prefix", [
    (M.insight_id, ("PATTERN", "s"), "IIN:"),
    (M.insight_event_id, ("i", "CREATED", 0), "IIE:"),
    (M.context_id, ("d", "desc"), "IIC:"),
    (M.interpretation_id, ("i", 0), "IIP:"),
    (M.evidence_link_id, ("i", "e", 0), "IIL:"),
    (M.gap_id, ("MISSING_VALIDATION", "d"), "IIG:"),
    (M.relationship_id, ("s", "t", "SUPPORTS"), "IIX:"),
    (M.report_id, ("s", "t"), "IIO:"),
    (M.artifact_id, ("INSIGHT", "r"), "IIA:"),
])
def test_id_prefixes(fn, args, prefix):
    assert fn(*args).startswith(prefix)


def test_ids_deterministic():
    assert M.insight_id("PATTERN", "s") == M.insight_id("PATTERN", "s")


def test_content_hash_excludes_meta():
    a = content_hash({"x": 1, "previous_hash": "p", "record_hash": "r"})
    b = content_hash({"x": 1, "previous_hash": "Q", "record_hash": "Z"})
    assert a == b


def test_jaccard():
    assert jaccard("a b", "a b") == 1.0
    assert jaccard("a", "b") == 0.0


# ═══════════════ summary ═══════════════
def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ins = _ins(e)
    e.interpret_evidence(ins, "x", ["e1"], [], "monitoring", T[1], commit=True)
    e.detect_gap("MISSING_VALIDATION", "g", now=T[2], commit=True)
    s = e.summary(T[9])
    assert s.insight_count == 1
    assert s.interpretation_count == 1
    assert s.gap_count == 1


def test_list_insights(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _ins(e, statement="a")
    _ins(e, statement="b", now=T[1])
    assert len(e.list_insights()) == 2


# ═══════════════ CLI ═══════════════
def test_cli_context(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_insight_intelligence.__main__ import main
    assert main(["context", "--domain", "regime", "--description", "study", "--refs", "kg:1",
                 "--commit"]) == 0


def test_cli_insight(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_insight_intelligence.__main__ import main
    assert main(["insight", "--category", "PATTERN", "--statement", "regime helps",
                 "--confidence", "0.7", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["insight"]["to_state"] == "CREATED"


def test_cli_interpret(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_insight_intelligence.__main__ import main
    main(["insight", "--category", "PATTERN", "--statement", "s", "--commit"])
    ins = json.loads(capsys.readouterr().out)["insight"]["insight_id"]
    assert main(["interpret", "--insight", ins, "--explanation", "x", "--supporting", "e1|e2",
                 "--conflicting", "e3", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["interpretation"]["supporting_count"] == 2


def test_cli_gap(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_insight_intelligence.__main__ import main
    assert main(["gap", "--type", "MISSING_VALIDATION", "--description", "no oos",
                 "--commit"]) == 0


def test_cli_relationship(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_insight_intelligence.__main__ import main
    main(["insight", "--category", "PATTERN", "--statement", "a", "--commit"])
    src = json.loads(capsys.readouterr().out)["insight"]["insight_id"]
    main(["insight", "--category", "RISK", "--statement", "b", "--commit"])
    tgt = json.loads(capsys.readouterr().out)["insight"]["insight_id"]
    assert main(["relationship", "--source", src, "--target", tgt, "--relation", "SUPPORTS",
                 "--commit"]) == 0


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_insight_intelligence.__main__ import main
    assert main(["report", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["report"]["is_binding"] is False


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_insight_intelligence.__main__ import main
    assert main(["verify"]) == 0


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_insight_intelligence.__main__ import main
    assert main(["summary"]) == 0


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_insight_intelligence.__main__ import main
    assert main(["replay"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["deterministic"] is True


# ═══════════════ 격리 / ledger ═══════════════
def test_records_frozen(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().extract_insight([], "PATTERN", "s", now=T[0], commit=True)
    with pytest.raises(Exception):
        ev.statement = "x"


def test_eight_ledgers():
    assert len(ledger.ALL_LEDGERS) == 8


def test_ledger_filenames_prefixed():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("rii_")


def test_required_ledgers_present():
    names = {f for f, _ in ledger.ALL_LEDGERS}
    for req in ("rii_insights.jsonl", "rii_contexts.jsonl", "rii_interpretations.jsonl",
                "rii_evidence_links.jsonl", "rii_research_gaps.jsonl", "rii_relationships.jsonl",
                "rii_reports.jsonl", "rii_artifacts.jsonl"):
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
    # 상위 소스 시드(READ ONLY 대상): P27 memory + P10.5 KG
    with open(sp("rmi_memories.jsonl"), "w") as f:
        f.write(json.dumps({"memory_event_id": "rmi:m1"}) + "\n")
    with open(sp("kg_entities.jsonl"), "w") as f:
        f.write(json.dumps({"entity_id": "kg:regime"}) + "\n")
    e = _eng()
    # 맥락 구축
    ctx = e.create_context("regime-robustness", ["kg:regime", "rmi:m1"],
                           "regime filter robustness study", T[0], commit=True).context_id
    # 통찰 추출(이해·설명만)
    a = e.extract_insight(["rmi:m1"], "PATTERN", "regime filter reduces drawdown across regimes",
                          0.7, ctx, T[1], commit=True).insight_id
    b = e.extract_insight(["kg:regime"], "LIMITATION", "only validated on 2 regimes", 0.5, ctx, T[2],
                          commit=True).insight_id
    # 증거 해석(지지/상충) → SUPPORTED 전이
    it = e.interpret_evidence(a, "3 experiments support, 1 conflicts", ["e1", "e2", "e3"], ["e4"],
                              "monitoring", T[3], commit=True)
    assert it.confidence == 0.75
    assert e.insight_state(a) == I_SUPPORTED
    # 관계 매핑(CONTRADICTS) → a CONNECTED
    e.connect_insights(a, b, "CONTRADICTS", T[4], commit=True)
    assert e.insight_state(a) == I_CONNECTED
    # 연구 공백 탐지
    e.detect_gap("INSUFFICIENT_SAMPLES", "only 2 regimes tested", "more regime samples", [a, b], T[5],
                 commit=True)
    # 검토 → 리포트
    e.review_insight(a, now=T[6], commit=True)
    r = e.generate_report("SYSTEM", T[7], commit=True)
    assert r.insight_count == 2
    assert r.gap_count == 1
    assert r.relationship_count == 1
    assert r.is_binding is False  # INSIGHT ≠ DECISION
    e.archive_insight(a, now=T[8], commit=True)
    assert e.insight_state(a) == I_ARCHIVED
    assert open(sp("rmi_memories.jsonl")).read()  # 상위 원장 여전히 존재·불변
    assert verify_chain()["ok"] is True
    assert replay(e, T[9])["deterministic"] is True
