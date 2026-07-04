"""Append-only 감사 로그(블랙박스).

모든 중요 행위 기록: agent·action·permission·risk·strategy·config_hash·
data_version·code_version·timestamp·result. **삭제/재작성 함수 없음.**
delete_audit_log 액션은 권한정책에서 FORBIDDEN.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from jarvis.config import CODE_VERSION, state_path

_AUDIT = "audit.jsonl"


def record(entry: dict) -> dict:
    """감사 항목 append. timestamp·code_version 자동. 반환=기록된 항목."""
    row = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "code_version": CODE_VERSION,
        **entry,
    }
    with open(state_path(_AUDIT), "a") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    return row


def read_all() -> list[dict]:
    import os
    p = state_path(_AUDIT)
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def tail(n: int = 20) -> list[dict]:
    return read_all()[-n:]
