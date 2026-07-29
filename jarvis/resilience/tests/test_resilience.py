"""P14 resilience 테스트 — 스캔·부분 replay·체크포인트·복구 복사·스냅샷·손상 진단·원본 불변·보안."""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.resilience import recover as RC
from jarvis.resilience.recover import (
    ScanResult,
    content_hash,
    diagnose_corruption,
    partial_replay,
    recover_to_copy,
    scan_ledger,
    snapshot_recovery,
    validate_checkpoint,
    verify_recoverable,
)

GENESIS = "GENESIS"


def _seal(core: dict, prev: str) -> dict:
    rec = dict(core)
    rec["previous_hash"] = prev
    rec["record_hash"] = content_hash(rec)
    return rec


def _build(path: str, n: int) -> list[dict]:
    """유효 해시체인 원장 생성."""
    recs: list[dict] = []
    prev = GENESIS
    for i in range(n):
        rec = _seal({"id": f"R{i}", "seq": i, "v": i * 10}, prev)
        recs.append(rec)
        prev = rec["record_hash"]
    with open(path, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return recs


# ═══════════════ scan_ledger ═══════════════
def test_scan_intact(tmp_path):
    p = str(tmp_path / "l.jsonl")
    _build(p, 10)
    res = scan_ledger(p)
    assert res.first_broken == -1
    assert res.valid_records == 10
    assert res.reason == "intact"


def test_scan_empty(tmp_path):
    p = str(tmp_path / "l.jsonl")
    open(p, "w").close()
    res = scan_ledger(p)
    assert res.valid_records == 0
    assert res.first_broken == -1


def test_scan_missing_file(tmp_path):
    res = scan_ledger(str(tmp_path / "nope.jsonl"))
    assert res.total_lines == 0
    assert res.valid_records == 0


def test_scan_trailing_newline_ok(tmp_path):
    p = str(tmp_path / "l.jsonl")
    _build(p, 3)
    with open(p, "a") as f:
        f.write("\n")
    res = scan_ledger(p)
    assert res.first_broken == -1
    assert res.valid_records == 3


def test_scan_detects_invalid_json(tmp_path):
    p = str(tmp_path / "l.jsonl")
    _build(p, 3)
    with open(p, "a") as f:
        f.write("{not json\n")
    res = scan_ledger(p)
    assert res.first_broken == 3
    assert res.reason == "invalid_json"


def test_scan_detects_chain_break(tmp_path):
    p = str(tmp_path / "l.jsonl")
    recs = _build(p, 5)
    recs[2]["previous_hash"] = "sha256:deadbeef"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    res = scan_ledger(p)
    assert res.first_broken == 2
    assert res.reason == "previous_hash_broken"


def test_scan_detects_hash_mismatch(tmp_path):
    p = str(tmp_path / "l.jsonl")
    recs = _build(p, 5)
    recs[3]["v"] = 99999  # record_hash 재계산 안됨 → mismatch
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    res = scan_ledger(p)
    assert res.first_broken == 3
    assert res.reason == "record_hash_mismatch"


def test_scan_detects_missing_hash(tmp_path):
    p = str(tmp_path / "l.jsonl")
    recs = _build(p, 3)
    del recs[1]["record_hash"]
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    res = scan_ledger(p)
    assert res.reason == "missing_record_hash"
    assert res.first_broken == 1


def test_scan_duplicate_id(tmp_path):
    p = str(tmp_path / "l.jsonl")
    recs = _build(p, 3)
    # 중복 id 를 유효 체인으로 이어붙이기
    dup = _seal({"id": "R0", "seq": 3, "v": 30}, recs[-1]["record_hash"])
    with open(p, "a") as f:
        f.write(json.dumps(dup) + "\n")
    res = scan_ledger(p, id_field="id")
    assert res.reason == "duplicate_id"


def test_scan_result_frozen(tmp_path):
    p = str(tmp_path / "l.jsonl")
    _build(p, 2)
    res = scan_ledger(p)
    with pytest.raises(Exception):
        res.valid_records = 0


# ═══════════════ partial_replay ═══════════════
def test_partial_replay_full(tmp_path):
    p = str(tmp_path / "l.jsonl")
    _build(p, 8)
    assert len(partial_replay(p)) == 8


def test_partial_replay_stops_at_corruption(tmp_path):
    p = str(tmp_path / "l.jsonl")
    recs = _build(p, 6)
    recs[4]["v"] = 123456
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert len(partial_replay(p)) == 4


def test_partial_replay_empty(tmp_path):
    p = str(tmp_path / "l.jsonl")
    open(p, "w").close()
    assert partial_replay(p) == []


# ═══════════════ validate_checkpoint ═══════════════
def test_validate_checkpoint_ok(tmp_path):
    p = str(tmp_path / "l.jsonl")
    recs = _build(p, 5)
    cp = {"seq": 2, "record_hash": recs[2]["record_hash"]}
    assert validate_checkpoint(p, cp)["valid"] is True


def test_validate_checkpoint_mismatch(tmp_path):
    p = str(tmp_path / "l.jsonl")
    _build(p, 5)
    cp = {"seq": 2, "record_hash": "sha256:wrong"}
    r = validate_checkpoint(p, cp)
    assert r["valid"] is False
    assert r["reason"] == "hash_mismatch"


def test_validate_checkpoint_out_of_range(tmp_path):
    p = str(tmp_path / "l.jsonl")
    _build(p, 3)
    r = validate_checkpoint(p, {"seq": 10, "record_hash": "x"})
    assert r["valid"] is False
    assert r["reason"] == "seq_out_of_range"


# ═══════════════ verify_recoverable ═══════════════
def test_verify_recoverable_intact(tmp_path):
    p = str(tmp_path / "l.jsonl")
    _build(p, 4)
    r = verify_recoverable(p)
    assert r["recoverable"] is True
    assert r["intact"] is True


def test_verify_recoverable_partial(tmp_path):
    p = str(tmp_path / "l.jsonl")
    recs = _build(p, 5)
    recs[3]["v"] = 999
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    r = verify_recoverable(p)
    assert r["recoverable"] is True
    assert r["intact"] is False
    assert r["valid_records"] == 3


def test_verify_recoverable_empty(tmp_path):
    p = str(tmp_path / "l.jsonl")
    open(p, "w").close()
    r = verify_recoverable(p)
    assert r["valid_records"] == 0


# ═══════════════ recover_to_copy (원본 불변) ═══════════════
def test_recover_to_copy_source_unchanged(tmp_path):
    src = str(tmp_path / "src.jsonl")
    dst = str(tmp_path / "dst.jsonl")
    _build(src, 6)
    before = open(src).read()
    res = recover_to_copy(src, dst)
    assert res["source_unchanged"] is True
    assert open(src).read() == before  # 원본 불변


def test_recover_to_copy_recovers_prefix(tmp_path):
    src = str(tmp_path / "src.jsonl")
    dst = str(tmp_path / "dst.jsonl")
    recs = _build(src, 6)
    recs[4]["v"] = 777
    with open(src, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    res = recover_to_copy(src, dst)
    assert res["recovered"] == 4
    assert sum(1 for _ in open(dst)) == 4


def test_recover_to_copy_dst_valid_chain(tmp_path):
    src = str(tmp_path / "src.jsonl")
    dst = str(tmp_path / "dst.jsonl")
    _build(src, 5)
    recover_to_copy(src, dst)
    assert scan_ledger(dst).first_broken == -1


def test_recover_to_copy_refuses_overwrite(tmp_path):
    src = str(tmp_path / "src.jsonl")
    dst = str(tmp_path / "dst.jsonl")
    _build(src, 3)
    open(dst, "w").close()
    with pytest.raises(FileExistsError):
        recover_to_copy(src, dst)


def test_recover_to_copy_refuses_same_path(tmp_path):
    src = str(tmp_path / "src.jsonl")
    _build(src, 3)
    with pytest.raises(ValueError):
        recover_to_copy(src, src)


# ═══════════════ snapshot_recovery ═══════════════
def test_snapshot_recovery_consistent(tmp_path):
    p = str(tmp_path / "l.jsonl")
    _build(p, 7)
    assert snapshot_recovery(p, {"total_records": 7})["consistent"] is True


def test_snapshot_recovery_inconsistent(tmp_path):
    p = str(tmp_path / "l.jsonl")
    _build(p, 7)
    r = snapshot_recovery(p, {"total_records": 99})
    assert r["consistent"] is False
    assert r["actual"] == 7


def test_snapshot_recovery_after_corruption(tmp_path):
    p = str(tmp_path / "l.jsonl")
    recs = _build(p, 6)
    recs[3]["v"] = 1
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    r = snapshot_recovery(p, {"total_records": 6})
    assert r["consistent"] is False
    assert r["actual"] == 3


# ═══════════════ diagnose_corruption ═══════════════
def test_diagnose_clean(tmp_path):
    p = str(tmp_path / "l.jsonl")
    _build(p, 5)
    d = diagnose_corruption(p)
    assert d["corrupted"] is False
    assert d["issue_count"] == 0


def test_diagnose_hash_mismatch(tmp_path):
    p = str(tmp_path / "l.jsonl")
    recs = _build(p, 4)
    recs[2]["v"] = 555
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    d = diagnose_corruption(p)
    assert d["corrupted"] is True
    assert any(i["issue"] == "hash_mismatch" for i in d["issues"])


def test_diagnose_invalid_json(tmp_path):
    p = str(tmp_path / "l.jsonl")
    _build(p, 2)
    with open(p, "a") as f:
        f.write("garbage\n")
    d = diagnose_corruption(p)
    assert any(i["issue"] == "invalid_json" for i in d["issues"])


def test_diagnose_missing_hash(tmp_path):
    p = str(tmp_path / "l.jsonl")
    recs = _build(p, 3)
    del recs[1]["record_hash"]
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    d = diagnose_corruption(p)
    assert any(i["issue"] == "missing_hash" for i in d["issues"])


def test_diagnose_deterministic(tmp_path):
    p = str(tmp_path / "l.jsonl")
    _build(p, 5)
    assert diagnose_corruption(p) == diagnose_corruption(p)


# ═══════════════ 파라미터화 ═══════════════
@pytest.mark.parametrize("n", [1, 3, 10, 50])
def test_scan_valid_counts(tmp_path, n):
    p = str(tmp_path / f"l{n}.jsonl")
    _build(p, n)
    assert scan_ledger(p).valid_records == n


@pytest.mark.parametrize("broken_at", [0, 1, 3, 7])
def test_scan_broken_position(tmp_path, broken_at):
    p = str(tmp_path / f"b{broken_at}.jsonl")
    recs = _build(p, 10)
    recs[broken_at]["v"] = 10**9
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    res = scan_ledger(p)
    assert res.first_broken == broken_at
    assert res.valid_records == broken_at


@pytest.mark.parametrize("n", [2, 5, 20])
def test_recover_roundtrip(tmp_path, n):
    src = str(tmp_path / f"s{n}.jsonl")
    dst = str(tmp_path / f"d{n}.jsonl")
    _build(src, n)
    res = recover_to_copy(src, dst)
    assert res["recovered"] == n


# ═══════════════ content_hash 관례 ═══════════════
def test_content_hash_excludes_meta():
    a = content_hash({"x": 1, "previous_hash": "p", "record_hash": "r"})
    b = content_hash({"x": 1, "previous_hash": "Q", "record_hash": "Z"})
    assert a == b


def test_content_hash_changes():
    assert content_hash({"x": 1}) != content_hash({"x": 2})


# ═══════════════ 보안 ═══════════════
_PKG = os.path.dirname(os.path.dirname(__file__))
_SRC = [os.path.join(_PKG, f) for f in os.listdir(_PKG) if f.endswith(".py")]

_FORBIDDEN_IMPORTS = ("jarvis.execution", "jarvis.broker", "jarvis.portfolio", "jarvis.risk",
                      "jarvis.permission", "jarvis.deployment", "jarvis.live", "jarvis.order")


@pytest.mark.parametrize("path", _SRC)
def test_no_forbidden_imports(path):
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(f) for f in _FORBIDDEN_IMPORTS), node.module


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert "claude-opus" not in open(path).read().lower()


def test_no_original_mutation_api():
    # 원본 원장 수정/삭제 API 미제공 — 복구는 새 파일로만
    src = open(os.path.join(_PKG, "recover.py")).read()
    assert "def recover_to_copy" in src
    assert "def delete_ledger" not in src
    assert "def repair_in_place" not in src
