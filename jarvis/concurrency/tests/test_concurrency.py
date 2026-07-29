"""P14 concurrency 테스트 — RWLock·원자적 append·안전 읽기·스레드 안전성·보안."""
from __future__ import annotations

import ast
import json
import os
import threading

import pytest

from jarvis.concurrency.locks import (
    RWLock,
    ThreadSafetyResult,
    atomic_append,
    file_lock,
    safe_read_lines,
    verify_thread_safety,
)


# ═══════════════ RWLock ═══════════════
def test_rwlock_read_context():
    lk = RWLock()
    with lk.read_locked():
        assert lk._readers == 1
    assert lk._readers == 0


def test_rwlock_write_context():
    lk = RWLock()
    with lk.append_locked():
        assert lk._writer is True
    assert lk._writer is False


def test_rwlock_multiple_readers():
    lk = RWLock()
    lk.acquire_read()
    lk.acquire_read()
    assert lk._readers == 2
    lk.release_read()
    lk.release_read()
    assert lk._readers == 0


def test_rwlock_writer_excludes_reader():
    lk = RWLock()
    acquired = []

    def reader():
        lk.acquire_read()
        acquired.append("r")
        lk.release_read()

    lk.acquire_write()
    t = threading.Thread(target=reader)
    t.start()
    t.join(timeout=0.3)
    # 라이터 보유 중에는 리더가 진입 못함
    assert acquired == []
    lk.release_write()
    t.join(timeout=1.0)
    assert acquired == ["r"]


def test_rwlock_sequential_writers():
    lk = RWLock()
    order = []
    lk.acquire_write()
    order.append("w1")
    lk.release_write()
    lk.acquire_write()
    order.append("w2")
    lk.release_write()
    assert order == ["w1", "w2"]


# ═══════════════ file_lock ═══════════════
def test_file_lock_shared_per_path(tmp_path):
    p = str(tmp_path / "a.jsonl")
    assert file_lock(p) is file_lock(p)


def test_file_lock_distinct_paths(tmp_path):
    a = file_lock(str(tmp_path / "a.jsonl"))
    b = file_lock(str(tmp_path / "b.jsonl"))
    assert a is not b


def test_file_lock_normalizes(tmp_path):
    p1 = str(tmp_path / "a.jsonl")
    p2 = str(tmp_path / "." / "a.jsonl")
    assert file_lock(p1) is file_lock(p2)


# ═══════════════ atomic_append / safe_read ═══════════════
def test_atomic_append_writes(tmp_path):
    p = str(tmp_path / "l.jsonl")
    atomic_append(p, {"a": 1})
    atomic_append(p, {"a": 2})
    rows = safe_read_lines(p)
    assert rows == [{"a": 1}, {"a": 2}]


def test_atomic_append_creates_dir(tmp_path):
    p = str(tmp_path / "sub" / "l.jsonl")
    atomic_append(p, {"a": 1})
    assert os.path.exists(p)


def test_safe_read_missing_file(tmp_path):
    assert safe_read_lines(str(tmp_path / "nope.jsonl")) == []


def test_safe_read_ignores_partial_line(tmp_path):
    p = str(tmp_path / "l.jsonl")
    atomic_append(p, {"a": 1})
    with open(p, "a") as f:
        f.write('{"a": 2}')  # 개행 없는 부분 줄
    rows = safe_read_lines(p)
    assert rows == [{"a": 1}]


def test_safe_read_ignores_blank(tmp_path):
    p = str(tmp_path / "l.jsonl")
    atomic_append(p, {"a": 1})
    with open(p, "a") as f:
        f.write("\n")
    assert safe_read_lines(p) == [{"a": 1}]


def test_atomic_append_appends_not_overwrites(tmp_path):
    p = str(tmp_path / "l.jsonl")
    atomic_append(p, {"a": 1})
    atomic_append(p, {"a": 2})
    atomic_append(p, {"a": 3})
    assert len(safe_read_lines(p)) == 3


# ═══════════════ verify_thread_safety ═══════════════
def test_thread_safety_complete(tmp_path):
    p = str(tmp_path / "c.jsonl")
    res = verify_thread_safety(p, appenders=4, per_appender=25, readers=3)
    assert res.complete is True
    assert res.observed == res.expected == 100


def test_thread_safety_no_corruption(tmp_path):
    p = str(tmp_path / "c.jsonl")
    res = verify_thread_safety(p, appenders=3, per_appender=20, readers=2)
    assert res.no_corruption is True


def test_thread_safety_all_lines_valid_json(tmp_path):
    p = str(tmp_path / "c.jsonl")
    verify_thread_safety(p, appenders=4, per_appender=20, readers=2)
    with open(p) as f:
        for ln in f:
            json.loads(ln)  # 모든 줄이 유효 JSON


def test_thread_safety_result_type(tmp_path):
    p = str(tmp_path / "c.jsonl")
    res = verify_thread_safety(p, appenders=2, per_appender=10, readers=1)
    assert isinstance(res, ThreadSafetyResult)


def test_thread_safety_frozen(tmp_path):
    p = str(tmp_path / "c.jsonl")
    res = verify_thread_safety(p, appenders=2, per_appender=5, readers=1)
    with pytest.raises(Exception):
        res.observed = 0


def test_thread_safety_unique_records(tmp_path):
    p = str(tmp_path / "c.jsonl")
    verify_thread_safety(p, appenders=5, per_appender=30, readers=3)
    rows = safe_read_lines(p)
    seen = {(r["w"], r["i"]) for r in rows}
    assert len(seen) == len(rows)


@pytest.mark.parametrize("appenders,per,readers", [
    (2, 10, 1), (3, 20, 2), (4, 15, 3), (5, 10, 4),
])
def test_thread_safety_param(tmp_path, appenders, per, readers):
    p = str(tmp_path / f"c{appenders}{per}{readers}.jsonl")
    res = verify_thread_safety(p, appenders=appenders, per_appender=per, readers=readers)
    assert res.complete
    assert res.no_corruption
    assert res.observed == appenders * per


def test_concurrent_append_no_loss(tmp_path):
    p = str(tmp_path / "seq.jsonl")
    lk = file_lock(p)
    barrier = threading.Barrier(6)

    def worker(w):
        barrier.wait()
        for i in range(40):
            atomic_append(p, {"w": w, "i": i}, lock=lk)

    ts = [threading.Thread(target=worker, args=(w,)) for w in range(6)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(safe_read_lines(p)) == 6 * 40


def test_reader_view_monotonic_bound(tmp_path):
    p = str(tmp_path / "m.jsonl")
    res = verify_thread_safety(p, appenders=3, per_appender=20, readers=3)
    # 리더가 관측한 최대 뷰는 최종 개수를 넘지 않음
    assert res.max_reader_view <= res.observed


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


@pytest.mark.parametrize("path", _SRC)
def test_no_delete_update_api(path):
    src = open(path).read()
    for bad in ("def delete_", "def update_", "def overwrite_"):
        assert bad not in src


def test_no_mutation_api():
    # 동시 변형(수정/삭제) API 미제공 — append/read 만
    src = open(os.path.join(_PKG, "locks.py")).read()
    assert "def atomic_append" in src
    assert "def safe_read_lines" in src
    assert "def truncate" not in src
