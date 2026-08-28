"""시드 경로 승격 게이트 테스트.

배경(2026-08-27): `boot()` → `seed_from_experiment_registry()` → `auto_deploy_all()`은
실험원장의 `status` 문자열만 보고 `paper_candidate`를 거쳐 `paper_active`까지 자동으로
올렸다. 정문(`run_batch`)의 critic→BH-FDR→레드팀 3중 게이트를 통째로 우회하는 경로다.

실제 피해: `scan_turn_to_profit`(net −0.9%, walk-forward 양쪽 음수, percentile 0.0,
p=1.0)이 "candidate" 도장을 달고 paper_active로 운영 중이었다. 이 행들은
`classify()`가 "유일한 진실원"이 되기 전에 쓰여서, 그 함수로는 나올 수 없는 조합이다.

이제 시드는 저장된 문자열 대신 행의 지표로 재판정한다.
"""
from __future__ import annotations

import pytest

import jarvis.registry.lifecycle as rl
from jarvis.registry import Status, StrategyRegistry
from tests.jarvis_state_isolation import isolate_jarvis_state

# autoresearch가 정상적으로 뽑은 후보 — 재판정해도 candidate.
QUALIFIED = {
    "hypothesis_id": "auto_fac_good", "status": "candidate",
    "net": 0.042305, "percentile": 100.0, "p": 0.0033,
    "wf_first": 0.043223, "wf_second": 0.041387,
    "redteam": "CLEARED", "bh_survivor": True,
}
# classify() 이전에 쓰인 행 — 문자열만 candidate, 지표는 전부 실패.
LEGACY_JUNK = {
    "hypothesis_id": "scan_junk", "status": "candidate", "verdict": "스캐너 CLEARED",
    "net": -0.008995, "percentile": 0.0, "p": 1.0,
    "wf_first": -0.014426, "wf_second": -0.003565,
    "redteam": "CLEARED", "bh_survivor": True,
}
# 다른 러너 출력 — 지표 스키마가 아예 달라 판정 불가.
FOREIGN_SCHEMA = {
    "hypothesis_id": "polymarket_thing", "status": "paper_candidate_forward_test_required",
    "n_anchors": 9756, "n_survivors": 18, "wf_all_pass": False,
}


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    return isolate_jarvis_state(monkeypatch, tmp_path)


def _seed(monkeypatch, rows):
    import research.agents.experiment_registry as er
    monkeypatch.setattr(er, "load_all", lambda: rows)
    reg = StrategyRegistry()
    rl.seed_from_experiment_registry(reg)
    return reg


# ── _seed_metrics_pass 단위 ──────────────────────────────────────────────────

def test_metrics_pass_for_genuine_candidate():
    assert rl._seed_metrics_pass(QUALIFIED) is True


def test_metrics_fail_for_legacy_junk():
    """net 음수 + walk-forward 양쪽 음수는 classify()로 절대 candidate가 아니다."""
    assert rl._seed_metrics_pass(LEGACY_JUNK) is False


def test_metrics_fail_when_schema_unreadable():
    """판정 못 하면 통과시키지 않는다 — 검증 못 한 걸 자동 배선하지 않는다."""
    assert rl._seed_metrics_pass(FOREIGN_SCHEMA) is False


def test_metrics_fail_without_bh_survivor():
    """BH-FDR 생존 미확정이면 pending — candidate 도장 불가(통계적 정직성)."""
    assert rl._seed_metrics_pass({**QUALIFIED, "bh_survivor": None}) is False


def test_stored_status_string_is_ignored():
    """지표가 통과하면 status 문자열이 뭐든 통과. 문자열을 안 본다는 뜻."""
    assert rl._seed_metrics_pass({**QUALIFIED, "status": "whatever"}) is True


# ── 시드 전이 결과 ───────────────────────────────────────────────────────────

def test_genuine_candidate_reaches_paper_candidate(monkeypatch):
    reg = _seed(monkeypatch, [QUALIFIED])
    assert reg.state("auto_fac_good")["status"] == Status.PAPER_CANDIDATE.value


def test_legacy_junk_stops_at_watchlist(monkeypatch):
    """이게 회귀의 핵심 — 예전엔 paper_candidate까지 갔고 forward 자동배선으로 이어졌다."""
    reg = _seed(monkeypatch, [LEGACY_JUNK])
    st = reg.state("scan_junk")
    assert st["status"] == Status.WATCHLIST.value
    assert "재판정 미통과" in st["last_reason"]


def test_foreign_schema_stops_at_watchlist(monkeypatch):
    reg = _seed(monkeypatch, [FOREIGN_SCHEMA])
    assert reg.state("polymarket_thing")["status"] == Status.WATCHLIST.value


def test_rejected_rows_still_rejected(monkeypatch):
    reg = _seed(monkeypatch, [{"hypothesis_id": "bad_v1", "status": "rejected",
                               "verdict": "REJECT — net 음수"}])
    assert reg.state("bad_v1")["status"] == Status.REJECTED.value


def test_blocked_rows_still_blocked(monkeypatch):
    reg = _seed(monkeypatch, [{"hypothesis_id": "nodata_v1", "status": "blocked_by_data"}])
    assert reg.state("nodata_v1")["status"] == Status.BLOCKED_BY_DATA.value


# ── 근거 기록 ────────────────────────────────────────────────────────────────

def test_evidence_uses_real_schema_keys(monkeypatch):
    """예전엔 `random_pct`를 읽어서 근거가 전부 null로 남았다 — 실제 키는 `percentile`."""
    reg = _seed(monkeypatch, [QUALIFIED])
    events = [e for e in reg._events()
              if e.get("strategy_id") == "auto_fac_good" and e.get("to") == "paper_candidate"]
    ev = events[-1]["evidence"]
    assert ev["percentile"] == pytest.approx(100.0)
    assert ev["net"] == pytest.approx(0.042305)
    assert ev["bh_survivor"] is True


def test_watchlist_holdback_also_records_evidence(monkeypatch):
    """왜 보류됐는지 원장만 보고 알 수 있어야 한다."""
    reg = _seed(monkeypatch, [LEGACY_JUNK])
    events = [e for e in reg._events()
              if e.get("strategy_id") == "scan_junk" and e.get("to") == "watchlist"]
    ev = events[-1]["evidence"]
    assert ev["net"] == pytest.approx(-0.008995)
    assert ev["source_status"] == "candidate"


# ── 자동 배선까지 안 가는지 ──────────────────────────────────────────────────

def test_holdback_is_not_auto_deployed(monkeypatch):
    """watchlist는 _DEPLOYABLE이 아니므로 auto_deploy_all()이 건드리지 않는다."""
    from jarvis.paper.deploy import auto_deploy_all
    _seed(monkeypatch, [LEGACY_JUNK, FOREIGN_SCHEMA])
    out = auto_deploy_all()
    assert out["deployed"] == 0


def test_genuine_candidate_is_auto_deployed(monkeypatch):
    """정상 후보의 기존 흐름은 그대로 — 게이트가 길을 막은 게 아니다."""
    from jarvis.paper.deploy import auto_deploy_all
    _seed(monkeypatch, [QUALIFIED])
    out = auto_deploy_all()
    assert out["deployed"] == 1
