import pandas as pd
import pytest

from research.hypotheses.mlb_specialist_consensus import consensus_signals, build_labels

SPECIALISTS = ["s1", "s2", "s3", "s4", "s5"]


def _pos(w, cid, side):
    return {"proxy_wallet": w, "condition_id": cid, "side": side}


def test_majority_signal():
    positions = [_pos("s1", "m1", "YES"), _pos("s2", "m1", "YES"), _pos("s3", "m1", "NO")]
    sig = consensus_signals(positions, SPECIALISTS, min_present=3, threshold="majority")
    assert len(sig) == 1 and sig[0]["condition_id"] == "m1" and sig[0]["side"] == "YES"


def test_unanimous_requires_all_same():
    # 3명 참여, 2 YES 1 NO — unanimous면 신호 없음
    positions = [_pos("s1", "m1", "YES"), _pos("s2", "m1", "YES"), _pos("s3", "m1", "NO")]
    assert consensus_signals(positions, SPECIALISTS, min_present=3, threshold="unanimous") == []


def test_unanimous_signal_when_all_agree():
    positions = [_pos("s1", "m1", "YES"), _pos("s2", "m1", "YES"), _pos("s3", "m1", "YES")]
    sig = consensus_signals(positions, SPECIALISTS, min_present=3, threshold="unanimous")
    assert len(sig) == 1 and sig[0]["side"] == "YES"


def test_min_present_not_met():
    positions = [_pos("s1", "m1", "YES"), _pos("s2", "m1", "YES")]  # 2명 < 3
    assert consensus_signals(positions, SPECIALISTS, min_present=3, threshold="majority") == []


def test_non_specialists_ignored():
    positions = [_pos("s1", "m1", "YES"), _pos("outsider", "m1", "YES"), _pos("s2", "m1", "YES")]
    # 스페셜리스트는 s1,s2 둘뿐 → present=2 < 3
    assert consensus_signals(positions, SPECIALISTS, min_present=3, threshold="majority") == []


def test_majority_tie_no_signal():
    positions = [_pos("s1", "m1", "YES"), _pos("s2", "m1", "YES"), _pos("s3", "m1", "NO"), _pos("s4", "m1", "NO")]
    # 2:2 동점 → 과반 아님
    assert consensus_signals(positions, SPECIALISTS, min_present=3, threshold="majority") == []


def test_build_labels_win_and_loss():
    signals = [{"condition_id": "m1", "side": "YES"}, {"condition_id": "m2", "side": "YES"}]
    res = {"m1": {"winning_side": "YES"}, "m2": {"winning_side": "NO"}}
    entry = {"m1": {"YES": 0.5}, "m2": {"YES": 0.4}}
    labels = build_labels(signals, res, entry)
    r1 = labels[labels["condition_id"] == "m1"].iloc[0]
    assert r1["exit_price"] == 1.0 and r1["forward_return"] == pytest.approx((1.0 - 0.5) / 0.5)
    r2 = labels[labels["condition_id"] == "m2"].iloc[0]
    assert r2["exit_price"] == 0.0 and r2["forward_return"] == pytest.approx((0.0 - 0.4) / 0.4)


def test_build_labels_skips_unresolved_or_no_price():
    signals = [{"condition_id": "m1", "side": "YES"}, {"condition_id": "unres", "side": "YES"}]
    res = {"m1": {"winning_side": "YES"}}
    entry = {"m1": {"YES": 0.5}}
    labels = build_labels(signals, res, entry)
    assert list(labels["condition_id"]) == ["m1"]
