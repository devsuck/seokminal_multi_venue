"""단일 판정 함수 classify — lab·autoresearch 공유 진실원."""
from __future__ import annotations

from research.scanner.verdict import classify, DISPLAY


def _kw(**kw):
    base = dict(net=100.0, percentile=99.0, p=0.01, wf_first=1.0, wf_second=1.0,
                redteam_verdict="CLEARED", bh_survivor=True)
    base.update(kw)
    return base


def test_candidate_requires_bh_redteam_and_robust_stats():
    status, text = classify(**_kw())
    assert status == "candidate"
    assert "CANDIDATE" in text or "candidate" in text.lower()


def test_bh_survivor_but_redteam_fail_is_reject_redteam():
    status, _ = classify(**_kw(redteam_verdict="REJECTED"))
    assert status == "reject_redteam"


def test_not_bh_survivor_is_reject_bh_even_if_stats_strong():
    status, _ = classify(**_kw(bh_survivor=False))
    assert status == "reject_bh"


def test_bh_survivor_but_negative_wf_is_watchlist():
    # BH 생존 + 레드팀 통과지만 walk-forward 후반 음수 → robust 아님 → watchlist
    status, _ = classify(**_kw(wf_second=-0.5, percentile=85.0))
    assert status == "watchlist"


def test_live_unknown_bh_with_strong_stats_is_pending():
    # bh_survivor=None(라이브, 배치 미확정) → candidate 도장 보류, pending_bh
    status, text = classify(**_kw(bh_survivor=None))
    assert status == "pending_bh"
    assert "대기" in text or "PENDING" in text.upper()


def test_live_unknown_bh_redteam_fail_is_reject_redteam():
    status, _ = classify(**_kw(bh_survivor=None, redteam_verdict="REJECTED"))
    assert status == "reject_redteam"


def test_live_unknown_bh_weak_stats_is_reject_stats():
    status, _ = classify(**_kw(bh_survivor=None, net=-10.0, percentile=40.0))
    assert status == "reject_stats"


def test_display_maps_canonical_to_uppercase():
    assert DISPLAY["candidate"] == "CANDIDATE"
    assert DISPLAY["reject_bh"] == "REJECT_BH"
    assert DISPLAY["reject_redteam"] == "REJECT_REDTEAM"
