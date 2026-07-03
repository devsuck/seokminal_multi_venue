"""배치 되먹임 순환 — LabEngine.reconcile_from_batch.

배치(Auto-Research) 완료 후 lab의 pending_bh 판정을 배치 결과로 확정.
event_study 재계산 없이 classify 재사용(단일 진실원).
"""
from __future__ import annotations

from research.lab import pipeline as pl


def _pending(hid: str) -> dict:
    return {"id": hid, "name": hid, "family": "event", "market": "KR",
            "status": "pending_bh", "verdict": "PENDING — 배치 대기", "data_mode": "real_event", "ts": "00:00:00"}


def _entry(fam_id: str, *, bh: bool, wf2: float = 1.0, redteam: str = "CLEARED") -> dict:
    return {"cid": f"ev_{fam_id}", "net": 5.0, "percentile": 99.0, "p": 0.001,
            "wf_first": 1.0, "wf_second": wf2, "redteam": redteam, "bh_survivor": bh}


def _fresh_engine(monkeypatch):
    # _seed(실 family 로드)를 우회 — 되먹임만 검증
    monkeypatch.setattr(pl.LabEngine, "_seed", lambda self: None)
    return pl.LabEngine()


def test_reconcile_pending_to_candidate(monkeypatch):
    eng = _fresh_engine(monkeypatch)
    eng._verdicts.appendleft(_pending("real_buyback"))
    eng.stats["pending"] = 1
    r = eng.reconcile_from_batch({"leaderboard": [_entry("buyback", bh=True)]})
    assert r["reconciled"] == 1
    v = eng.snapshot()["verdicts"][0]
    assert v["status"] == "candidate"
    assert v["reconciled"] is True
    assert eng.stats["pending"] == 0
    assert eng.stats["edges"] == 1


def test_reconcile_pending_to_reject_bh(monkeypatch):
    eng = _fresh_engine(monkeypatch)
    eng._verdicts.appendleft(_pending("real_spinoff"))
    eng.stats["pending"] = 1
    r = eng.reconcile_from_batch({"leaderboard": [_entry("spinoff", bh=False)]})
    assert r["reconciled"] == 1
    assert eng.snapshot()["verdicts"][0]["status"] == "reject_bh"
    assert eng.stats["pending"] == 0
    assert eng.stats["rejects"] == 1


def test_reconcile_wf_negative_to_watchlist(monkeypatch):
    eng = _fresh_engine(monkeypatch)
    eng._verdicts.appendleft(_pending("real_buyback"))
    eng.stats["pending"] = 1
    # bh 생존 + 레드팀 CLEARED지만 wf 후반 음수 → watchlist(강건성 게이트)
    r = eng.reconcile_from_batch({"leaderboard": [_entry("buyback", bh=True, wf2=-0.5)]})
    assert r["reconciled"] == 1
    assert eng.snapshot()["verdicts"][0]["status"] == "watchlist"
    assert eng.stats["edges"] == 1  # watchlist도 edge 버킷


def test_reconcile_skips_non_pending(monkeypatch):
    eng = _fresh_engine(monkeypatch)
    already = {"id": "real_buyback", "name": "b", "family": "event", "market": "KR",
               "status": "candidate", "verdict": "CANDIDATE", "data_mode": "real_event", "ts": "0"}
    eng._verdicts.appendleft(already)
    r = eng.reconcile_from_batch({"leaderboard": [_entry("buyback", bh=False)]})
    assert r["reconciled"] == 0
    assert eng.snapshot()["verdicts"][0]["status"] == "candidate"  # 안 건드림


def test_reconcile_family_absent_in_batch(monkeypatch):
    eng = _fresh_engine(monkeypatch)
    eng._verdicts.appendleft(_pending("real_unknown"))
    eng.stats["pending"] = 1
    r = eng.reconcile_from_batch({"leaderboard": [_entry("buyback", bh=True)]})
    assert r["reconciled"] == 0
    assert eng.stats["pending"] == 1  # 배치에 없으면 그대로 대기


def test_reconcile_idempotent(monkeypatch):
    eng = _fresh_engine(monkeypatch)
    eng._verdicts.appendleft(_pending("real_buyback"))
    eng.stats["pending"] = 1
    status = {"leaderboard": [_entry("buyback", bh=True)]}
    assert eng.reconcile_from_batch(status)["reconciled"] == 1
    assert eng.reconcile_from_batch(status)["reconciled"] == 0  # 두 번째는 이미 확정
    assert eng.stats["edges"] == 1
