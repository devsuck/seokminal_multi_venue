"""Claude CLI 호출 공유 헬퍼 — lv5_agent, ai_portfolio 등 배치성 LLM 호출이 공유."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess

_log = logging.getLogger(__name__)


def claude_bin() -> str | None:
    return shutil.which("claude") or (
        os.path.expanduser("~/.local/bin/claude")
        if os.path.exists(os.path.expanduser("~/.local/bin/claude")) else None
    )


def call_claude(claude_path: str, prompt: str, timeout: int = 90) -> str:
    """Claude CLI 호출 → stdout 반환. 실패 시 빈 문자열."""
    try:
        proc = subprocess.run(
            [claude_path, "--dangerously-skip-permissions",
             "--permission-mode", "bypassPermissions", "--print", prompt],
            capture_output=True, text=True, timeout=timeout,
        )
        return proc.stdout.strip()
    except Exception as e:
        _log.warning("[claude_cli] 호출 실패: %s", e)
        return ""
