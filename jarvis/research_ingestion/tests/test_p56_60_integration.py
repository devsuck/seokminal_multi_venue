"""P56-60 통합 — 최종 비전 흐름 검증. **모두 자문/사람 게이트, 실행 없음.**

Data → Memory → Opportunities → Multi-perspective → (Validation) → Knowledge Growth.
1) discovery → (사람 승인) → import → recall 이 찾는다.
2) event_intelligence → research_queue 후보 생성.
3) council 이 상충을 종합.
"""
from __future__ import annotations

import json

import pytest

from jarvis.research_assistant import ledger as al
from jarvis.research_assistant.council import ResearchCouncilEngine
from jarvis.research_assistant.engine import ResearchAssistantEngine
from jarvis.research_assistant.event_intelligence import MarketEventIntelligence
from jarvis.research_assistant.research_queue import K_EVENT, ResearchQueueEngine
from jarvis.research_ingestion import ledger as ring_ledger
from jarvis.research_ingestion.archive_discovery import discover
from jarvis.research_ingestion.history_importer import HistoricalResearchImporter

NOW = "2026-01-01T00:00:00Z"
_FULL = {"return": 0.14, "sharpe": 0.9, "max_drawdown": -0.18, "volatility": 0.13,
         "walk_forward": 0.8, "out_of_sample": 0.7, "cost_impact": 0.1,
         "parameter_stability": 0.8, "random_baseline": 0.2}


@pytest.fixture()
def state(tmp_path, monkeypatch):
    st = tmp_path / "_state"
    st.mkdir()
    sp = lambda name: str(st / name)  # noqa: E731
    from jarvis.experiment_tracking import ledger as el
    from jarvis.research_memory_intelligence import ledger as ml
    monkeypatch.setattr(ring_ledger, "state_path", sp)
    monkeypatch.setattr(el, "state_path", sp)
    monkeypatch.setattr(ml, "state_path", sp)
    monkeypatch.setattr(al, "state_path", sp)
    return tmp_path


# ── 1. discovery → 사람 승인 → import → recall (Test req #1, #2) ──
def test_discovery_to_approved_import_reaches_memory(state):
    root = state / "research"
    root.mkdir()
    (root / "tsmom.json").write_text(json.dumps(
        {"strategy": "TSMOM", "metrics": dict(_FULL)}), encoding="utf-8")

    man = discover(["research"], base=str(state))
    approved = [c for c in man.candidates if c.import_candidate and c.detected_strategy == "TSMOM"]
    assert approved, "발견이 TSMOM 후보를 제시"

    # 사람이 승인한 파일만 실제 임포트(발견 ≠ 임포트)
    imp = HistoricalResearchImporter()
    imp.import_file(approved[0].file, now=NOW, commit=True)

    r = ResearchAssistantEngine().recall("TSMOM")
    assert r.tried_before is True                    # 승인된 임포트가 메모리에 도달


# ── 2. event → queue (Test req #5, #7 연결) ──
def test_event_generates_queue_candidates(state):
    events = MarketEventIntelligence().generate_candidates("Taiwan earthquake")
    q = ResearchQueueEngine(ResearchAssistantEngine(reader=lambda n: [])).generate(
        events=events, limit=20)
    evs = [p for p in q.proposals if p.kind == K_EVENT]
    assert evs, "이벤트 파급 개체가 연구 후보가 된다"
    assert any("NVIDIA" in p.name for p in evs)
    assert q.requires_human_approval is True


# ── 3. council 종합(Test req #6) — 흐름 말단 ──
def test_council_synthesizes_perspectives(state):
    reader = lambda n: {  # noqa: E731
        "experiments": [{"name": "momentum study"}],
        "experiment_runs": [{"note": "momentum edge"}],
        "failures": [{"reason": "momentum overfit"}, {"reason": "momentum regime"}],
    }.get(n, [])
    memo = ResearchCouncilEngine(ResearchAssistantEngine(reader=reader)).deliberate("momentum")
    assert memo.requires_human_judgment is True
    assert memo.recommendation                       # 균형 권고 존재
