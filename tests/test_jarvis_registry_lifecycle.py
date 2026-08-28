"""Test suite for jarvis/registry/lifecycle.py — seed_from_experiment_registry idempotency & incremental."""
import os

import pytest
from unittest.mock import patch
from jarvis.registry.lifecycle import StrategyRegistry, Status, seed_from_experiment_registry


@pytest.fixture(autouse=True)
def _isolate_audit_log(tmp_path, monkeypatch):
    """transition() 이 jarvis.audit.log.record() 를 호출 — 운영 audit.jsonl 오염 방지(tests/test_jarvis_deploy.py 패턴)."""
    import jarvis.audit.log as al

    def sp(name):
        return os.path.join(tmp_path, name)

    monkeypatch.setattr(al, "state_path", sp)


@pytest.fixture
def registry(tmp_path):
    """Create a StrategyRegistry in a temp directory."""
    reg = StrategyRegistry(path=str(tmp_path / "registry.jsonl"))
    return reg


@pytest.fixture
def mock_experiment_data_v1():
    """First version of experiment data (2 entries)."""
    return [
        {
            "hypothesis_id": "hyp_001",
            "verdict": "promising signal, low drawdown",
            "status": "paper_candidate",
            "data_quality": "A",
            "random_pct": 0.15,
            "p": 0.0033,
        },
        {
            "hypothesis_id": "hyp_002",
            "verdict": "rejected in sanity check",
            "status": "rejected",
            "data_quality": "B",
        },
    ]


@pytest.fixture
def mock_experiment_data_v2(mock_experiment_data_v1):
    """Extended version with new entries (adds hyp_003 and hyp_004)."""
    return mock_experiment_data_v1 + [
        {
            "hypothesis_id": "hyp_003",
            "verdict": "passed audit, ready for paper",
            "status": "candidate",
            "data_quality": "A",
        },
        {
            "hypothesis_id": "hyp_004",
            "verdict": "blocked by data issues",
            "status": "blocked_by_data",
            "data_quality": "C",
        },
    ]


def test_seed_idempotent_no_change_on_second_call(registry, mock_experiment_data_v1):
    """Test idempotency: calling seed twice with same data adds nothing on second call."""
    with patch("research.agents.experiment_registry.load_all", return_value=mock_experiment_data_v1):
        # First call should add 2 entries
        added1 = seed_from_experiment_registry(registry)
        assert added1 == 2
        assert len(registry.all_current()) == 2

        # Second call with same data should add 0 (already registered)
        added2 = seed_from_experiment_registry(registry)
        assert added2 == 0
        assert len(registry.all_current()) == 2  # No change


def test_seed_incremental_adds_only_new_entries(registry, mock_experiment_data_v1, mock_experiment_data_v2):
    """Test incremental: new hypothesis_ids in experiment_registry are added, old ones skipped."""
    # First call: seed with v1 data (2 entries)
    with patch("research.agents.experiment_registry.load_all", return_value=mock_experiment_data_v1):
        added1 = seed_from_experiment_registry(registry)
        assert added1 == 2
        current1 = registry.all_current()
        assert len(current1) == 2
        ids1 = {s["strategy_id"] for s in current1}
        assert ids1 == {"hyp_001", "hyp_002"}

    # Second call: seed with v2 data (now 4 entries, 2 new)
    with patch("research.agents.experiment_registry.load_all", return_value=mock_experiment_data_v2):
        added2 = seed_from_experiment_registry(registry)
        assert added2 == 2  # Only the 2 new ones
        current2 = registry.all_current()
        assert len(current2) == 4
        ids2 = {s["strategy_id"] for s in current2}
        assert ids2 == {"hyp_001", "hyp_002", "hyp_003", "hyp_004"}


def test_seed_lifecycle_transitions_paper_candidate(registry):
    """Test that paper_candidate status gets correct lifecycle transitions."""
    data = [
        {
            "hypothesis_id": "hyp_paper",
            "verdict": "strong signal",
            "status": "paper_candidate",
            "data_quality": "A",
            "random_pct": 0.1,
            "p": 0.001,
        }
    ]
    with patch("research.agents.experiment_registry.load_all", return_value=data):
        added = seed_from_experiment_registry(registry)
        assert added == 1

    state = registry.state("hyp_paper")
    assert state is not None
    # 지표가 없는 행은 재판정 불가 → watchlist 보류(2026-08-27 시드 게이트).
    # paper_candidate는 forward 자동배선으로 바로 이어지므로, 검증 못 한 건 안 올린다.
    assert state["status"] == Status.WATCHLIST.value
    assert "재판정 미통과" in state["last_reason"]


def test_seed_lifecycle_transitions_rejected(registry):
    """Test that rejected status gets correct lifecycle transitions."""
    data = [
        {
            "hypothesis_id": "hyp_rejected",
            "verdict": "failed data quality check",
            "status": "rejected",
            "data_quality": "C",
        }
    ]
    with patch("research.agents.experiment_registry.load_all", return_value=data):
        added = seed_from_experiment_registry(registry)
        assert added == 1

    state = registry.state("hyp_rejected")
    assert state is not None
    # Rejected should end up in REJECTED status
    assert state["status"] == Status.REJECTED.value


def test_seed_lifecycle_transitions_blocked(registry):
    """Test that blocked status gets correct lifecycle transitions."""
    data = [
        {
            "hypothesis_id": "hyp_blocked",
            "verdict": "data issue",
            "status": "blocked_by_data",
            "data_quality": "C",
        }
    ]
    with patch("research.agents.experiment_registry.load_all", return_value=data):
        added = seed_from_experiment_registry(registry)
        assert added == 1

    state = registry.state("hyp_blocked")
    assert state is not None
    # Blocked should end up in BLOCKED_BY_DATA status
    assert state["status"] == Status.BLOCKED_BY_DATA.value


def test_seed_lifecycle_transitions_candidate(registry):
    """Test that candidate status gets correct lifecycle transitions."""
    data = [
        {
            "hypothesis_id": "hyp_candidate",
            "verdict": "passed audit, paper testing",
            "status": "candidate",
            "data_quality": "A",
            "p": 0.05,
        }
    ]
    with patch("research.agents.experiment_registry.load_all", return_value=data):
        added = seed_from_experiment_registry(registry)
        assert added == 1

    state = registry.state("hyp_candidate")
    assert state is not None
    # p만 있고 net·walk-forward·redteam·bh_survivor가 없으면 판정 불가 → 보류.
    assert state["status"] == Status.WATCHLIST.value


def test_seed_promotes_candidate_with_full_metrics(registry):
    """지표가 전부 갖춰지고 재판정을 통과하면 예전처럼 paper_candidate까지 간다.

    게이트가 길을 막은 게 아니라, 근거 없는 승격만 막는다는 걸 못박는다.
    """
    data = [
        {
            "hypothesis_id": "hyp_qualified",
            "verdict": "auto-research CANDIDATE",
            "status": "candidate",
            "data_quality": "KRX PIT survivorship-free",
            "net": 0.042, "percentile": 100.0, "p": 0.0033,
            "wf_first": 0.043, "wf_second": 0.041,
            "redteam": "CLEARED", "bh_survivor": True,
        }
    ]
    with patch("research.agents.experiment_registry.load_all", return_value=data):
        assert seed_from_experiment_registry(registry) == 1

    state = registry.state("hyp_qualified")
    assert state["status"] == Status.PAPER_CANDIDATE.value


def test_seed_empty_experiment_registry(registry):
    """Test seeding with empty experiment data."""
    with patch("research.agents.experiment_registry.load_all", return_value=[]):
        added = seed_from_experiment_registry(registry)
        assert added == 0
        assert len(registry.all_current()) == 0


def test_seed_handles_load_all_exception(registry):
    """Test that seed gracefully handles exception when load_all fails."""
    with patch("research.agents.experiment_registry.load_all", side_effect=Exception("import failed")):
        added = seed_from_experiment_registry(registry)
        assert added == 0
        assert len(registry.all_current()) == 0


def test_seed_skips_entries_without_hypothesis_id(registry):
    """Test that entries without hypothesis_id are skipped."""
    data = [
        {
            "hypothesis_id": "hyp_valid",
            "verdict": "good",
            "status": "candidate",
            "data_quality": "A",
        },
        {
            # No hypothesis_id
            "verdict": "orphan",
            "status": "candidate",
            "data_quality": "B",
        },
    ]
    with patch("research.agents.experiment_registry.load_all", return_value=data):
        added = seed_from_experiment_registry(registry)
        # Only 1 should be added (the one with hypothesis_id)
        assert added == 1
        assert len(registry.all_current()) == 1
        assert registry.all_current()[0]["strategy_id"] == "hyp_valid"
