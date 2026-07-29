"""동시성 안전 (P14) — 다중 리더 / 배타적 append. **안전 append 전용, 원장 스키마 불변.**

기존 원장 파일 형식(JSONL append-only)을 그대로 유지하면서, 안전한 동시 읽기와 원자적 append 를 제공한다. 동시 변형
(수정/삭제)은 지원하지 않는다 — append 만 배타적으로 직렬화한다. 스레드 안전성 검증 헬퍼를 포함한다.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass


class RWLock:
    """다중 리더 / 단일 라이터(append) 락. 라이터 대기 시 신규 리더 차단(라이터 기아 방지)."""

    def __init__(self) -> None:
        self._cond = threading.Condition(threading.Lock())
        self._readers = 0
        self._writer = False
        self._writers_waiting = 0

    def acquire_read(self) -> None:
        with self._cond:
            while self._writer or self._writers_waiting > 0:
                self._cond.wait()
            self._readers += 1

    def release_read(self) -> None:
        with self._cond:
            self._readers -= 1
            if self._readers == 0:
                self._cond.notify_all()

    def acquire_write(self) -> None:
        with self._cond:
            self._writers_waiting += 1
            while self._writer or self._readers > 0:
                self._cond.wait()
            self._writers_waiting -= 1
            self._writer = True

    def release_write(self) -> None:
        with self._cond:
            self._writer = False
            self._cond.notify_all()

    class _ReadCtx:
        def __init__(self, lock): self._lock = lock
        def __enter__(self): self._lock.acquire_read(); return self._lock
        def __exit__(self, *a): self._lock.release_read()

    class _WriteCtx:
        def __init__(self, lock): self._lock = lock
        def __enter__(self): self._lock.acquire_write(); return self._lock
        def __exit__(self, *a): self._lock.release_write()

    def read_locked(self) -> "RWLock._ReadCtx":
        return RWLock._ReadCtx(self)

    def append_locked(self) -> "RWLock._WriteCtx":
        return RWLock._WriteCtx(self)


# 파일 경로별 공유 append 락(프로세스 내) — 동일 파일 동시 append 직렬화
_FILE_LOCKS: dict = {}
_REGISTRY_LOCK = threading.Lock()


def file_lock(path: str) -> RWLock:
    """경로별 프로세스 내 공유 RWLock 반환(동일 파일 append 직렬화)."""
    key = os.path.abspath(path)
    with _REGISTRY_LOCK:
        lk = _FILE_LOCKS.get(key)
        if lk is None:
            lk = RWLock()
            _FILE_LOCKS[key] = lk
        return lk


def atomic_append(path: str, record: dict, *, lock: RWLock | None = None) -> None:
    """원자적 JSONL append — 한 줄을 통째로 기록(부분 줄 방지). append 락으로 직렬화.

    원장 스키마를 바꾸지 않는다. 기존 파일에 이어 붙이기만 한다.
    """
    lk = lock or file_lock(path)
    line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
    data = line.encode()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with lk.append_locked():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)


def safe_read_lines(path: str, *, lock: RWLock | None = None) -> list[dict]:
    """리더 락 하에 JSONL 안전 읽기(완전한 줄만 파싱)."""
    lk = lock or file_lock(path)
    with lk.read_locked():
        if not os.path.exists(path):
            return []
        out: list[dict] = []
        with open(path) as f:
            for ln in f:
                if not ln.endswith("\n"):
                    continue  # 부분 줄 무시(쓰기 진행 중)
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    out.append(json.loads(ln))
                except (ValueError, json.JSONDecodeError):
                    continue
        return out


@dataclass(frozen=True)
class ThreadSafetyResult:
    appenders: int
    per_appender: int
    readers: int
    expected: int
    observed: int
    complete: bool
    no_corruption: bool
    max_reader_view: int

    def to_dict(self) -> dict:
        return asdict(self)


def verify_thread_safety(path: str, *, appenders: int = 4, per_appender: int = 50,
                         readers: int = 4) -> ThreadSafetyResult:
    """동시 append + 동시 read 안전성 검증. 반환: 불변식 만족 여부.

    불변식: 모든 append 가 유실 없이 기록되고(complete), 어떤 줄도 손상되지 않는다(no_corruption).
    """
    lk = file_lock(path)
    barrier = threading.Barrier(appenders + readers)
    reader_views: list[int] = []
    reader_lock = threading.Lock()
    errors: list = []

    def append_worker(wid: int) -> None:
        try:
            barrier.wait()
            for i in range(per_appender):
                atomic_append(path, {"w": wid, "i": i, "v": wid * 100000 + i}, lock=lk)
        except Exception as e:  # pragma: no cover
            errors.append(repr(e))

    def read_worker() -> None:
        try:
            barrier.wait()
            for _ in range(per_appender):
                rows = safe_read_lines(path, lock=lk)
                with reader_lock:
                    reader_views.append(len(rows))
        except Exception as e:  # pragma: no cover
            errors.append(repr(e))

    threads = [threading.Thread(target=append_worker, args=(w,)) for w in range(appenders)]
    threads += [threading.Thread(target=read_worker) for _ in range(readers)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    rows = safe_read_lines(path, lock=lk)
    expected = appenders * per_appender
    observed = len(rows)
    # 손상 없음: 모든 줄이 유효 dict 이고 (w,i) 쌍이 유일
    seen = {(r.get("w"), r.get("i")) for r in rows}
    no_corruption = (not errors) and len(seen) == observed and all(
        isinstance(r.get("v"), int) for r in rows)
    return ThreadSafetyResult(
        appenders=appenders, per_appender=per_appender, readers=readers, expected=expected,
        observed=observed, complete=(observed == expected), no_corruption=no_corruption,
        max_reader_view=max(reader_views) if reader_views else 0)
