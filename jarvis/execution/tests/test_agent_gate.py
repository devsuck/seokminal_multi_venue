"""에이전트 ↔ registry 전략 매핑 게이트 테스트.

핵심 계약: profile_name 조회는 agent["type"]만 씀(과거 profile.name/style/
profile_name은 죽은 필드였음) · PROFILE_TO_STRATEGY 미등록이면 무조건 미검증 ·
등록돼도 registry 상태가 _VALIDATED_STATUSES 밖이면 미검증.
"""
from __future__ import annotations

from jarvis.execution import agent_gate as ag


def test_unmapped_type_is_unvalidated():
    v = ag.validation_of({"type": "kr_daytrade"})
    assert v["validated"] is False
    assert v["strategy_id"] is None


def test_profile_name_key_is_type_not_dead_fields(monkeypatch):
    monkeypatch.setitem(ag.PROFILE_TO_STRATEGY, "kr_daytrade", "kr_dart_buyback_drift_v1")
    monkeypatch.setattr(
        "jarvis.registry.StrategyRegistry.all_current",
        lambda self: [{"strategy_id": "kr_dart_buyback_drift_v1", "status": "paper_active"}],
    )
    # profile.name/style/profile_name 세팅해도 무시되고 type만 봐야 함(회귀 방지).
    agent = {
        "type": "kr_daytrade",
        "profile": {"label": "데이트레이딩 (한국주식)", "name": "wrong"},
        "style": "also_wrong",
        "profile_name": "still_wrong",
    }
    v = ag.validation_of(agent)
    assert v["validated"] is True
    assert v["strategy_id"] == "kr_dart_buyback_drift_v1"


def test_mapped_but_registry_status_not_validated(monkeypatch):
    monkeypatch.setitem(ag.PROFILE_TO_STRATEGY, "kr_daytrade", "kr_dart_buyback_drift_v1")
    monkeypatch.setattr(
        "jarvis.registry.StrategyRegistry.all_current",
        lambda self: [{"strategy_id": "kr_dart_buyback_drift_v1", "status": "draft"}],
    )
    v = ag.validation_of({"type": "kr_daytrade"})
    assert v["validated"] is False
    assert "검증 상태 아님" in v["reason"]


def test_enforce_paper_forces_paper_when_unvalidated():
    paper, reason = ag.enforce_paper({"type": "kr_daytrade", "paper": False})
    assert paper is True
    assert reason is not None


def test_enforce_paper_allows_live_when_validated(monkeypatch):
    monkeypatch.setitem(ag.PROFILE_TO_STRATEGY, "kr_daytrade", "kr_dart_buyback_drift_v1")
    monkeypatch.setattr(
        "jarvis.registry.StrategyRegistry.all_current",
        lambda self: [{"strategy_id": "kr_dart_buyback_drift_v1", "status": "paper_active"}],
    )
    paper, reason = ag.enforce_paper({"type": "kr_daytrade", "paper": False})
    assert paper is False
    assert reason is None


def test_already_paper_short_circuits_without_registry_lookup():
    paper, reason = ag.enforce_paper({"type": "kr_daytrade", "paper": True})
    assert paper is True and reason is None
