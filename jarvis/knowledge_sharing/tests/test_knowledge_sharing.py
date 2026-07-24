"""P11.8 Cross-Agent Knowledge Sharing 테스트. **에이전트 간 지식 공유 — 공유·기록 전용.**

레지스트리·토픽(그래프·순환 거부)·소스(READ ONLY)·지식 발행(13유형·중복 불변·계보)·링크(dangling/순환/자기 거부)·
공유(전달·PUBLISHED→SHARED)·소비(SHARED→CONSUMED)·평가(1~5·불변)·재사용 점수(결정적·CONSUMED→REUSED)·스냅샷
(결정적)·리포트·verify(체인/변조/중복/생애주기/참조/순환/계보)·replay·CLI·보안(금지import·실행/승인/배포/상위수정
없음·삭제 API 없음·불변·SHARING≠EXECUTION·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import json
import os

import pytest

from jarvis.knowledge_sharing import ledger
from jarvis.knowledge_sharing import models as M
from jarvis.knowledge_sharing.engine import KnowledgeSharingEngine
from jarvis.knowledge_sharing.models import (
    K_ARCHIVED,
    K_CONSUMED,
    K_CREATED,
    K_PUBLISHED,
    K_REUSED,
    K_SHARED,
    KT_FINDING,
    KT_LESSON_LEARNED,
    KT_SIGNAL,
    LINK_ENTRY_RELATED,
    LINK_ENTRY_TOPIC,
    LINK_TOPIC_PARENT,
    LINK_TOPIC_RELATED,
    CircularReferenceError,
    DanglingReferenceError,
    IllegalEntryTransition,
    ImmutableEntryError,
    ImmutableRatingError,
    ImmutableTopicError,
    InvalidKnowledgeType,
    InvalidLineageError,
    InvalidLinkType,
    InvalidRating,
    SelfReferenceError,
    UnknownEntryError,
    UnknownRegistryError,
    UnknownTopicError,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(40)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.knowledge_sharing.ledger.state_path", sp)
    return sp


def _eng():
    return KnowledgeSharingEngine()


def _reg(e, name="research_kb", now=T[0]):
    return e.register_registry(name, "share knowledge", now, commit=True).registry_id


def _topic(e, reg=None, name="momentum", now=T[0]):
    if reg is None:
        reg = _reg(e, now=now)
    return e.register_topic(reg, name, "momentum research", "", now, commit=True).topic_id


def _entry(e, topic=None, title="momentum decays", ktype=KT_FINDING, author="alpha_agent",
           content="12m momentum decays post-2000", now=T[0]):
    if topic is None:
        topic = _topic(e, now=now)
    return e.publish_knowledge(topic, title, ktype, content, author, "", "", now,
                               commit=True).entry_id


# ══════════════ registry / topic ══════════════
def test_registry_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().register_registry("kb", "m", T[0], commit=True)
    assert r.registry_id.startswith("KSG:")


def test_registry_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _reg(e)
    _reg(e, now=T[1])
    assert len(ledger.read_registry()) == 1


def test_topic_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    t = e.register_topic(_reg(e), "momentum", "d", "", T[0], commit=True)
    assert t.topic_id.startswith("KST:")


def test_topic_unknown_registry(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownRegistryError):
        _eng().register_topic("KSG:ghost", "t", "", "", T[0], commit=True)


def test_topic_parent_graph(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg = _reg(e)
    parent = e.register_topic(reg, "factors", "", "", T[0], commit=True).topic_id
    child = e.register_topic(reg, "momentum", "", parent, T[1], commit=True).topic_id
    assert child in e.topic_children(parent)
    assert any(l["link_type"] == "TOPIC_PARENT" for l in ledger.read_links())


def test_topic_parent_dangling(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg = _reg(e)
    with pytest.raises(DanglingReferenceError):
        e.register_topic(reg, "t", "", "KST:ghost", T[0], commit=True)


def test_topic_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg = _reg(e)
    p = e.register_topic(reg, "factors", "", "", T[0], commit=True).topic_id
    e.register_topic(reg, "momentum", "", "", T[1], commit=True)
    with pytest.raises(ImmutableTopicError):
        e.register_topic(reg, "momentum", "", p, T[2], commit=True)


def test_topic_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _topic(e)
    assert any(a["artifact_type"] == "TOPIC" for a in ledger.read_artifacts())


# ══════════════ register_source (READ ONLY) ══════════════
def test_source_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().register_source("research_kg", "ent1", "d", T[0], commit=True)
    assert s.source_id.startswith("KSS:")
    assert s.read_only is True


def test_source_verify_ref(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("kg_entities.jsonl"), "w") as f:
        f.write(json.dumps({"entity_id": "ent1"}) + "\n")
    s = _eng().register_source("research_kg", "ent1", "", T[0], commit=True, verify_ref=True)
    assert s.ref == "ent1"


def test_source_verify_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(DanglingReferenceError):
        _eng().register_source("research_kg", "ghost", "", T[0], commit=True, verify_ref=True)


def test_source_never_writes_upstream(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("kg_entities.jsonl"), "w") as f:
        f.write(json.dumps({"entity_id": "ent1"}) + "\n")
    before = open(sp("kg_entities.jsonl")).read()
    _eng().register_source("research_kg", "ent1", "", T[0], commit=True, verify_ref=True)
    assert open(sp("kg_entities.jsonl")).read() == before


# ══════════════ publish_knowledge (lifecycle CREATED→PUBLISHED) ══════════════
def test_publish_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    topic = _topic(e)
    ev = e.publish_knowledge(topic, "finding X", KT_FINDING, "content", "agent", "", "", T[0],
                             commit=True)
    assert ev.entry_id.startswith("KSE:")
    assert ev.to_state == K_PUBLISHED
    assert e.entry_state(ev.entry_id) == K_PUBLISHED


def test_publish_creates_created_then_published(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    topic = _topic(e)
    ev = e.publish_knowledge(topic, "t", KT_FINDING, "c", "a", "", "", T[0], commit=True)
    states = [x["to_state"] for x in ledger.entry_events(ev.entry_id)]
    assert states == [K_CREATED, K_PUBLISHED]


def test_publish_invalid_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    topic = _topic(e)
    with pytest.raises(InvalidKnowledgeType):
        e.publish_knowledge(topic, "t", "GOSSIP", "c", "a", "", "", T[0], commit=True)


def test_publish_unknown_topic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownTopicError):
        _eng().publish_knowledge("KST:ghost", "t", KT_FINDING, "c", "a", "", "", T[0], commit=True)


def test_publish_duplicate_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    topic = _topic(e)
    e.publish_knowledge(topic, "t", KT_FINDING, "c1", "a", "", "", T[0], commit=True)
    with pytest.raises(ImmutableEntryError):
        e.publish_knowledge(topic, "t", KT_FINDING, "c2", "a", "", "", T[1], commit=True)


def test_publish_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    topic = _topic(e)
    e.publish_knowledge(topic, "t", KT_FINDING, "c", "a", "", "", T[0], commit=True)
    e.publish_knowledge(topic, "t", KT_FINDING, "c", "a", "", "", T[1], commit=True)
    assert len(ledger.entry_ids()) == 1


@pytest.mark.parametrize("ktype", list(M.KNOWLEDGE_TYPES))
def test_publish_all_13_types(tmp_path, monkeypatch, ktype):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    topic = _topic(e)
    ev = e.publish_knowledge(topic, f"t_{ktype}", ktype, "c", "a", "", "", T[0], commit=True)
    assert e.entry_meta(ev.entry_id)["knowledge_type"] == ktype


def test_thirteen_knowledge_types():
    assert len(M.KNOWLEDGE_TYPES) == 13


# ══════════════ lineage (parent_entry) ══════════════
def test_publish_with_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    topic = _topic(e)
    p = _entry(e, topic, "base finding")
    c = e.publish_knowledge(topic, "derived finding", KT_FINDING, "builds on base", "a2", "", p,
                            T[1], commit=True)
    assert e.trace_lineage(c.entry_id) == [p]
    assert len(ledger.read_lineage()) == 1


def test_lineage_dangling_parent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    topic = _topic(e)
    with pytest.raises(DanglingReferenceError):
        e.publish_knowledge(topic, "t", KT_FINDING, "c", "a", "", "KSE:ghost", T[0], commit=True)


def test_lineage_cycle_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    topic = _topic(e)
    a = _entry(e, topic, "a")
    b = e.publish_knowledge(topic, "b", KT_FINDING, "c", "a2", "", a, T[1], commit=True).entry_id
    # a derives from b would create a<->b cycle; a already exists so re-publish path differs.
    # 대신 새 엔트리 c 가 b 파생, 그리고 b 를 c 파생으로 만들 수 없음(이미 존재). 순환은 detect 로 보장.
    from jarvis.knowledge_sharing.models import detect_cycle
    assert detect_cycle([(b, a), (a, b)]) != []


# ══════════════ link_knowledge ══════════════
def test_link_topic_related(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg = _reg(e)
    t1 = e.register_topic(reg, "a", "", "", T[0], commit=True).topic_id
    t2 = e.register_topic(reg, "b", "", "", T[1], commit=True).topic_id
    l = e.link_knowledge(LINK_TOPIC_RELATED, t1, t2, "related", T[2], commit=True)
    assert l.link_id.startswith("KSL:")


def test_link_invalid_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(InvalidLinkType):
        _eng().link_knowledge("BOGUS", "a", "b", "", T[0], commit=True)


def test_link_self_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    t = _topic(e)
    with pytest.raises(SelfReferenceError):
        e.link_knowledge(LINK_TOPIC_RELATED, t, t, "", T[0], commit=True)


def test_link_dangling_topic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    t = _topic(e)
    with pytest.raises(DanglingReferenceError):
        e.link_knowledge(LINK_TOPIC_RELATED, t, "KST:ghost", "", T[0], commit=True)


def test_link_entry_related_cycle_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    topic = _topic(e)
    a = _entry(e, topic, "a")
    b = e.publish_knowledge(topic, "b", KT_FINDING, "c", "a2", "", "", T[1], commit=True).entry_id
    e.link_knowledge(LINK_ENTRY_RELATED, a, b, "", T[2], commit=True)
    with pytest.raises(CircularReferenceError):
        e.link_knowledge(LINK_ENTRY_RELATED, b, a, "", T[3], commit=True)


def test_link_entry_topic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    topic = _topic(e)
    a = _entry(e, topic, "a")
    l = e.link_knowledge(LINK_ENTRY_TOPIC, a, topic, "belongs", T[2], commit=True)
    assert l.link_type == LINK_ENTRY_TOPIC


def test_link_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg = _reg(e)
    t1 = e.register_topic(reg, "a", "", "", T[0], commit=True).topic_id
    t2 = e.register_topic(reg, "b", "", "", T[1], commit=True).topic_id
    e.link_knowledge(LINK_TOPIC_RELATED, t1, t2, "", T[2], commit=True)
    e.link_knowledge(LINK_TOPIC_RELATED, t1, t2, "", T[3], commit=True)
    assert len(ledger.read_links()) == 1


# ══════════════ share_with_agent (PUBLISHED→SHARED) ══════════════
def test_share(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    entry = _entry(e)
    t = e.share_with_agent(entry, "alpha_agent", "risk_agent", "fyi", T[1], commit=True)
    assert t.transfer_id.startswith("KSX:")
    assert e.entry_state(entry) == K_SHARED


def test_share_unknown_entry(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntryError):
        _eng().share_with_agent("KSE:ghost", "a", "b", "", T[0], commit=True)


def test_share_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    entry = _entry(e)
    e.share_with_agent(entry, "a", "b", "", T[1], commit=True)
    e.share_with_agent(entry, "a", "b", "", T[2], commit=True)
    assert len(ledger.entry_transfers(entry)) == 1


def test_share_multiple_agents(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    entry = _entry(e)
    e.share_with_agent(entry, "a", "b", "", T[1], commit=True)
    e.share_with_agent(entry, "a", "c", "", T[2], commit=True)
    assert len(ledger.entry_transfers(entry)) == 2


# ══════════════ record_consumption (SHARED→CONSUMED) ══════════════
def test_consume(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    entry = _entry(e)
    e.share_with_agent(entry, "a", "b", "", T[1], commit=True)
    c = e.record_consumption(entry, "b", False, "used it", T[2], commit=True)
    assert c.consumer_id.startswith("KSC:")
    assert e.entry_state(entry) == K_CONSUMED


def test_consume_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    entry = _entry(e)
    e.share_with_agent(entry, "a", "b", "", T[1], commit=True)
    e.record_consumption(entry, "b", False, "", T[2], commit=True)
    e.record_consumption(entry, "b", False, "", T[3], commit=True)
    assert len(ledger.entry_consumers(entry)) == 1


# ══════════════ record_feedback (rating) ══════════════
def test_feedback(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    entry = _entry(e)
    r = e.record_feedback(entry, "b", 5, "excellent", T[1], commit=True)
    assert r.rating_id.startswith("KSR:")
    assert r.score == 5


def test_feedback_invalid_score(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    entry = _entry(e)
    with pytest.raises(InvalidRating):
        e.record_feedback(entry, "b", 6, "", T[1], commit=True)


def test_feedback_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    entry = _entry(e)
    e.record_feedback(entry, "b", 4, "", T[1], commit=True)
    with pytest.raises(ImmutableRatingError):
        e.record_feedback(entry, "b", 2, "", T[2], commit=True)


@pytest.mark.parametrize("score", [1, 2, 3, 4, 5])
def test_feedback_valid_scores(tmp_path, monkeypatch, score):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    entry = _entry(e)
    r = e.record_feedback(entry, f"agent{score}", score, "", T[1], commit=True)
    assert r.score == score


# ══════════════ calculate_reuse_score (CONSUMED→REUSED) ══════════════
def test_reuse_score(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    entry = _entry(e)
    e.share_with_agent(entry, "a", "b", "", T[1], commit=True)
    e.record_consumption(entry, "b", True, "", T[2], commit=True)
    res = e.calculate_reuse_score(entry, T[3], commit=True)
    assert res["reuse_score"] > 0
    assert res["reused"] is True
    assert e.entry_state(entry) == K_REUSED


def test_reuse_score_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    entry = _entry(e)
    e.share_with_agent(entry, "a", "b", "", T[1], commit=True)
    e.record_consumption(entry, "b", False, "", T[2], commit=True)
    a = e.calculate_reuse_score(entry, T[3], commit=False)
    b = e.calculate_reuse_score(entry, T[4], commit=False)
    assert a["reuse_score"] == b["reuse_score"]


def test_reuse_score_pure():
    assert M.reuse_score(0, 0, 0.0, 0) == 0.0
    assert M.reuse_score(3, 3, 5.0, 2) == 1.0


def test_reuse_via_derived(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    topic = _topic(e)
    base = _entry(e, topic, "base")
    e.share_with_agent(base, "a", "b", "", T[1], commit=True)
    e.record_consumption(base, "b", False, "", T[2], commit=True)
    e.publish_knowledge(topic, "derived", KT_FINDING, "c", "a2", "", base, T[3], commit=True)
    res = e.calculate_reuse_score(base, T[4], commit=True)
    assert res["derived"] == 1
    assert res["reused"] is True


# ══════════════ snapshot (deterministic) ══════════════
def test_snapshot_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _entry(e)
    s = e.snapshot_knowledge("GLOBAL", T[1], commit=True)
    assert s.snapshot_id.startswith("KSN:")
    assert s.entry_count == 1


def test_snapshot_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _entry(e)
    a = e.snapshot_knowledge("GLOBAL", T[1], commit=False)
    b = e.snapshot_knowledge("GLOBAL", T[2], commit=False)
    assert a.content_digest == b.content_digest


def test_snapshot_state_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    entry = _entry(e)
    e.share_with_agent(entry, "a", "b", "", T[1], commit=True)
    s = e.snapshot_knowledge("GLOBAL", T[2], commit=True)
    assert s.state_distribution.get(K_SHARED) == 1


# ══════════════ generate_report ══════════════
def test_report_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _entry(e)
    r = e.generate_report("GLOBAL", T[1], commit=True)
    assert r.report_id.startswith("KSP:")
    assert r.entry_count == 1
    assert r.is_binding is False


def test_report_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _entry(e)
    a = e.generate_report("GLOBAL", T[1], commit=False)
    b = e.generate_report("GLOBAL", T[1], commit=False)
    assert a.to_dict() == b.to_dict()


def test_report_has_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    r = e.generate_report("GLOBAL", T[0], commit=True)
    assert "SHARING ≠ EXECUTION" in r.disclaimer


# ══════════════ verify / replay ══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.knowledge_sharing.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_after_full_workflow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.knowledge_sharing.verify import verify_chain
    e = _eng()
    topic = _topic(e)
    a = _entry(e, topic, "a")
    b = e.publish_knowledge(topic, "b", KT_FINDING, "c", "a2", "", a, T[1], commit=True).entry_id
    e.link_knowledge(LINK_ENTRY_RELATED, a, b, "", T[2], commit=True)
    e.share_with_agent(a, "x", "y", "", T[3], commit=True)
    e.record_consumption(a, "y", True, "", T[4], commit=True)
    e.record_feedback(a, "y", 5, "great", T[5], commit=True)
    e.calculate_reuse_score(a, T[6], commit=True)
    e.snapshot_knowledge("GLOBAL", T[7], commit=True)
    e.generate_report("GLOBAL", T[8], commit=True)
    res = verify_chain()
    assert res["ok"] is True
    assert res["lifecycle"]["ok"]
    assert res["reference"]["ok"]
    assert res["cycle"]["ok"]
    assert res["lineage"]["ok"]


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _entry(e)
    fp = sp("ksh_entries.jsonl")
    rows = [json.loads(x) for x in open(fp)]
    rows[0]["content"] = "TAMPERED"
    with open(fp, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.knowledge_sharing.verify import verify_chain
    assert verify_chain()["ok"] is False


def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.knowledge_sharing.verify import replay
    e = _eng()
    _entry(e)
    assert replay(e, T[1])["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    entry = _entry(e)
    e.share_with_agent(entry, "a", "b", "", T[1], commit=True)
    e.record_feedback(entry, "b", 5, "", T[2], commit=True)
    s = e.summary(T[3])
    assert s.transfer_count == 1
    assert s.rating_count == 1
    assert s.entry_event_count == 3  # created, published, shared


# ══════════════ 보안 / 불변식 ══════════════
def test_no_forbidden_imports():
    import ast
    fp = ("execution", "broker", "portfolio", "risk", "permission", "deployment", "live",
          "order", "capital_allocation", "live_trading", "risk_controller", "portfolio_execution")
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
                if not m.startswith("jarvis."):
                    continue
                sub = m[len("jarvis."):]
                for f in fp:
                    assert not (sub == f or sub.startswith(f)), (fn, m)


def test_engine_no_execution_methods():
    e = KnowledgeSharingEngine()
    for bad in ("execute", "trade", "deploy", "broker", "modify_portfolio", "allocate",
                "permission", "promote_strategy", "promote_model", "auto_approve", "approve",
                "activate"):
        assert not hasattr(e, bad), bad


def test_no_execution_verbs_in_source():
    base = os.path.dirname(os.path.dirname(__file__))
    for fn in ("engine.py", "models.py"):
        src = open(os.path.join(base, fn)).read()
        for bad in ("def execute", "def trade", "def deploy", "def broker", "def allocate",
                    "def promote_strategy", "def promote_model", "def modify_portfolio",
                    "def auto_approve"):
            assert bad not in src, (fn, bad)


def test_forbidden_verbs_defined():
    for v in ("EXECUTE", "TRADE", "DEPLOY", "BROKER", "PROMOTE_STRATEGY", "PROMOTE_MODEL",
              "AUTO_APPROVE"):
        assert M.is_forbidden_verb(v) is True
    assert M.is_forbidden_verb("SHARE") is False


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


def test_disclaimer_marks_no_execution():
    from jarvis.knowledge_sharing.engine import _DISCLAIMER
    assert "SHARING ≠ EXECUTION" in _DISCLAIMER
    assert "REUSE ≠ APPROVAL" in _DISCLAIMER


def test_all_sources_read_only(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_source("research_kg", "e1", "", T[0], commit=True)
    for s in ledger.read_sources():
        assert s["read_only"] is True


def test_all_reports_not_binding(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.generate_report("GLOBAL", T[0], commit=True)
    for r in ledger.read_reports():
        assert r["is_binding"] is False


def test_records_frozen():
    r = M.EntryEventRecord(entry_event_id="KEE:x", entry_id="KSE:e", topic_id="KST:t", title="t",
                           knowledge_type="FINDING", content="c", author="a", source_id="",
                           from_state="CREATED", to_state="PUBLISHED", note="", occurred_at=T[0])
    with pytest.raises(Exception):
        r.content = "z"  # type: ignore


def test_only_ksh_files_written(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    entry = _entry(e)
    e.share_with_agent(entry, "a", "b", "", T[1], commit=True)
    e.record_consumption(entry, "b", False, "", T[2], commit=True)
    e.record_feedback(entry, "b", 5, "", T[3], commit=True)
    e.snapshot_knowledge("GLOBAL", T[4], commit=True)
    e.generate_report("GLOBAL", T[5], commit=True)
    for fn in os.listdir(tmp_path):
        assert fn.startswith("ksh_"), fn


# ══════════════ 커버리지: id 접두사·상수 ══════════════
def test_id_prefixes_distinct():
    ids = {M.registry_id("n")[:4], M.topic_id("n")[:4], M.entry_id("t", "ti", "a")[:4],
           M.entry_event_id("e", "s", 0)[:4], M.source_id("l", "r")[:4],
           M.link_id("t", "s", "d")[:4], M.transfer_id("e", "f", "t")[:4],
           M.consumer_id("e", "a")[:4], M.rating_id("e", "a")[:4], M.snapshot_id("s", T[0])[:4],
           M.report_id("s", T[0])[:4], M.artifact_id("t", "r")[:4], M.lineage_id("c", "p")[:4]}
    assert len(ids) == 13


def test_twelve_owned_ledgers():
    assert len(ledger.ALL_LEDGERS) == 12
    fns = {l[0] for l in ledger.ALL_LEDGERS}
    assert len(fns) == 12
    assert all(f.startswith("ksh_") for f in fns)


def test_six_entry_states():
    assert len(M.ENTRY_STATES) == 6


def test_four_link_types():
    assert len(M.LINK_TYPES) == 4


def test_content_hash_excludes_hash_fields():
    r = {"a": 1, "previous_hash": "p", "record_hash": "r"}
    assert M.content_hash(r) == M.content_hash({"a": 1, "previous_hash": "z", "record_hash": "q"})


def test_detect_cycle_pure():
    assert M.detect_cycle([("a", "b")]) == []
    cyc = M.detect_cycle([("a", "b"), ("b", "a")])
    assert cyc and cyc[0] == cyc[-1]


def test_ancestors_pure():
    assert M.ancestors([("a", "b"), ("b", "c")], "a") == ["b", "c"]


def test_can_transition_pure():
    assert M.can_transition(K_PUBLISHED, K_SHARED) is True
    assert M.can_transition(K_PUBLISHED, K_REUSED) is False


# ══════════════ 추가 커버리지 ══════════════
@pytest.mark.parametrize("frm,to,ok", [
    (K_CREATED, K_PUBLISHED, True), (K_PUBLISHED, K_SHARED, True), (K_SHARED, K_CONSUMED, True),
    (K_CONSUMED, K_REUSED, True), (K_REUSED, K_ARCHIVED, True), (K_PUBLISHED, K_ARCHIVED, True),
    (K_CREATED, K_SHARED, False), (K_PUBLISHED, K_CONSUMED, False), (K_ARCHIVED, K_PUBLISHED, False),
])
def test_transition_matrix(frm, to, ok):
    assert M.can_transition(frm, to) is ok


def test_archive_knowledge(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    entry = _entry(e)
    e.archive_knowledge(entry, T[1], commit=True)
    assert e.entry_state(entry) == K_ARCHIVED


def test_topic_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg = _reg(e)
    e.register_topic(reg, "t", "", "", T[0], commit=False)
    assert ledger.read_topics() == []


def test_publish_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    topic = _topic(e)
    e.publish_knowledge(topic, "t", KT_FINDING, "c", "a", "", "", T[0], commit=False)
    assert ledger.read_entry_events() == []


def test_share_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    entry = _entry(e)
    e.share_with_agent(entry, "a", "b", "", T[1], commit=False)
    assert ledger.read_transfers() == []


def test_feedback_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    entry = _entry(e)
    e.record_feedback(entry, "b", 5, "", T[1], commit=False)
    assert ledger.read_ratings() == []


def test_list_entries_by_topic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg = _reg(e)
    t1 = e.register_topic(reg, "t1", "", "", T[0], commit=True).topic_id
    t2 = e.register_topic(reg, "t2", "", "", T[1], commit=True).topic_id
    a = e.publish_knowledge(t1, "a", KT_FINDING, "c", "x", "", "", T[2], commit=True).entry_id
    e.publish_knowledge(t2, "b", KT_FINDING, "c", "x", "", "", T[3], commit=True)
    assert e.list_entries(t1) == [a]


def test_list_topics(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    t = _topic(e)
    assert t in e.list_topics()


def test_topic_deep_chain_no_cycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg = _reg(e)
    prev = ""
    for i in range(5):
        prev = e.register_topic(reg, f"t{i}", "", prev, T[i], commit=True).topic_id
    from jarvis.knowledge_sharing.verify import cycle_integrity
    assert cycle_integrity()["ok"] is True


def test_entry_meta_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntryError):
        _eng().entry_meta("KSE:ghost")


def test_lesson_learned_and_signal_types(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    topic = _topic(e)
    a = e.publish_knowledge(topic, "lesson", KT_LESSON_LEARNED, "c", "x", "", "", T[0],
                            commit=True)
    b = e.publish_knowledge(topic, "signal", KT_SIGNAL, "c", "x", "", "", T[1], commit=True)
    assert e.entry_meta(a.entry_id)["knowledge_type"] == KT_LESSON_LEARNED
    assert e.entry_meta(b.entry_id)["knowledge_type"] == KT_SIGNAL


def test_reference_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.knowledge_sharing.verify import reference_integrity
    e = _eng()
    topic = _topic(e)
    a = _entry(e, topic, "a")
    e.link_knowledge(LINK_ENTRY_TOPIC, a, topic, "", T[1], commit=True)
    assert reference_integrity()["ok"] is True


def test_snapshot_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _entry(e)
    e.snapshot_knowledge("GLOBAL", T[1], commit=True)
    assert any(a["artifact_type"] == "SNAPSHOT" for a in ledger.read_artifacts())


# ══════════════ CLI ══════════════
def _run(argv, capsys):
    from jarvis.knowledge_sharing.__main__ import main
    rc = main(argv)
    return rc, capsys.readouterr().out


def test_cli_registry_topic_publish(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["registry", "--name", "kb", "--commit"], capsys)
    reg = json.loads(out)["registry"]["registry_id"]
    rc2, out2 = _run(["topic", "--registry", reg, "--name", "mom", "--commit"], capsys)
    tid = json.loads(out2)["topic"]["topic_id"]
    rc3, out3 = _run(["publish", "--topic", tid, "--title", "f1", "--type", "FINDING",
                      "--content", "c", "--author", "a", "--commit"], capsys)
    assert rc3 == 0
    assert json.loads(out3)["entry"]["to_state"] == "PUBLISHED"


def test_cli_share_consume_feedback_reuse(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    entry = _entry(e)
    rc, out = _run(["share", "--entry", entry, "--from", "a", "--to", "b", "--commit"], capsys)
    assert rc == 0
    _run(["consume", "--entry", entry, "--agent", "b", "--reused", "--commit"], capsys)
    _run(["feedback", "--entry", entry, "--agent", "b", "--score", "5", "--commit"], capsys)
    rc2, out2 = _run(["reuse", "--entry", entry, "--commit"], capsys)
    assert rc2 == 0
    assert json.loads(out2)["reuse"]["reused"] is True


def test_cli_link(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg = _reg(e)
    t1 = e.register_topic(reg, "a", "", "", T[0], commit=True).topic_id
    t2 = e.register_topic(reg, "b", "", "", T[1], commit=True).topic_id
    rc, out = _run(["link", "--type", "TOPIC_RELATED", "--source", t1, "--target", t2,
                    "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["link"]["link_type"] == "TOPIC_RELATED"


def test_cli_snapshot_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _entry(_eng())
    rc, out = _run(["snapshot", "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["snapshot"]["entry_count"] == 1
    rc2, out2 = _run(["report", "--commit"], capsys)
    assert json.loads(out2)["report"]["is_binding"] is False


def test_cli_entries_topics(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _entry(_eng())
    rc, out = _run(["entries"], capsys)
    assert rc == 0
    assert len(json.loads(out)["entries"]) == 1
    rc2, out2 = _run(["topics"], capsys)
    assert len(json.loads(out2)["topics"]) == 1


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["verify"], capsys)
    assert rc == 0
    assert json.loads(out)["ok"] is True


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _entry(_eng())
    rc, out = _run(["replay"], capsys)
    assert rc == 0
    assert json.loads(out)["deterministic"] is True


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["summary"], capsys)
    assert rc == 0
    assert "entry_event_count" in json.loads(out)


# ══════════════ 통합 시나리오 (end-to-end workflow) ══════════════
def test_end_to_end_workflow(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("ki_insights.jsonl"), "w") as f:
        f.write(json.dumps({"insight_id": "ins1"}) + "\n")
    e = _eng()
    reg = e.register_registry("research_knowledge_base", "cross-agent sharing", T[0],
                              commit=True).registry_id
    root = e.register_topic(reg, "factor_research", "", "", T[0], commit=True).topic_id
    mom = e.register_topic(reg, "momentum", "", root, T[1], commit=True).topic_id
    src = e.register_source("knowledge_intelligence", "ins1", "grounding", T[1], commit=True,
                            verify_ref=True).source_id
    base = e.publish_knowledge(mom, "12m momentum decays", KT_FINDING,
                               "decays post-2000", "alpha_agent", src, "", T[2], commit=True).entry_id
    lesson = e.publish_knowledge(mom, "avoid lookahead in momentum", KT_LESSON_LEARNED,
                                 "point-in-time only", "reviewer_agent", "", base, T[3],
                                 commit=True).entry_id
    e.link_knowledge(LINK_ENTRY_TOPIC, base, mom, "belongs", T[4], commit=True)
    # share base to 3 agents, consume + reuse
    for a in ("strat_agent", "risk_agent", "sim_agent"):
        e.share_with_agent(base, "alpha_agent", a, "fyi", T[5], commit=True)
    e.record_consumption(base, "strat_agent", True, "reused in v3", T[6], commit=True)
    e.record_feedback(base, "strat_agent", 5, "very useful", T[7], commit=True)
    e.record_feedback(base, "risk_agent", 4, "solid", T[8], commit=True)
    reuse = e.calculate_reuse_score(base, T[9], commit=True)
    assert reuse["reused"] is True
    assert e.entry_state(base) == K_REUSED
    assert e.trace_lineage(lesson) == [base]
    snap = e.snapshot_knowledge("GLOBAL", T[10], commit=True)
    assert snap.entry_count == 2
    rep = e.generate_report("GLOBAL", T[11], commit=True)
    assert rep.entry_count == 2
    assert rep.transfer_count == 3
    assert rep.is_binding is False
    # upstream source untouched
    assert open(sp("ki_insights.jsonl")).read().count("ins1") == 1
    from jarvis.knowledge_sharing.verify import verify_chain
    v = verify_chain()
    assert v["ok"] is True
    assert v["lifecycle"]["ok"] and v["reference"]["ok"] and v["cycle"]["ok"] and \
        v["lineage"]["ok"] and v["artifact_lineage"]["ok"]
