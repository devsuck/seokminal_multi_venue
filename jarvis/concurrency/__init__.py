"""jarvis.concurrency — 동시성 안전 유틸리티 (P14 Production Hardening). **안전 append 전용, 완전 additive.**

다중 리더 / 배타적 append 락, 경로별 공유 락, 원자적 JSONL append, 안전 읽기, 스레드 안전성 검증을 제공한다. 기존
원장 스키마·공개 API 를 변경하지 않으며, 동시 변형(수정/삭제)은 지원하지 않는다 — append 만 직렬화한다. 실행 능력 없음.
"""
from jarvis.concurrency.locks import (  # noqa: F401
    RWLock,
    ThreadSafetyResult,
    atomic_append,
    file_lock,
    safe_read_lines,
    verify_thread_safety,
)
