"""P15 integrity 테스트 — 해시체인·변조·중복·타임스탬프·계보·replay·아티팩트·보안."""
from __future__ import annotations

import ast
import os

import pytest

from jarvis.integrity import artifact as ART
from jarvis.integrity import ledger as L
from jarvis.integrity.ledger import (
    content_hash,
    detect_broken_lineage,
    detect_duplicate_ids,
    detect_invalid_timestamps,
    detect_orphan_artifacts,
    detect_tamper,
    replay_consistency,
    verify_hash_chain,
    verify_ledger,
)

GENESIS = "GENESIS"


def _seal(core, prev):
    rec = dict(core)
    rec["previous_hash"] = prev
    rec["record_hash"] = content_hash(rec)
    return rec


def _chain(n, ts=True):
    recs = []
    prev = GENESIS
    for i in range(n):
        core = {"id": f"R{i}", "seq": i}
        if ts:
            core["at"] = f"2026-07-24T00:{i:02d}:00Z"
        rec = _seal(core, prev)
        recs.append(rec)
        prev = rec["record_hash"]
    return recs


# ═══════════════ verify_hash_chain ═══════════════
def test_chain_intact():
    assert verify_hash_chain(_chain(5))["ok"] is True


def test_chain_empty():
    assert verify_hash_chain([])["ok"] is True


def test_chain_broken_link():
    recs = _chain(4)
    recs[2]["previous_hash"] = "sha256:bad"
    res = verify_hash_chain(recs)
    assert res["ok"] is False
    assert res["broken_at"] == 2


def test_chain_missing_hash():
    recs = _chain(3)
    del recs[1]["record_hash"]
    assert verify_hash_chain(recs)["reason"] == "missing_record_hash"


def test_chain_tampered():
    recs = _chain(3)
    recs[1]["seq"] = 999
    assert verify_hash_chain(recs)["reason"] == "record_hash_mismatch"


# ═══════════════ detect_tamper ═══════════════
def test_tamper_none():
    assert detect_tamper(_chain(5)) == []


def test_tamper_detected():
    recs = _chain(4)
    recs[2]["seq"] = 111
    assert detect_tamper(recs) == [2]


def test_tamper_multiple():
    recs = _chain(5)
    recs[1]["seq"] = 1000
    recs[3]["seq"] = 2000
    assert detect_tamper(recs) == [1, 3]


# ═══════════════ duplicate ids ═══════════════
def test_dup_none():
    assert detect_duplicate_ids(_chain(3), "id") == []


def test_dup_detected():
    recs = _chain(3)
    recs.append({"id": "R0"})
    assert detect_duplicate_ids(recs, "id") == ["R0"]


# ═══════════════ timestamps ═══════════════
def test_ts_valid():
    assert detect_invalid_timestamps(_chain(3), "at") == []


def test_ts_invalid():
    recs = _chain(3)
    recs[1]["at"] = "not-a-date"
    assert detect_invalid_timestamps(recs, "at") == [1]


def test_ts_missing():
    recs = _chain(2, ts=False)
    assert detect_invalid_timestamps(recs, "at") == [0, 1]


@pytest.mark.parametrize("ts,valid", [
    ("2026-07-24T00:00:00Z", True), ("2026-07-24T00:00:00", True),
    ("2026-07-24T00:00:00.123Z", True), ("2026-07-24T00:00:00+09:00", True),
    ("2026-07-24", False), ("garbage", False), ("", False),
])
def test_ts_formats(ts, valid):
    recs = [_seal({"id": "R0", "at": ts}, GENESIS)]
    assert (detect_invalid_timestamps(recs, "at") == []) == valid


# ═══════════════ replay ═══════════════
def test_replay_deterministic():
    assert replay_consistency(_chain(5))["deterministic"] is True


def test_replay_empty():
    assert replay_consistency([])["deterministic"] is True


# ═══════════════ lineage ═══════════════
def test_orphan_none():
    recs = [{"id": "A", "parent": ""}, {"id": "B", "parent": "A"}]
    assert detect_orphan_artifacts(recs, "id", "parent") == []


def test_orphan_detected():
    recs = [{"id": "B", "parent": "GHOST"}]
    assert detect_orphan_artifacts(recs, "id", "parent") == ["B"]


def test_broken_lineage_clean():
    recs = [{"id": "A", "parent": ""}, {"id": "B", "parent": "A"}]
    assert detect_broken_lineage(recs, "id", "parent")["ok"] is True


def test_broken_lineage_orphan():
    recs = [{"id": "B", "parent": "X"}]
    assert detect_broken_lineage(recs, "id", "parent")["ok"] is False


def test_broken_lineage_cycle():
    recs = [{"id": "A", "parent": "B"}, {"id": "B", "parent": "A"}]
    r = detect_broken_lineage(recs, "id", "parent")
    assert r["has_cycle"] is True


# ═══════════════ verify_ledger ═══════════════
def test_verify_ledger_ok():
    res = verify_ledger(_chain(5), id_field="id", ts_field="at")
    assert res["ok"] is True


def test_verify_ledger_detects_tamper():
    recs = _chain(4)
    recs[2]["seq"] = 9999
    assert verify_ledger(recs, id_field="id")["ok"] is False


def test_verify_ledger_detects_dup():
    recs = _chain(3)
    recs.append(_seal({"id": "R0", "seq": 99}, recs[-1]["record_hash"]))
    assert verify_ledger(recs, id_field="id")["ok"] is False


def test_verify_ledger_deterministic():
    recs = _chain(4)
    assert verify_ledger(recs, id_field="id", ts_field="at") == verify_ledger(
        recs, id_field="id", ts_field="at")


def test_verify_ledger_with_lineage():
    recs = [_seal({"id": "A", "parent": ""}, GENESIS)]
    recs.append(_seal({"id": "B", "parent": "A"}, recs[0]["record_hash"]))
    res = verify_ledger(recs, id_field="id", parent_field="parent")
    assert res["lineage"]["ok"] is True


# ═══════════════ content_hash ═══════════════
def test_content_hash_excludes_meta():
    a = content_hash({"x": 1, "previous_hash": "p", "record_hash": "r"})
    b = content_hash({"x": 1, "previous_hash": "Q", "record_hash": "Z"})
    assert a == b


# ═══════════════ artifact validation ═══════════════
def test_validate_report_ok():
    assert ART.validate_artifact({"is_binding": False}, "report")["ok"] is True


def test_validate_report_binding_fails():
    assert ART.validate_artifact({"is_binding": True}, "report")["ok"] is False


def test_validate_report_missing_field():
    assert ART.validate_artifact({}, "report")["ok"] is False


def test_validate_snapshot():
    assert ART.validate_artifact({"is_binding": False}, "snapshot")["ok"] is True


def test_verify_benchmark_ok():
    bench = {"checksum": "sha256:x", "results": [
        {"name": "a", "checksum": "sha256:1"}, {"name": "b", "checksum": "sha256:2"}]}
    assert ART.verify_benchmark(bench)["ok"] is True


def test_verify_benchmark_unsorted():
    bench = {"checksum": "sha256:x", "results": [
        {"name": "z", "checksum": "sha256:1"}, {"name": "a", "checksum": "sha256:2"}]}
    assert ART.verify_benchmark(bench)["ok"] is False


def test_verify_benchmark_no_checksum():
    bench = {"results": []}
    assert ART.verify_benchmark(bench)["ok"] is False


def test_verify_snapshot_ok():
    assert ART.verify_snapshot({"is_binding": False, "total_records": 5})["ok"] is True


def test_verify_snapshot_binding_fails():
    assert ART.verify_snapshot({"is_binding": True, "total_records": 5})["ok"] is False


def test_verify_snapshot_no_count():
    assert ART.verify_snapshot({"is_binding": False})["ok"] is False


def test_verify_graph_ok():
    g = {"nodes": ["a", "b"], "edges": {"a": ["b"]}}
    assert ART.verify_graph_export(g)["ok"] is True


def test_verify_graph_dangling_edge():
    g = {"nodes": ["a"], "edges": {"a": ["ghost"]}}
    assert ART.verify_graph_export(g)["ok"] is False


def test_verify_checksum_ok():
    core = {"a": 1, "b": 2}
    payload = dict(core)
    payload["checksum"] = ART._sha(core)
    assert ART.verify_checksum(payload)["ok"] is True


def test_verify_checksum_tampered():
    payload = {"a": 1, "checksum": "sha256:wrong"}
    assert ART.verify_checksum(payload)["ok"] is False


def test_validate_artifacts_batch():
    arts = [{"kind": "report", "data": {"is_binding": False}},
            {"kind": "snapshot", "data": {"is_binding": False}}]
    assert ART.validate_artifacts(arts)["ok"] is True


def test_validate_artifacts_batch_fail():
    arts = [{"kind": "report", "data": {"is_binding": True}}]
    res = ART.validate_artifacts(arts)
    assert res["ok"] is False
    assert len(res["failed"]) == 1


@pytest.mark.parametrize("kind", ["report", "snapshot", "research_report"])
def test_binding_kinds(kind):
    assert ART.validate_artifact({"is_binding": True}, kind)["ok"] is False
    assert ART.validate_artifact({"is_binding": False}, kind)["ok"] is True


# ═══════════════ 보안 ═══════════════
_PKG = os.path.dirname(os.path.dirname(__file__))
_SRC = [os.path.join(_PKG, f) for f in os.listdir(_PKG) if f.endswith(".py")]

_FORBIDDEN = ("jarvis.execution", "jarvis.broker", "jarvis.portfolio", "jarvis.risk",
              "jarvis.permission", "jarvis.deployment", "jarvis.live", "jarvis.order")


@pytest.mark.parametrize("path", _SRC)
def test_no_forbidden_imports(path):
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(f) for f in _FORBIDDEN), node.module


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert "claude-opus" not in open(path).read().lower()
