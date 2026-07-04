"""에이전트별 누적 전략 메모리 — Claude가 읽고 쓰는 append-only 로그.

각 리뷰 후 핵심 발견을 1~2줄로 기록. 다음 리뷰 시 Claude가 전체 이력 읽고 판단.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path


def _base_dir() -> Path:
    db = os.environ.get("AGENT_DB_PATH", "data/agents.db")
    return Path(db).parent


def memory_path(agent_id: str) -> Path:
    return _base_dir() / f"{agent_id}_memory.md"


def read_memory(agent_id: str, max_chars: int = 3000) -> str:
    """최근 max_chars 글자 반환. 파일 없으면 '(첫 리뷰)'."""
    p = memory_path(agent_id)
    if not p.exists():
        return "(메모리 없음 — 첫 리뷰)"
    text = p.read_text(encoding="utf-8")
    if len(text) > max_chars:
        # 항상 완전한 줄부터 시작
        truncated = text[-max_chars:]
        first_nl = truncated.find("\n")
        return truncated[first_nl + 1:] if first_nl >= 0 else truncated
    return text


def append_memory(agent_id: str, insight: str) -> None:
    """새 인사이트 한 줄 추가 (타임스탬프 포함)."""
    p = memory_path(agent_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    with p.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {insight.strip()}\n")


def clear_memory(agent_id: str) -> None:
    p = memory_path(agent_id)
    if p.exists():
        p.unlink()
