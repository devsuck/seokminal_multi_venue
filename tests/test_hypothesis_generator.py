"""HypothesisGenerator 목표(topic) 관련도 재정렬 + 합성 테스트.

_topic_tokens/_relevance(순수 함수) + _from_topic(합성) + generate()의
topic 기반 재정렬·합성-삽입 분기를 검증한다. ResearchQueueEngine/
MarketEventIntelligence는 monkeypatch로 대체해 결정적으로 고정한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from jarvis.research_workflow import hypothesis_generator as hg


# ── _topic_tokens ──

def test_topic_tokens_splits_english_and_korean():
    assert hg._topic_tokens("Copper Manipulation 구리 조작") == {
        "copper", "manipulation", "구리", "조작",
    }


def test_topic_tokens_filters_single_char_tokens():
    assert hg._topic_tokens("a i 구 구리") == {"구리"}


def test_topic_tokens_none_or_blank_is_empty_set():
    assert hg._topic_tokens(None) == set()
    assert hg._topic_tokens("   ") == set()


def test_topic_tokens_lowercases():
    assert hg._topic_tokens("COPPER") == {"copper"}


# ── _relevance ──

@dataclass
class _FakeHyp:
    statement: str
    rationale: str = ""


def test_relevance_zero_when_no_tokens():
    assert hg._relevance(_FakeHyp("copper edge"), set()) == 0


def test_relevance_counts_matches_in_statement_and_rationale():
    h = _FakeHyp(statement="Copper leads Aluminum returns", rationale="구리 조작 의심 패턴")
    assert hg._relevance(h, {"copper", "구리", "gold"}) == 2


def test_relevance_is_case_insensitive():
    h = _FakeHyp(statement="COPPER edge", rationale="")
    assert hg._relevance(h, {"copper"}) == 1


# ── HypothesisGenerator._from_topic ──

def test_from_topic_uses_topic_template_and_low_confidence():
    g = hg.HypothesisGenerator(assistant=object())
    h = g._from_topic("  copper manipulation  ")
    assert h.statement == "copper manipulation produces a persistent, cost-robust edge"
    assert "copper manipulation" in h.rationale
    assert h.source == "topic"
    assert h.expected_edge == "LOW"
    assert h.confidence == "LOW"
    assert h.assumptions == hg._TEMPLATES["TOPIC"]["assumptions"]
    assert h.invalidation_conditions == hg._TEMPLATES["TOPIC"]["invalidation"]


# ── generate(): topic 재정렬/합성 ──

@dataclass
class _FakeProposal:
    name: str
    reason: str
    kind: str
    confidence: str = "MEDIUM"
    expected_value: str = "MEDIUM"


@dataclass
class _FakeQueue:
    proposals: list = field(default_factory=list)


class _FakeQueueEngine:
    def __init__(self, assistant=None, reader=None):
        pass

    def generate(self, regime=None, events=None, limit=8):
        return _FakeQueue(proposals=[
            _FakeProposal(
                name="Copper + Aluminum Combination",
                reason="copper와 aluminum 조합 미탐색",
                kind="COMBINATION"),
            _FakeProposal(
                name="Late Fill Failure-robust variant",
                reason="late fill 실패 강건화",
                kind="FAILURE_FIX"),
        ])


class _FakeEventIntel:
    def relationship_graph(self):
        return {"edges": []}


@pytest.fixture(autouse=True)
def _stub_collaborators(monkeypatch):
    monkeypatch.setattr(
        "jarvis.research_assistant.research_queue.ResearchQueueEngine", _FakeQueueEngine)
    monkeypatch.setattr(
        "jarvis.research_assistant.event_intelligence.MarketEventIntelligence", _FakeEventIntel)


def _gen():
    return hg.HypothesisGenerator(assistant=object())


def test_generate_without_topic_keeps_queue_order():
    hyps = _gen().generate(topic=None, limit=8)
    assert [h.source for h in hyps] == ["queue:COMBINATION", "queue:FAILURE_FIX"]


def test_generate_with_topic_overlap_reorders_without_synthesis():
    # topic 토큰 "aluminum" 은 두번째 후보 rationale/statement엔 없고 첫번째에만 있음
    hyps = _gen().generate(topic="aluminum", limit=8)
    assert hyps[0].source == "queue:COMBINATION"
    assert not any(h.source == "topic" for h in hyps)


def test_generate_with_topic_no_overlap_synthesizes_topic_hypothesis_first():
    hyps = _gen().generate(topic="uranium enrichment", limit=8)
    assert hyps[0].source == "topic"
    assert hyps[0].statement == "uranium enrichment produces a persistent, cost-robust edge"


def test_generate_with_blank_topic_behaves_like_no_topic():
    hyps = _gen().generate(topic="   ", limit=8)
    assert not any(h.source == "topic" for h in hyps)
    assert hyps[0].source == "queue:COMBINATION"
