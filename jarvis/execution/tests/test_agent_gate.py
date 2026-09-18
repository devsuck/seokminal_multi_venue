"""에이전트 ↔ registry 전략 매핑 게이트 테스트.

핵심 계약: profile_name 조회는 agent["type"]만 씀(과거 profile.name/style/
profile_name은 죽은 필드였음) · 매핑 미등록이면 무조건 미검증 ·
등록돼도 registry 상태가 _VALIDATED_STATUSES 밖이면 미검증 ·
매핑 등록/해제는 사람 ADMIN만(arm.py와 동일 패턴, jsonl latest-wins).
"""
from __future__ import annotations

import os

import pytest

from jarvis.agents import BACKTEST_AGENT, HUMAN_ADMIN
from jarvis.execution import agent_gate as ag
from jarvis.permissions import PermissionDenied
from jarvis.registry import StrategyRegistry


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    import importlib
    for mod in ("jarvis.audit.log", "jarvis.registry.lifecycle", "jarvis.execution.agent_gate"):
        monkeypatch.setattr(importlib.import_module(mod), "state_path", sp)
    return tmp_path


def _register(sid="kr_dart_buyback_drift_v1"):
    StrategyRegistry().register(sid, name=sid, config={"x": 1})
    return sid


def test_unmapped_type_is_unvalidated():
    v = ag.validation_of({"type": "kr_daytrade"})
    assert v["validated"] is False
    assert v["strategy_id"] is None


def test_profile_name_key_is_type_not_dead_fields(monkeypatch):
    sid = _register()
    ag.register_validated_strategy("kr_daytrade", sid, HUMAN_ADMIN)
    monkeypatch.setattr(
        "jarvis.registry.StrategyRegistry.all_current",
        lambda self: [{"strategy_id": sid, "status": "paper_active"}],
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
    assert v["strategy_id"] == sid


def test_mapped_but_registry_status_not_validated(monkeypatch):
    sid = _register()
    ag.register_validated_strategy("kr_daytrade", sid, HUMAN_ADMIN)
    monkeypatch.setattr(
        "jarvis.registry.StrategyRegistry.all_current",
        lambda self: [{"strategy_id": sid, "status": "draft"}],
    )
    v = ag.validation_of({"type": "kr_daytrade"})
    assert v["validated"] is False
    assert "검증 상태 아님" in v["reason"]


def test_enforce_paper_forces_paper_when_unvalidated():
    paper, reason = ag.enforce_paper({"type": "kr_daytrade", "paper": False})
    assert paper is True
    assert reason is not None


def test_enforce_paper_allows_live_when_validated(monkeypatch):
    sid = _register()
    ag.register_validated_strategy("kr_daytrade", sid, HUMAN_ADMIN)
    monkeypatch.setattr(
        "jarvis.registry.StrategyRegistry.all_current",
        lambda self: [{"strategy_id": sid, "status": "paper_active"}],
    )
    paper, reason = ag.enforce_paper({"type": "kr_daytrade", "paper": False})
    assert paper is False
    assert reason is None


def test_already_paper_short_circuits_without_registry_lookup():
    paper, reason = ag.enforce_paper({"type": "kr_daytrade", "paper": True})
    assert paper is True and reason is None


def test_god_mode_bypasses_unvalidated_registry():
    # god_mode=1은 별도 3조건 실적 심사(god_mode.py)를 이미 통과한 것 —
    # registry 미등록이어도(매핑 비어있음) live 허용돼야 함.
    paper, reason = ag.enforce_paper({"type": "kr_daytrade", "paper": False, "god_mode": True})
    assert paper is False and reason is None


def test_register_validated_strategy_requires_human_admin():
    sid = _register()
    with pytest.raises(PermissionDenied):
        ag.register_validated_strategy("kr_daytrade", sid, BACKTEST_AGENT)
    assert ag._current_mapping() == {}


def test_unregister_strategy_requires_human():
    sid = _register()
    ag.register_validated_strategy("kr_daytrade", sid, HUMAN_ADMIN)
    with pytest.raises(PermissionDenied):
        ag.unregister_strategy("kr_daytrade", BACKTEST_AGENT)
    assert ag._current_mapping() == {"kr_daytrade": sid}


def test_register_validated_strategy_rejects_unregistered_strategy_id():
    r = ag.register_validated_strategy("kr_daytrade", "no_such_strategy", HUMAN_ADMIN)
    assert r["registered"] is False
    assert r["reason"] == "strategy_not_registered"
    assert ag._current_mapping() == {}


def test_unregister_strategy_removes_mapping():
    sid = _register()
    ag.register_validated_strategy("kr_daytrade", sid, HUMAN_ADMIN)
    assert ag._current_mapping() == {"kr_daytrade": sid}

    ag.unregister_strategy("kr_daytrade", HUMAN_ADMIN)

    assert ag._current_mapping() == {}


def test_current_mapping_latest_wins():
    sid1 = _register("strat_a")
    sid2 = _register("strat_b")
    ag.register_validated_strategy("kr_daytrade", sid1, HUMAN_ADMIN)
    ag.register_validated_strategy("kr_daytrade", sid2, HUMAN_ADMIN)

    assert ag._current_mapping() == {"kr_daytrade": sid2}
