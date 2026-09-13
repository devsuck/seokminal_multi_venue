"""Claude 호출 공유 헬퍼 — lv5_agent, ai_portfolio 등 배치성 LLM 호출이 공유.

ANTHROPIC_API_KEY 있으면 API 직접 호출(헤드리스 VM용), 없으면 로컬 claude CLI
subprocess로 폴백(맥 개발 — 구독, API 과금 0)."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess

_log = logging.getLogger(__name__)
_MODEL = "claude-sonnet-5"


def claude_bin() -> str | None:
    return shutil.which("claude") or (
        os.path.expanduser("~/.local/bin/claude")
        if os.path.exists(os.path.expanduser("~/.local/bin/claude")) else None
    )


def claude_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY")) or claude_bin() is not None


def _call_claude_api(prompt: str, timeout: int) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=timeout)
    resp = client.messages.create(
        model=_MODEL, max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def call_claude(claude_path: str | None, prompt: str, timeout: int = 90) -> str:
    """Claude 호출 → 응답 텍스트 반환. 실패 시 빈 문자열."""
    try:
        if os.environ.get("ANTHROPIC_API_KEY"):
            return _call_claude_api(prompt, timeout)
        if claude_path:
            proc = subprocess.run(
                [claude_path, "--dangerously-skip-permissions",
                 "--permission-mode", "bypassPermissions", "--print", prompt],
                capture_output=True, text=True, timeout=timeout,
            )
            return proc.stdout.strip()
        return ""
    except Exception as e:
        _log.warning("[claude_cli] 호출 실패: %s", e)
        return ""
