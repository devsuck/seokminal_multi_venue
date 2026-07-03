"""service 되먹임 배선 — _autoresearch_batch가 배치 후 lab reconcile 트리거."""
from __future__ import annotations

import research.autoresearch.engine as eng
from research.lab import pipeline as pl
from research.lab.service import ResearchService


def test_autoresearch_batch_triggers_reconcile(monkeypatch):
    monkeypatch.setattr(eng, "run_batch", lambda: {"n_candidates": 2, "leaderboard": [{"cid": "ev_x"}]})
    seen = {}

    def fake_reconcile(status=None):
        seen["status"] = status
        return {"reconciled": 3}

    monkeypatch.setattr(pl.ENGINE, "reconcile_from_batch", fake_reconcile)

    svc = ResearchService()          # 신규 인스턴스 = throttle ts 0 → 첫 호출 통과
    svc._autoresearch_batch()

    assert seen["status"]["n_candidates"] == 2          # 배치 summary가 reconcile에 전달됨
    assert svc.autoresearch_reconciled == 3
    assert svc.last_autoresearch is not None
    assert svc.status()["autoresearch_reconciled"] == 3


def test_reconcile_failure_does_not_break_batch(monkeypatch):
    monkeypatch.setattr(eng, "run_batch", lambda: {"n_candidates": 1, "leaderboard": []})

    def boom(status=None):
        raise RuntimeError("reconcile 폭발")

    monkeypatch.setattr(pl.ENGINE, "reconcile_from_batch", boom)

    svc = ResearchService()
    svc._autoresearch_batch()        # 예외 삼켜야 함(배치 자체는 성공 기록)
    assert svc.autoresearch_candidates == 1
    assert svc.last_autoresearch is not None
